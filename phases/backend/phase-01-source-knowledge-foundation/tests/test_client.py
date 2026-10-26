import httpx
import pytest

from tripwise.config import Settings
from tripwise.source_client import TransientSourceError, WikivoyageClient


def test_client_retries_transient_status(monkeypatch):
    settings = Settings(
        database_url="sqlite:///:memory:",
        api_url="https://en.wikivoyage.org/w/api.php",
        user_agent="TripWiseAI-test",
        scope_mode="seeds_only",
        scope_root="Japan",
        seeds=["Tokyo"],
        max_depth=0,
        follow_go_next=False,
        allowed_page_types=["city"],
        request_delay_seconds=0,
        max_retries=2,
        timeout_seconds=5,
        batch_size=1,
        log_level="INFO",
        log_json=False,
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": {"code": "ratelimited"}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "title": "Tokyo",
                            "fullurl": "https://en.wikivoyage.org/wiki/Tokyo",
                            "revisions": [
                                {
                                    "revid": 10,
                                    "timestamp": "2026-09-08T00:00:00Z",
                                    "sha1": "abc",
                                    "slots": {"main": {"content": "{{guidecity}}\nTokyo"}},
                                }
                            ],
                        }
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = WikivoyageClient(settings, client=http_client)
    pages = client.fetch_pages(["Tokyo"])
    client.close()
    assert pages[0].title == "Tokyo"
    assert calls["n"] == 3


def test_client_does_not_retry_http_400():
    settings = Settings(
        database_url="sqlite:///:memory:",
        api_url="https://en.wikivoyage.org/w/api.php",
        user_agent="TripWiseAI-test",
        scope_mode="seeds_only",
        scope_root="Japan",
        seeds=["Tokyo"],
        max_depth=0,
        follow_go_next=False,
        allowed_page_types=["city"],
        request_delay_seconds=0,
        max_retries=3,
        timeout_seconds=5,
        batch_size=1,
        log_level="INFO",
        log_json=False,
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    client = WikivoyageClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Exception):
        client.fetch_pages(["Tokyo"])
    client.close()
    assert calls["n"] == 1
