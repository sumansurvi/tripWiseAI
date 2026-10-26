"""Unit tests for the cosine-gate suggestion (no Postgres)."""

from tripwise_p3.calibrate import suggest_min_score


def test_suggest_midpoint_when_in_corpus_is_above_out():
    assert suggest_min_score([0.72, 0.80], [0.40, 0.48]) == 0.60


def test_suggest_just_above_out_when_scores_overlap():
    assert suggest_min_score([0.50, 0.55], [0.54, 0.58]) == 0.60


def test_suggest_default_when_no_in_corpus():
    assert suggest_min_score([], [0.3]) == 0.50
