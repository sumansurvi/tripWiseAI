"""Pure-Python cosine ranking used by retrieve tests."""

from tripwise_p3.embedding_client import FakeEmbeddingClient
from tripwise_p3.retrieve import cosine_similarity, rank_by_cosine


def test_cosine_identical_is_one():
    v = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_rank_by_cosine_prefers_matching_planted_vector():
    client = FakeEmbeddingClient(dim=32)
    eat_vec = client.embed_query("Old Delhi street food kebabs eat")
    sleep_vec = client.embed_query("quiet hotels and hostels to sleep")
    query_vec = client.embed_query("Old Delhi eat")

    rows = [
        (
            "sleep-1",
            "Delhi/South",
            "Sleep",
            "Quiet boutique hotels.",
            "https://en.wikivoyage.org/wiki/Delhi/South",
            "Sleep",
            sleep_vec,
        ),
        (
            "eat-1",
            "Delhi/Old Delhi",
            "Eat",
            "Street food and kebabs.",
            "https://en.wikivoyage.org/wiki/Delhi/Old_Delhi",
            "Lead > Eat",
            eat_vec,
        ),
    ]
    hits = rank_by_cosine(query_vec, rows, top_k=2)
    assert hits[0].chunk_id == "eat-1"
    assert hits[0].source_url.endswith("Old_Delhi")
    assert hits[0].score >= hits[1].score
