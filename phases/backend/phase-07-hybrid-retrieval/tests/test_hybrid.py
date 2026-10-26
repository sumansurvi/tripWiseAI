from tripwise_p7.hybrid import _rrf_fuse
from tripwise_p3.retrieve import RetrieveHit


def _hit(cid: str, score: float) -> RetrieveHit:
    return RetrieveHit(
        title="t",
        section_title=None,
        text="x",
        source_url="https://en.wikivoyage.org/wiki/T",
        score=score,
        chunk_id=cid,
    )


def test_rrf_prefers_shared_ids():
    vector = [_hit("a", 0.9), _hit("b", 0.8), _hit("c", 0.7)]
    lexical = [_hit("b", 0.5), _hit("d", 0.4)]
    fused = _rrf_fuse(vector, lexical, top_k=3)
    ids = [h.chunk_id for h in fused]
    assert "b" in ids
    assert len(fused) == 3


def test_gate_blocks_weak_vector_matches_without_touching_lexical():
    from tripwise_p7.hybrid import hybrid_retrieve

    weak = lambda *_a, **_k: [_hit("a", 0.55), _hit("b", 0.50)]  # noqa: E731
    # session=None proves lexical search is never reached when the gate fails.
    out = hybrid_retrieve(
        None, None, "best things to do in Paris", vector_fn=weak, min_vector_score=0.65
    )
    assert out == []


def test_gate_allows_strong_vector_matches(monkeypatch):
    import tripwise_p7.hybrid as hybrid

    monkeypatch.setattr(hybrid, "lexical_candidates", lambda *a, **k: [])
    strong = lambda *_a, **_k: [_hit("a", 0.78), _hit("b", 0.70)]  # noqa: E731
    out = hybrid.hybrid_retrieve(
        None, None, "What to eat in Old Delhi?", vector_fn=strong, min_vector_score=0.65
    )
    assert [h.chunk_id for h in out] == ["a", "b"]


def test_content_tokens_drop_stopwords():
    from tripwise_p7.hybrid import _content_tokens

    assert _content_tokens("What is the best way to get around Jaipur?") == [
        "way",
        "jaipur",
    ]
