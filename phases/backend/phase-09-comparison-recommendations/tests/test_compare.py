from tripwise_p3.retrieve import RetrieveHit
from tripwise_p9.compare import build_comparison, interleave


def _h(title: str, cid: str) -> RetrieveHit:
    return RetrieveHit(
        title=title,
        section_title="Eat",
        text="food note",
        source_url=f"https://en.wikivoyage.org/wiki/{title.replace(' ', '_')}",
        score=0.8,
        chunk_id=cid,
    )


def test_comparison_interleaves_both_sides():
    hits = [_h("Delhi", "1"), _h("Delhi", "2"), _h("Mumbai", "3"), _h("Mumbai", "4")]
    result = build_comparison(["Delhi", "Mumbai"], hits)
    assert [h.chunk_id for h in result.evidence][:4] == ["1", "3", "2", "4"]
    assert result.missing == []


def test_comparison_reports_missing_side_and_no_internal_stats():
    hits = [_h("Delhi", "1"), _h("Delhi", "2")]
    result = build_comparison(["Delhi", "Mumbai"], hits)
    assert result.missing == ["Mumbai"]
    # No chunk-count "trade-offs" or canned recommendation leak into the UI.
    assert result.trade_offs == []
    assert result.recommendation is None


def test_interleave_dedupes():
    a = [_h("Delhi", "1")]
    b = [_h("Delhi", "1"), _h("Mumbai", "2")]
    assert [h.chunk_id for h in interleave(a, b)] == ["1", "2"]
