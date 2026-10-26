"""Silence noisy third-party warnings on Python 3.9 / macOS LibreSSL."""

from __future__ import annotations

import logging
import warnings


def suppress_vendor_noise(*, quiet_http_logs: bool = False) -> None:
    """Ignore google-auth FutureWarning and urllib3 NotOpenSSLWarning."""
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pydantic.*")
    # Match by message so we never import urllib3 (import itself emits the warning).
    warnings.filterwarnings(
        "ignore",
        message=r".*urllib3 v2 only supports OpenSSL.*",
    )
    warnings.filterwarnings("ignore", module=r"urllib3.*")
    warnings.filterwarnings(
        "ignore",
        message=r".*@model_validator.*",
    )
    try:
        from pydantic.warnings import PydanticDeprecatedSince212

        warnings.filterwarnings("ignore", category=PydanticDeprecatedSince212)
    except Exception:  # noqa: BLE001 — pydantic version may differ
        pass
    if quiet_http_logs:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("google_genai").setLevel(logging.WARNING)
