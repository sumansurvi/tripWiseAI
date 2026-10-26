from pathlib import Path

from tripwise_p10.eval_run import load_cases, run_fixture_eval, score_retrieval


FIX = Path(__file__).resolve().parents[1] / "fixtures" / "eval_cases.json"


def test_load_cases_has_journeys():
    cases = load_cases(FIX)
    assert len(cases) >= 30
    assert any(c.expect_refuse for c in cases)


def test_fixture_eval_routing():
    cases = load_cases(FIX)
    report = run_fixture_eval(cases)
    assert report["n_cases"] == len(cases)
    assert report["route_accuracy"] >= 0.7


def test_score_retrieval_hit():
    s = score_retrieval(
        expect_titles=["Delhi"],
        retrieved_titles=["Old Delhi", "India"],
        retrieved_urls=["https://en.wikivoyage.org/wiki/Old_Delhi"],
    )
    assert s.hit_at_k and s.citation_ok
