from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from tripwise.config import Settings
from tripwise.logging_utils import log_event

logger = logging.getLogger("tripwise.ingest.client")

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class TransientSourceError(Exception):
    pass


class PermanentSourceError(Exception):
    pass


@dataclass
class RetrievedPage:
    requested_title: str
    title: str
    wiki_page_id: int
    canonical_url: str
    revision_id: int | None
    revision_timestamp: datetime | None
    sha1: str | None
    wikitext: str
    missing: bool = False
    redirected_from: str | None = None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, TransientSourceError):
        return True
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.NetworkError):
        return True
    return False


class WikivoyageClient:
    """English Wikivoyage Action API client.

    Chosen over HTML scraping and browser automation (Playwright/Selenium)
    because it returns canonical page ids, revision metadata, and raw wikitext
    required for template extraction and traceable RAG citations.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=settings.timeout_seconds,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
        )
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WikivoyageClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _throttle(self) -> None:
        delay = self.settings.request_delay_seconds
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
            **params,
        }

        @retry(
            retry=retry_if_exception(_is_retryable),
            wait=wait_exponential_jitter(initial=1, max=30),
            stop=stop_after_attempt(self.settings.max_retries + 1),
            reraise=True,
        )
        def _call() -> dict[str, Any]:
            self._throttle()
            try:
                response = self._client.get(self.settings.api_url, params=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise TransientSourceError(str(exc)) from exc
            finally:
                self._last_request_at = time.monotonic()

            if response.status_code in TRANSIENT_STATUS:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(float(retry_after))
                    except ValueError:
                        time.sleep(2)
                raise TransientSourceError(f"HTTP {response.status_code}")
            if response.status_code >= 400:
                raise PermanentSourceError(f"HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
            if data.get("error"):
                code = str(data["error"].get("code", "api"))
                if code in {"maxlag", "ratelimited"}:
                    raise TransientSourceError(code)
                raise PermanentSourceError(code)
            return data

        return _call()

    def fetch_pages(self, titles: list[str]) -> list[RetrievedPage]:
        if not titles:
            return []
        joined = "|".join(titles)
        data = self._request(
            {
                "action": "query",
                "titles": joined,
                "prop": "info|revisions",
                "rvprop": "ids|timestamp|content|sha1",
                "rvslots": "main",
                "inprop": "url",
                "redirects": "1",
            }
        )
        query = data.get("query") or {}
        redirects = {item["from"]: item["to"] for item in query.get("redirects", [])}
        normalized = {item["from"]: item["to"] for item in query.get("normalized", [])}
        pages: list[RetrievedPage] = []
        by_title: dict[str, dict] = {}
        for page in query.get("pages", []):
            by_title[page.get("title")] = page

        for requested in titles:
            canonical = redirects.get(requested, requested)
            canonical = normalized.get(canonical, canonical)
            # Also try normalized requested title
            canonical = normalized.get(requested, canonical)
            page = by_title.get(canonical) or by_title.get(requested)
            if page is None:
                # MediaWiki may return the resolved title only
                if len(by_title) == 1:
                    page = next(iter(by_title.values()))
                else:
                    pages.append(
                        RetrievedPage(
                            requested_title=requested,
                            title=requested,
                            wiki_page_id=0,
                            canonical_url="",
                            revision_id=None,
                            revision_timestamp=None,
                            sha1=None,
                            wikitext="",
                            missing=True,
                        )
                    )
                    continue
            if page.get("missing"):
                pages.append(
                    RetrievedPage(
                        requested_title=requested,
                        title=page.get("title") or requested,
                        wiki_page_id=0,
                        canonical_url="",
                        revision_id=None,
                        revision_timestamp=None,
                        sha1=None,
                        wikitext="",
                        missing=True,
                    )
                )
                continue
            rev = (page.get("revisions") or [{}])[0]
            content = ((rev.get("slots") or {}).get("main") or {}).get("content") or ""
            ts = rev.get("timestamp")
            parsed_ts = None
            if ts:
                parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
            redirected_from = requested if canonical != requested else None
            pages.append(
                RetrievedPage(
                    requested_title=requested,
                    title=page.get("title") or requested,
                    wiki_page_id=int(page.get("pageid") or 0),
                    canonical_url=page.get("fullurl") or "",
                    revision_id=rev.get("revid"),
                    revision_timestamp=parsed_ts,
                    sha1=rev.get("sha1"),
                    wikitext=content,
                    redirected_from=redirected_from,
                )
            )
            log_event(
                logger,
                logging.INFO,
                "page_retrieved",
                page_id=page.get("pageid"),
                page_title=page.get("title"),
                operation="retrieve",
                status="ok",
            )
        return pages
