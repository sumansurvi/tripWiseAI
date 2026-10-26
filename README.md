# TripWise AI

A **RAG-powered travel chatbot**. Ask natural-language questions about destinations and get answers grounded in English Wikivoyage, with citations.

Full design (phase by phase: **Goal / Description / Outcome**): [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md).  
Phase 1 data shape: [docs/PHASE1_DATA_SCHEMA.md](docs/PHASE1_DATA_SCHEMA.md). Local ops: [docs/LOCAL_RUNTIME.md](docs/LOCAL_RUNTIME.md). Eval: [docs/eval/REPORT.md](docs/eval/REPORT.md).

This is the **only README** in the repo; per-phase notes are consolidated below.

## Hard rules

- **Citation rule:** every answer must cite the Wikivoyage `source_url`(s) used. Never invent a URL.
- **Chat LLM is Groq; embeddings are local bge by default (laptop).** Answers must come from **retrieved embeddings** (stored Wikivoyage chunks), not from the model alone. Empty or weak retrieval → "I don't know". **Vercel production forces Gemini** (`TRIPWISE_EMBEDDING_PROVIDER=gemini`) because ONNX/bge cannot ship in the serverless bundle.
- **Personal information** questions (passport, ID, bank, medical, private contact, "what is my …") are out of scope and refused.
- **Data acquisition** is the Wikivoyage **Action API** (`httpx`) — not Playwright, not HTML scraping. Phase 2 adds optional dumps for bulk India pages.
- Wikivoyage article **text** is [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); citations carry each page's canonical `source_url` and revision id. No image ingest in MVP.

---

## Quick start

Requires Python 3.11+, Node.js 20+, and PostgreSQL with **pgvector** (local or Supabase).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env   # then fill in keys
```

Build the corpus and vectors, then run the app:

```bash
# 1. acquire pages → data/raw|structured|chunks
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py init-db
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py ingest

# 2. embed chunks → pgvector
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py init-db
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed

# 3. API  → http://127.0.0.1:8000
python main.py

# 4. UI   → http://localhost:3000
npm run install:ui && npm run dev
```

---

## Folder layout

```text
tripWiseAI/
├── main.py                 # start the RAG chat API (Phase 5)
├── api/                    # Vercel Python: chat.py + health.py
├── vercel.json             # Next.js build + /chat|/health routes
├── config/                 # .env / .env.example
├── data/
│   ├── raw/                # Wikivoyage API JSON (+ source_url)
│   ├── structured/         # extracted sections/listings (+ source_url)
│   ├── chunks/             # RAG text units (+ source_url) → Phase 3 embeddings
│   └── dumps/              # optional enwikivoyage XML(.bz2) for Phase 2 bulk ingest
├── docs/
│   ├── RAG_ARCHITECTURE.md
│   ├── PHASE1_DATA_SCHEMA.md
│   ├── LOCAL_RUNTIME.md    # Phase 13 — local ops + Vercel notes
│   └── eval/REPORT.md
├── phases/
│   ├── backend/            # Phases 01–10 + go-ingest/ (optional Go acquisition)
│   └── frontend/           # Phases 11–12 (Next.js + research panels)
├── package.json            # npm run dev → Phase 11 UI
├── pytest.ini
├── README.md
├── requirements.txt        # local (includes fastembed)
└── requirements-vercel.txt # slim serverless deps (Gemini only)
```

---

## Current status

| Phase | Layer | Status |
|-------|--------|--------|
| 0 Product discovery | Docs | Done (in architecture) |
| 1 Source recon + India sample ingest | Backend | Done — [`phases/backend/phase-01-source-knowledge-foundation/`](phases/backend/phase-01-source-knowledge-foundation/) |
| 2 Scale India corpus (`scope_root` API; optional dump) | Backend | Pipeline done (current corpus = partial sample, ~487 pages / ~11k chunks) — [`phases/backend/phase-02-scale-india-corpus/`](phases/backend/phase-02-scale-india-corpus/) |
| 3 Embeddings + vector store (`chunks` → local bge → pgvector; Gemini optional) | Backend | Done — [`phases/backend/phase-03-embeddings-vector-store/`](phases/backend/phase-03-embeddings-vector-store/) |
| 4 Scheduler (P2 ingest → P3 embed) | Backend | Done — [`phases/backend/phase-04-scheduler/`](phases/backend/phase-04-scheduler/) |
| 5 RAG chat API (`POST /chat`, Groq) | Backend | Done — [`phases/backend/phase-05-rag-chat-api/`](phases/backend/phase-05-rag-chat-api/) |
| 6 Query routing | Backend | Done — [`phases/backend/phase-06-query-routing/`](phases/backend/phase-06-query-routing/) |
| 7 Hybrid retrieval | Backend | Done — [`phases/backend/phase-07-hybrid-retrieval/`](phases/backend/phase-07-hybrid-retrieval/) |
| 8 Conversation | Backend | Done — [`phases/backend/phase-08-conversation/`](phases/backend/phase-08-conversation/) |
| 9 Comparison / recommendations | Backend | Done — [`phases/backend/phase-09-comparison-recommendations/`](phases/backend/phase-09-comparison-recommendations/) |
| 10 RAG evaluation | Backend | Done — [`phases/backend/phase-10-rag-evaluation/`](phases/backend/phase-10-rag-evaluation/) |
| 11 Chat UI | Frontend | Done — [`phases/frontend/phase-11-chat-ui/`](phases/frontend/phase-11-chat-ui/) |
| 12 Research UI | Frontend | Done — [`phases/frontend/phase-12-research-ui/`](phases/frontend/phase-12-research-ui/) |
| 13 Local runtime docs (local Postgres default; optional Supabase `DATABASE_URL`) | Docs | Done — [`docs/LOCAL_RUNTIME.md`](docs/LOCAL_RUNTIME.md) |
| Go ingest (optional, additive) | Backend | Concurrent Wikivoyage → `data/*`, then Python embed — [`phases/backend/go-ingest/`](phases/backend/go-ingest/) |

**Known limits:** router entity list is a small hard-coded India set; Phase 7 lexical pass is token/ILIKE matching, not BM25/tsvector; Gemini fallback still has a free-tier ~1000 embed **requests**/day; Phase 8 conversation memory is process-local; live faithfulness/latency eval is manual.

---

## Configuration

Copy `config/.env.example` to `config/.env` and adjust. **Never commit `.env`.** Scripts load `config/.env`, then an optional repo-root `.env`.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres + pgvector. Must start with `postgresql://` (not `https://…supabase.co`) |
| `WIKIVOYAGE_API_URL` | Action API endpoint (default `en.wikivoyage.org/w/api.php`) |
| `WIKIVOYAGE_USER_AGENT` | Required descriptive User-Agent (Wikimedia policy) |
| `TRIPWISE_SCOPE_MODE` | `seeds_only` \| `seeds_and_districts` \| `scope_root` (Phase 2) |
| `TRIPWISE_SCOPE_ROOT` / `TRIPWISE_SEEDS` | India-first sample; change to add countries later |
| `TRIPWISE_MAX_DEPTH` / `TRIPWISE_MAX_PAGES` | Crawl depth / page cap (`0` = unlimited) |
| `TRIPWISE_REQUEST_DELAY_SECONDS` / `TRIPWISE_MAX_RETRIES` / `TRIPWISE_TIMEOUT_SECONDS` | HTTP pacing |
| `TRIPWISE_BATCH_SIZE` | Ingest batch size (also the default worker count for Go ingest) |
| `GEMINI_API_KEY` | Required only when `TRIPWISE_EMBEDDING_PROVIDER=gemini` |
| `GEMINI_EMBEDDING_MODEL` | Default `gemini-embedding-001` (768-d, must match `Vector(768)`) |
| `TRIPWISE_EMBEDDING_PROVIDER` | `local` (default, `BAAI/bge-base-en-v1.5` via fastembed) or `gemini` |
| `TRIPWISE_LOCAL_EMBEDDING_MODEL` | Default `BAAI/bge-base-en-v1.5` (768-d, same `Vector(768)` column) |
| `TRIPWISE_EMBED_BATCH_SIZE` | Texts per embed call, default `32` |
| `TRIPWISE_EMBED_MIN_INTERVAL_SEC` | Seconds between **Gemini** embed requests, default `0.35` (ignored for local) |
| `TRIPWISE_MIN_CHUNK_CHARS` | Skip junk chunks below this length, default `40` |
| `GROQ_API_KEY` | Chat generation (Phase 5) |
| `GROQ_MODEL` | Default `openai/gpt-oss-20b` |
| `TRIPWISE_CHAT_TOP_K` | Default `5` |
| `TRIPWISE_CHAT_MIN_SCORE` | Default `0.64` — hard relevance gate on best cosine similarity (calibrated on local bge) |
| `TRIPWISE_CHAT_HOST` / `TRIPWISE_CHAT_PORT` | API bind address |
| `TRIPWISE_SCHEDULER_MAX_PAGES` / `TRIPWISE_SCHEDULER_CRON` | Phase 4 tick cap / cron (default `0 3 * * *`) |
| `LOG_LEVEL` / `LOG_JSON` | Structured logging |
| `NEXT_PUBLIC_TRIPWISE_API_URL` | UI → API base. Unset in production = same-origin (`/chat`). Local dev defaults to `http://127.0.0.1:8000` |
| `TRIPWISE_CORS_ORIGINS` | Extra CORS origins (comma-separated). `VERCEL_URL` is added automatically |

`TRIPWISE_BATCH_SIZE` (ingest) and `TRIPWISE_EMBED_BATCH_SIZE` (texts per embed call) are different knobs.

### pgvector on Homebrew `postgresql@14`

`brew install pgvector` only ships files for Postgres 17/18. On 14, build from source once:

```bash
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector
cd /tmp/pgvector
make PG_CONFIG=/opt/homebrew/opt/postgresql@14/bin/pg_config
make PG_CONFIG=/opt/homebrew/opt/postgresql@14/bin/pg_config install
psql -d tripwise_p1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

### Optional Supabase (database only)

Point `DATABASE_URL` at a Supabase Postgres URI — prefer the **session/transaction pooler** host (`aws-0-<region>.pooler.supabase.com`, port `6543`) with user `postgres.<project_ref>` and `?sslmode=require`. The direct `db.<ref>.supabase.co` host may be IPv6-only and unreachable on IPv4 networks. URL-encode special characters in the password (`#` → `%23`). Run `CREATE EXTENSION IF NOT EXISTS vector;` in the SQL editor, then the usual `init-db` + `embed`. The API, UI, and Groq keys stay local; Gemini keys stay unused when `TRIPWISE_EMBEDDING_PROVIDER=local`. The publishable/anon key and `https://….supabase.co` URL are **not** used by the RAG path.

---

## Data artifacts

Website-derived JSON only (English Wikivoyage Action API). Not hand-authored samples.

| Folder | Meaning | Next use |
|--------|---------|----------|
| `raw/` | API-faithful page JSON: wikitext + revision metadata + **`source_url`** | Audit / re-parse |
| `structured/` | Extracted sections, listings, relationships + **`source_url`** | Inspect / debug |
| `chunks/` | RAG-ready text units (section/listing), each with **`source_url`** | Phase 3 `embed` → Gemini → pgvector |
| `dumps/` | Optional complete enwikivoyage XML(.bz2) for Phase 2 bulk ingest | `run_phase2.py ingest-dump` |

Contents of `data/raw`, `data/structured`, `data/chunks`, and `data/dumps` are gitignored (large). Rebuild JSON from Postgres without re-fetching:

```bash
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py export-data
```

---

## Phase 1 — Source knowledge foundation

Ingest a controlled **India** Wikivoyage sample into PostgreSQL and write citation-ready JSON under `data/{raw,structured,chunks}`. Discovers district children for huge cities, extracts sections/listings/relationships, upserts Postgres, exports JSON. Every record includes `source_url`. No embeddings here — `data/chunks` is the handoff into Phase 3.

```bash
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py init-db
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py ingest
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py inspect
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py quality
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py export-data
```

Optional helpers (both Action API, not browser crawls):

```bash
python phases/backend/phase-01-source-knowledge-foundation/scripts/crawl.py India Delhi --save-wiki
python phases/backend/phase-01-source-knowledge-foundation/scripts/parse.py \
  phases/backend/phase-01-source-knowledge-foundation/tests/fixtures/tokyo.wiki --title Tokyo
```

`tokyo.wiki` is a **parser regression fixture** only; the product corpus is India. `quality` prints the project rules plus research-query coverage with backing URLs. Shared library: `scripts/tripwise/` (client, discovery, extract, persist, `export_json`). Default scope is India (`TRIPWISE_SCOPE_ROOT=India`); for other countries change seeds in `config/.env` and re-ingest.

---

## Phase 2 — Scale India corpus

Reuses the Phase 1 pipeline to ingest every destination whose `isPartOf` ancestry reaches **India** (~1,000+ pages). Prefer Action API BFS; use dump ingest only with a **complete** local dump file. Outline articles are stored as-is (never LLM-filled).

```bash
python phases/backend/phase-02-scale-india-corpus/scripts/run_phase2.py init-db

# Option A — Action API BFS from India (recommended)
python phases/backend/phase-02-scale-india-corpus/scripts/run_phase2.py ingest-api --max-pages 50
# progress pages=12/50 succeeded=11 failed=0 skipped=1 queue=28 title=Delhi

# Option B — dump (optional, ~100+ MB; verify completeness first)
python phases/backend/phase-02-scale-india-corpus/scripts/download_dump.py --list   # prints URL only
python phases/backend/phase-02-scale-india-corpus/scripts/download_dump.py
python phases/backend/phase-02-scale-india-corpus/scripts/run_phase2.py ingest-dump \
  data/dumps/enwikivoyage-latest-pages-articles.xml.bz2

python phases/backend/phase-02-scale-india-corpus/scripts/run_phase2.py coverage
python phases/backend/phase-02-scale-india-corpus/scripts/run_phase2.py inspect
```

Phase 2 defaults (override in `config/.env`):

| Variable | Default |
|----------|---------|
| `TRIPWISE_SCOPE_MODE` | `scope_root` |
| `TRIPWISE_SCOPE_ROOT` | `India` |
| `TRIPWISE_SEEDS` | `India` |
| `TRIPWISE_MAX_DEPTH` | `12` |
| `TRIPWISE_FOLLOW_GO_NEXT` | `false` |
| `TRIPWISE_SKIP_PAGE_TYPES` | `itinerary,phrasebook` |
| `TRIPWISE_ALLOWED_PAGE_TYPES` | `country,region,city,district,park,topic,airport,unknown` |

The dump path is two-pass: index `isPartOf` parents, keep pages under `India`, then persist and export JSON with `source_url`.

---

## Optional Go ingest

Concurrent Wikivoyage acquisition into `data/*` using the same `TRIPWISE_*` / `WIKIVOYAGE_*` env vars. Writes the same JSON contracts with `source_url` and CC BY-SA attribution, then hand off to Python `embed`. Progress rewrites a single terminal line.

```bash
cd phases/backend/go-ingest
go build -o bin/tripwise-ingest ./cmd/tripwise-ingest
./bin/tripwise-ingest --max-pages 50 --workers 8
# then from repo root:
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--max-pages` | `TRIPWISE_MAX_PAGES` (`0` = unlimited) | Cap pages this run |
| `--workers` | `TRIPWISE_BATCH_SIZE` or `8` (max 16) | Concurrent fetch workers |
| `--seeds` | `TRIPWISE_SEEDS` | Comma-separated start titles |
| `--data-dir` | `<repo>/data` | Output root |

Limits: no Gemini/Groq calls, no Postgres page upsert, and a lightweight section splitter rather than full `mwparserfromhell` parity.

---

## Phase 3 — Embeddings + vector store

Reads `data/chunks/*.json`, embeds with the active provider (default **local** `BAAI/bge-base-en-v1.5` via `fastembed`; optional **Gemini** `gemini-embedding-001`), upserts `rag_documents` / `rag_chunks`. Both output **768-d** so the Supabase/pgvector schema is unchanged. Idempotent: unchanged `content_hash` skips the embed. `GEMINI_API_KEY` is required only for the Gemini fallback (not `GROQ_API_KEY`).

```bash
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py init-db
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py retrieve "Old Delhi eat" --top-k 5
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py calibrate-gate
```

`embed` batches texts (`TRIPWISE_EMBED_BATCH_SIZE`, default 32) and skips chunks shorter than 40 characters. Local embed has no daily cap. On the Gemini fallback, free-tier daily exhaustion pauses with status `PARTIAL` (exit 0) — re-run after reset and hash skip resumes.

Content hashes include `provider=local|model=BAAI/bge-base-en-v1.5` (or `provider=gemini|model=…`), so switching provider or model forces a re-embed. Do not mix models in one table. To wipe vectors instead:

```bash
psql -d tripwise_p1 -c 'TRUNCATE rag_chunks, rag_documents;'
```

---

## Phase 4 — Scheduler

Overlap lock on `ingestion_runs` → Phase 2 `ingest-api` → Phase 3 `embed`. If any run row is `RUNNING` with no `completed_at`, the tick **skips**.

```bash
# one-shot tick (optional safety cap)
TRIPWISE_SCHEDULER_MAX_PAGES=20 python phases/backend/phase-04-scheduler/scripts/run_phase4.py tick

# same orchestrator
python phases/backend/phase-04-scheduler/scripts/refresh.py

# daily cron loop (default 03:00 — TRIPWISE_SCHEDULER_CRON)
python phases/backend/phase-04-scheduler/scripts/run_phase4.py serve
```

After Phase 7, a lexical index rebuild may be registered (`SCHEDULER_LEXICAL_STAGE`); it is not wired into the tick graph until a tsvector-style index exists.

---

## Phase 5 — RAG chat API

Requires Phase 3 vectors plus `GROQ_API_KEY` (chat). Query embedding uses the same provider as Phase 3 (`TRIPWISE_EMBEDDING_PROVIDER=local` by default). `GEMINI_API_KEY` is only needed for the Gemini fallback.

```bash
python main.py
# same as: python phases/backend/phase-05-rag-chat-api/scripts/run_phase5.py
# optional: --host 127.0.0.1 --port 8000

curl -s -X POST http://127.0.0.1:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Old Delhi eat"}'
```

Turn behaviour:

1. Refuse personal-info asks (no Groq call)
2. Retrieve top-k; if empty or best cosine score < `TRIPWISE_CHAT_MIN_SCORE` → `"I don't know"`
3. Otherwise Groq answers **only** from retrieved context; `sources[]` are Wikivoyage URLs

`GET /health` is available for liveness. API startup does **not** probe Gemini, so an exhausted Gemini quota no longer blocks chat when the provider is local. After switching embedding models, run `calibrate-gate` and set `TRIPWISE_CHAT_MIN_SCORE` — bge cosine scores are not on the same scale as Gemini's.

---

## Phases 6–10 — Routing, hybrid, conversation, comparison, eval

| Phase | What it adds |
| --- | --- |
| 6 Query routing | Intent/entity heuristics + filtered retrieval; personal-info short-circuits to refusal. Wired into Phase 5 via `tripwise_p6` on `pythonpath` |
| 7 Hybrid retrieval | Vector + lexical (ILIKE/token overlap) fused with RRF (`k=60`); rerank disabled by default |
| 8 Conversation | In-process slots (`active_destination`, `compared_destinations`, `last_domain`); pass `conversation_id` on `/chat`; lost on API restart |
| 9 Comparison | Dual-destination evidence plus a labeled `recommendation` field |
| 10 Evaluation | Fixture cases in `phases/backend/phase-10-rag-evaluation/fixtures/eval_cases.json` (~30 India + refuse + absent); summary in [docs/eval/REPORT.md](docs/eval/REPORT.md) |

---

## Frontend (Phases 11–12)

Next.js + Tailwind chat with a tour/adventure theme and **dark / light** mode. Phase 12 research panels (recommendation / trade-offs, destination cards, suggested follow-ups) live in `phases/frontend/phase-12-research-ui` and are imported by the Phase 11 app via the `@research/*` alias — one runnable server.

```bash
# terminal 1 — API
python main.py

# terminal 2 — UI
npm run install:ui && npm run dev
# http://localhost:3000
```

Set `NEXT_PUBLIC_TRIPWISE_API_URL` if the API is not on `http://127.0.0.1:8000`.

---

## Deploy on Vercel (UI + API)

One Vercel project serves the Next.js UI and Python `/chat` + `/health` functions ([`vercel.json`](vercel.json), [`api/`](api/)). **Ingest, Go CLI, and the Phase 4 scheduler stay off Vercel** — run them on your laptop when refreshing the corpus.

**Embeddings on Vercel = Gemini only.** Local bge/ONNX is omitted from [`requirements-vercel.txt`](requirements-vercel.txt). Document and query vectors must both be Gemini — re-embed Supabase before the first deploy (do not mix with bge vectors).

### 1. Re-embed for Gemini (laptop → Supabase)

```bash
source .venv/bin/activate
# Temporary override for this shell; does not require editing config/.env permanently
export TRIPWISE_EMBEDDING_PROVIDER=gemini
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py calibrate-gate
```

Free-tier Gemini may pause with `PARTIAL` — re-run until `COMPLETED`. If laptop and Vercel share the same Supabase `DATABASE_URL`, set `TRIPWISE_EMBEDDING_PROVIDER=gemini` in local `.env` too (or use a separate local Postgres for bge).

### 2. Vercel project settings

- **Root Directory:** repository root (`.`)
- **Env vars** (Production + Preview):

| Variable | Value |
|----------|--------|
| `DATABASE_URL` | Supabase pooler URI (`sslmode=require`) |
| `GEMINI_API_KEY` | AI Studio key |
| `GROQ_API_KEY` | Groq key |
| `TRIPWISE_EMBEDDING_PROVIDER` | `gemini` (forced on Vercel even if unset) |
| `GROQ_MODEL` | e.g. `openai/gpt-oss-20b` |
| `TRIPWISE_CHAT_MIN_SCORE` | from `calibrate-gate` (often ~`0.65` for Gemini) |
| `TRIPWISE_CORS_ORIGINS` | optional; `VERCEL_URL` is allowed automatically |
| `NEXT_PUBLIC_TRIPWISE_API_URL` | leave **unset** for same-origin `/chat` |

### 3. Deploy

```bash
npx vercel          # preview
npx vercel --prod   # production
```

Smoke: `GET https://<deployment>/health` → `{"status":"ok"}`; UI at the deployment URL; ask “Old Delhi eat”.

**Limits:** Hobby plan function timeout may be tight for RAG+Groq (Pro allows 60s via the Python function). Phase 8 conversation slots are process-local — follow-ups can reset across cold starts.

---

## Tests

```bash
pytest -m 'not integration' -q          # everything in pytest.ini testpaths
pytest phases/backend/phase-03-embeddings-vector-store/tests -q   # one phase
```

Unit tests mock Groq and use `FakeEmbeddingClient`, so they need no network. Live tests (embeddings + Groq + Postgres) are opt-in:

```bash
TRIPWISE_RUN_INTEGRATION=1 pytest phases/backend/phase-05-rag-chat-api/tests -m integration -q
```

Those assert real Wikivoyage `source_url`s, refuse to invent prices when evidence lacks them, and smoke the `Old Delhi eat` retrieve → chat path.
