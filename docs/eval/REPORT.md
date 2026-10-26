# TripWise RAG eval report (Phase 10)

## Scope

- Fixture set: `phases/backend/phase-10-rag-evaluation/fixtures/eval_cases.json` (30 cases).
- Journeys A–J (India), personal-info refusals (P), known-absent (X: Kyoto/Paris).
- CI measures **routing / refusal** accuracy offline (no live Wikimedia).

## Baseline vs enhancements

| Layer | Change vs Phase 5 vector-only |
| --- | --- |
| Phase 6 | Intent routing + title filters + huge-city expansion |
| Phase 7 | Hybrid RRF (vector + lexical); rerank **off** pending lift |
| Phase 8 | `conversation_id` slots for follow-ups |
| Phase 9 | Comparison trade-offs + labeled recommendation |

## How to re-run

```bash
pytest phases/backend/phase-10-rag-evaluation/tests -q
```

## Notes

- Faithfulness / p95 latency against live Groq + embeddings remain manual (`TRIPWISE_RUN_INTEGRATION=1`).
- Citation rule unchanged: only `source_url` from retriever metadata.
