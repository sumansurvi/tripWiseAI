# Local runtime (Phase 13)

Run TripWise **on your machine by default**. No Docker or Kubernetes in this phase.
Optional: point `DATABASE_URL` at managed Postgres (e.g. Supabase) for the same schema + pgvector.

## Prerequisites

- Python 3.11+ with project `.venv` and `pip install -r requirements.txt`
- PostgreSQL with **pgvector** (local, or Supabase with `CREATE EXTENSION vector`)
- Node.js 20+ (for the chat UI)
- Keys in `config/.env`: `DATABASE_URL`, `GROQ_API_KEY`. `GEMINI_API_KEY` is only needed when `TRIPWISE_EMBEDDING_PROVIDER=gemini` (leave existing keys as-is)
- Optional: Go 1.22+ for [phases/backend/go-ingest](../phases/backend/go-ingest/)

## Backend API

```bash
# from repo root
source .venv/bin/activate
python main.py
# http://127.0.0.1:8000  — POST /chat, GET /health
```

Pipeline CLIs (as needed):

```bash
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py ingest
python phases/backend/phase-02-scale-india-corpus/scripts/run_phase2.py ingest-api --max-pages 50
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
TRIPWISE_SCHEDULER_MAX_PAGES=20 python phases/backend/phase-04-scheduler/scripts/run_phase4.py tick
# or: python phases/backend/phase-04-scheduler/scripts/run_phase4.py serve
```

### Optional Go ingest (fast acquisition → `data/`)

Does not change the UI or existing API keys. Writes `data/raw|structured|chunks`, then use Python embed + chat as usual.

```bash
cd phases/backend/go-ingest && go build -o bin/tripwise-ingest ./cmd/tripwise-ingest
./bin/tripwise-ingest --max-pages 5
# from repo root:
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
python main.py
```

### Optional Supabase

1. Create a project and copy the Postgres URI (use `sslmode=require`).
2. In the SQL editor: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Set `DATABASE_URL` in `config/.env` to that URI (do not commit `.env`).
4. Run existing `init-db` + `embed` CLIs. Embeddings are computed locally (bge) and stored in Supabase pgvector. Chat UI and Groq keys stay the same.

Local default remains `postgresql://tripwise:tripwise@127.0.0.1:5432/tripwise_p1`.

Phase 4 pipeline today: ingest-api → embed. A future lexical rebuild stage is documented as `SCHEDULER_LEXICAL_STAGE` in Phase 7 (not registered until a tsvector index exists).

## Frontend

```bash
# from repo root
npm run dev
# http://localhost:3000
```

Optional: `NEXT_PUBLIC_TRIPWISE_API_URL=http://127.0.0.1:8000`.

Phase 12 research panels are imported into the Phase 11 app (`@research/*`).

## Tests

```bash
pytest -m 'not integration' -q
```

Eval fixtures / report: [docs/eval/REPORT.md](eval/REPORT.md).

## Deploy on Vercel

See the **Deploy on Vercel** section in [README.md](../README.md). Summary:

- Same repo: Next.js UI + Python `api/chat.py` / `api/health.py` ([`vercel.json`](../vercel.json)).
- Vercel forces **Gemini** embeddings (no local bge in the serverless bundle). Re-embed Supabase with `TRIPWISE_EMBEDDING_PROVIDER=gemini` before chat will work in production.
- Set `DATABASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY` in the Vercel dashboard. Leave `NEXT_PUBLIC_TRIPWISE_API_URL` unset (same-origin `/chat`).
- Ingest / Go / Phase 4 scheduler remain **local-only**.

## Explicitly out of scope here

Docker images and Kubernetes. Managed Postgres (Supabase) is optional for the DB; Vercel hosts the chat UI + `/chat` API (not the ingest pipeline).
