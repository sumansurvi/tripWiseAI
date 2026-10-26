"""Embedding clients: local bge (default), Gemini fallback, Fake for tests."""

from __future__ import annotations

import os
import re
import time
from typing import Callable, List, Optional, Protocol, Sequence, TypeVar

from tripwise_p3.config import (
    DEFAULT_LOCAL_EMBEDDING_MODEL,
    Settings,
    is_local_provider,
)
from tripwise_p3.warnings_util import suppress_vendor_noise

suppress_vendor_noise()

# Pace between API *requests* (a request may embed many texts). Free tier ~100 RPM.
EMBED_MIN_INTERVAL_SEC = float(os.getenv("TRIPWISE_EMBED_MIN_INTERVAL_SEC", "0.35"))
# Texts per embed_content call — fewer requests → faster + more chunks per daily quota.
EMBED_BATCH_SIZE = max(1, int(os.getenv("TRIPWISE_EMBED_BATCH_SIZE", "32")))
# Official BGE retrieval instruction — documents are embedded without this prefix.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_RPM_RETRIES = 5
DEFAULT_RETRY_SECONDS = 10.0
DEFAULT_TRANSIENT_RETRY_SECONDS = 5.0

T = TypeVar("T")


class DailyQuotaExceeded(RuntimeError):
    """Raised when Gemini free-tier daily embed quota is exhausted."""


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """Return one embedding vector per input text (same order)."""
        ...

    def embed_query(self, text: str) -> List[float]:
        ...


def _http_status(exc: BaseException) -> Optional[int]:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"\b(429|500|502|503|504)\b", str(exc))
    if match:
        return int(match.group(1))
    return None


def is_resource_exhausted(exc: BaseException) -> bool:
    if _http_status(exc) == 429:
        return True
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def is_transient_gemini_error(exc: BaseException) -> bool:
    """True for temporary Gemini outages (503/5xx) that should be retried."""
    status = _http_status(exc)
    if status in {500, 502, 503, 504}:
        return True
    text = str(exc).upper()
    return "UNAVAILABLE" in text


def classify_gemini_quota(exc: BaseException) -> Optional[str]:
    """Return 'rpm', 'daily', or None if not a Gemini quota error."""
    if not is_resource_exhausted(exc):
        return None
    text = str(exc)
    if "PerMinute" in text or "RequestsPerMinute" in text:
        return "rpm"
    if "PerDay" in text or "RequestsPerDay" in text:
        return "daily"
    if re.search(r"retry in\s+\d", text, flags=re.IGNORECASE):
        return "rpm"
    # Exhausted without a short retry hint → treat as hard / daily stop.
    return "daily"


def parse_retry_seconds(
    exc: BaseException, default: float = DEFAULT_RETRY_SECONDS
) -> float:
    match = re.search(
        r"retry in\s+([\d.]+)\s*s", str(exc), flags=re.IGNORECASE
    )
    if match:
        try:
            seconds = float(match.group(1))
            if seconds > 0:
                return min(seconds, 120.0)
        except ValueError:
            pass
    return default


def call_with_quota_retry(
    embed_once: Callable[[], T],
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    on_rate_limited: Optional[Callable[[float], None]] = None,
    max_retries: int = MAX_RPM_RETRIES,
) -> T:
    """Run one embed call; sleep/retry on RPM 429 and 503; raise on daily quota."""
    last_exc: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            return embed_once()
        except Exception as exc:  # noqa: BLE001 — classify API errors
            last_exc = exc
            kind = classify_gemini_quota(exc)
            if kind == "daily":
                raise DailyQuotaExceeded(str(exc)) from exc
            retryable = kind == "rpm" or is_transient_gemini_error(exc)
            if retryable and attempt < max_retries - 1:
                if kind == "rpm":
                    wait = parse_retry_seconds(exc)
                else:
                    wait = min(
                        DEFAULT_TRANSIENT_RETRY_SECONDS * (2**attempt),
                        60.0,
                    )
                if on_rate_limited is not None:
                    on_rate_limited(wait)
                sleep_fn(wait)
                continue
            raise
    assert last_exc is not None
    raise last_exc


class GeminiEmbeddingClient:
    """Embed text with the Gemini embedding API (google-genai SDK)."""

    def __init__(
        self,
        settings: Settings,
        *,
        on_rate_limited: Optional[Callable[[float], None]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        min_interval_sec: Optional[float] = None,
        batch_size: Optional[int] = None,
        probe: bool = True,
    ):
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is missing or empty in config/.env.\n"
                "1. Create a key at https://aistudio.google.com/apikey\n"
                "2. Set:  GEMINI_API_KEY=your_key_here\n"
                "3. Keep GEMINI_EMBEDDING_MODEL=gemini-embedding-001"
            )
        from google import genai

        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_embedding_model
        self._dim = settings.embedding_dim
        self.on_rate_limited = on_rate_limited
        self._sleep_fn = sleep_fn
        self._min_interval_sec = (
            EMBED_MIN_INTERVAL_SEC if min_interval_sec is None else min_interval_sec
        )
        self._batch_size = EMBED_BATCH_SIZE if batch_size is None else max(1, batch_size)
        if hasattr(settings, "embed_batch_size") and batch_size is None:
            self._batch_size = max(1, int(settings.embed_batch_size))
        if hasattr(settings, "embed_min_interval_sec") and min_interval_sec is None:
            self._min_interval_sec = float(settings.embed_min_interval_sec)
        self._last_embed_mono: Optional[float] = None
        if probe:
            self._probe_model_access()

    def _pace(self) -> None:
        if self._last_embed_mono is None or self._min_interval_sec <= 0:
            return
        elapsed = time.monotonic() - self._last_embed_mono
        wait = self._min_interval_sec - elapsed
        if wait > 0:
            self._sleep_fn(wait)

    def _embed_request(self, texts: Sequence[str]) -> List[List[float]]:
        """One Gemini request for 1..N texts (batch)."""
        if not texts:
            return []
        self._pace()
        contents: object = texts[0] if len(texts) == 1 else list(texts)
        result = self._client.models.embed_content(
            model=self._model,
            contents=contents,
            config={"output_dimensionality": self._dim},
        )
        self._last_embed_mono = time.monotonic()
        embeddings = list(result.embeddings or [])
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Expected {len(texts)} embeddings, got {len(embeddings)}"
            )
        out: List[List[float]] = []
        for emb in embeddings:
            values = list(emb.values)
            if len(values) != self._dim:
                raise ValueError(
                    f"Expected embedding dim {self._dim}, got {len(values)}"
                )
            out.append(values)
        return out

    def _probe_model_access(self) -> None:
        """Fail fast if Gemini embeddings are unavailable for this key/model."""
        try:
            call_with_quota_retry(
                lambda: self._embed_request(["tripwise embedding probe"]),
                sleep_fn=self._sleep_fn,
                on_rate_limited=self.on_rate_limited,
                max_retries=3,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Gemini embeddings unavailable for model '{self._model}'.\n"
                f"API error: {exc}\n"
                "Check GEMINI_API_KEY and https://aistudio.google.com/apikey"
            ) from exc

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        out: List[List[float]] = []
        batch = self._batch_size
        for start in range(0, len(texts), batch):
            chunk = list(texts[start : start + batch])
            vectors = call_with_quota_retry(
                lambda c=chunk: self._embed_request(c),
                sleep_fn=self._sleep_fn,
                on_rate_limited=self.on_rate_limited,
            )
            out.extend(vectors)
        return out

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]


class FakeEmbeddingClient:
    """Deterministic embeddings for unit tests (no network)."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        self.calls.append(list(texts))
        vectors: List[List[float]] = []
        for text in texts:
            seed = sum(ord(c) for c in text) % 997
            vec = [0.0] * self.dim
            for i in range(min(32, self.dim)):
                vec[i] = ((seed + i * 13) % 100) / 100.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]


class LocalEmbeddingClient:
    """Local ONNX embeddings (default BAAI/bge-base-en-v1.5, 768-d). No API quota.

    Pass ``model`` in tests to avoid downloading weights. Queries get the BGE
    retrieval prefix; document texts are embedded as given.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        model: object = None,
        model_name: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        self._dim = settings.embedding_dim
        self._model_name = (
            model_name
            or getattr(settings, "local_embedding_model", None)
            or DEFAULT_LOCAL_EMBEDDING_MODEL
        )
        if batch_size is not None:
            self._batch_size = max(1, batch_size)
        elif hasattr(settings, "embed_batch_size"):
            self._batch_size = max(1, int(settings.embed_batch_size))
        else:
            self._batch_size = EMBED_BATCH_SIZE
        self._model = model

    def _ensure_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - env-specific
            raise RuntimeError(
                "Local embeddings require the 'fastembed' package.\n"
                "Install with:  pip install -r requirements.txt"
            ) from exc
        self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def _as_vector(self, raw: Sequence[float]) -> List[float]:
        values = [float(x) for x in raw]
        if len(values) != self._dim:
            raise ValueError(
                f"Expected embedding dim {self._dim}, got {len(values)}"
            )
        return values

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        embed = getattr(model, "embed")
        try:
            raw_iter = embed(list(texts), batch_size=self._batch_size)
        except TypeError:
            raw_iter = embed(list(texts))
        out = [self._as_vector(vec) for vec in raw_iter]
        if len(out) != len(texts):
            raise ValueError(
                f"Expected {len(texts)} embeddings, got {len(out)}"
            )
        return out

    def embed_query(self, text: str) -> List[float]:
        q = text.strip()
        if not q.startswith(BGE_QUERY_PREFIX):
            q = BGE_QUERY_PREFIX + q
        return self.embed_texts([q])[0]


def make_embedding_client(
    settings: Settings,
    *,
    probe: bool = False,
    on_rate_limited: Optional[Callable[[float], None]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> EmbeddingClient:
    """Build the client for ``TRIPWISE_EMBEDDING_PROVIDER`` (local | gemini).

    API startup should pass ``probe=False`` so a Gemini 429 cannot take chat down.
    The Gemini CLI path may pass ``probe=True`` to fail fast.
    """
    provider = (settings.embedding_provider or "").strip().lower()
    if is_local_provider(provider):
        return LocalEmbeddingClient(settings)
    if provider == "gemini":
        return GeminiEmbeddingClient(
            settings,
            on_rate_limited=on_rate_limited,
            sleep_fn=sleep_fn,
            probe=probe,
        )
    raise ValueError(
        f"Unknown TRIPWISE_EMBEDDING_PROVIDER={provider!r}. Use 'local' or 'gemini'."
    )
