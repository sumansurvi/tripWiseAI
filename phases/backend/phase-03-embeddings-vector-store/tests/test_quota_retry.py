"""Unit tests for Gemini 429 RPM/daily classification and retry."""

import pytest

from tripwise_p3.embedding_client import (
    DailyQuotaExceeded,
    call_with_quota_retry,
    classify_gemini_quota,
    is_transient_gemini_error,
    parse_retry_seconds,
)

RPM_MSG = (
    "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: "
    "embed_content_free_tier_requests, limit: 100, model: gemini-embedding-1.0\n"
    "Please retry in 9.78s. "
    "quotaId': 'EmbedContentRequestsPerMinutePerUserPerProjectPerModel-FreeTier'"
)

DAILY_MSG = (
    "429 RESOURCE_EXHAUSTED. "
    "quotaId': 'EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier'"
)

UNAVAILABLE_MSG = (
    "503 UNAVAILABLE. {'error': {'code': 503, "
    "'message': 'The service is currently unavailable.', "
    "'status': 'UNAVAILABLE'}}"
)


def test_classify_rpm():
    assert classify_gemini_quota(Exception(RPM_MSG)) == "rpm"


def test_classify_daily():
    assert classify_gemini_quota(Exception(DAILY_MSG)) == "daily"


def test_classify_non_quota():
    assert classify_gemini_quota(ValueError("bad dim")) is None


def test_is_transient_503():
    assert is_transient_gemini_error(Exception(UNAVAILABLE_MSG)) is True
    assert is_transient_gemini_error(Exception(RPM_MSG)) is False


def test_parse_retry_seconds():
    assert parse_retry_seconds(Exception(RPM_MSG)) == pytest.approx(9.78)


def test_call_retries_rpm_then_succeeds():
    sleeps: list[float] = []
    notices: list[float] = []
    state = {"n": 0}

    def embed_once():
        state["n"] += 1
        if state["n"] < 3:
            raise Exception(RPM_MSG)
        return [0.1, 0.2]

    out = call_with_quota_retry(
        embed_once,
        sleep_fn=sleeps.append,
        on_rate_limited=notices.append,
        max_retries=5,
    )
    assert out == [0.1, 0.2]
    assert state["n"] == 3
    assert len(sleeps) == 2
    assert notices == sleeps
    assert sleeps[0] == pytest.approx(9.78)


def test_call_retries_503_then_succeeds():
    sleeps: list[float] = []
    state = {"n": 0}

    def embed_once():
        state["n"] += 1
        if state["n"] < 3:
            raise Exception(UNAVAILABLE_MSG)
        return [0.3, 0.4]

    out = call_with_quota_retry(
        embed_once,
        sleep_fn=sleeps.append,
        on_rate_limited=lambda _: None,
        max_retries=5,
    )
    assert out == [0.3, 0.4]
    assert state["n"] == 3
    assert sleeps == [5.0, 10.0]


def test_call_raises_daily_without_retry():
    sleeps: list[float] = []

    def embed_once():
        raise Exception(DAILY_MSG)

    with pytest.raises(DailyQuotaExceeded):
        call_with_quota_retry(
            embed_once,
            sleep_fn=sleeps.append,
            max_retries=5,
        )
    assert sleeps == []
