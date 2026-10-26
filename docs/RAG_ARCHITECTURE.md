# TripWise AI — Architecture

TripWise AI is a **RAG-powered travel chatbot**. Every assistant turn **retrieves Wikivoyage context from the embedding store, then generates with Groq**. The LLM is never the knowledge source.

This document is organized **phase by phase**. Each phase uses the same format: **Goal**, **Description**, **Outcome**. Implementation code for a phase lives under `phases/backend/phase-0N-.../` (backend) or `phases/frontend/phase-0N-.../` (frontend). Shared `config/`, `data/`, and `docs/` stay at the repo root. Optional additive tools: `phases/backend/go-ingest/` (fast Wikivoyage acquisition → `data/`) and managed Postgres via `DATABASE_URL` (e.g. Supabase).

**Product question:**

> What does the available travel knowledge tell me about this destination, and how does it relate to my question?

```text
User message (Next.js UI → POST /chat)
  → rewrite with short-term conversation slots (conversation_id)
  → refuse if personal / out-of-scope (no answer from model alone)
  → route intent/entities (Phase 6)
  → retrieve Wikivoyage chunks (Phase 7 hybrid: pgvector + lexical; RRF)
  → if no relevant chunks / cosine below gate → "I don't know" (do not invent)
  → generate with Groq from retrieved context only
  → show Answer (Markdown/tables) / Sources (source_url required) /
      optional Recommendation & trade-offs / Ask next
```

**Hard product rules (all phases):**

1. **Chat LLM = Groq; embeddings = local bge by default.** Generation for `/chat` uses Groq. Phase 3 embeddings default to `LocalEmbeddingClient` (`TRIPWISE_EMBEDDING_PROVIDER=local`, model `BAAI/bge-base-en-v1.5` → pgvector @768d) so indexing and query embed do not share Gemini free-tier quota. Optional fallback: `TRIPWISE_EMBEDDING_PROVIDER=gemini` (`gemini-embedding-001`, same 768-d column). Never answer travel questions from the model alone. Do **not** mix Gemini and bge vectors in one table — `content_hash` includes `provider=…|model=…` so a switch forces a full re-embed.
2. **No standalone LLM answers.** The chatbot must not answer from the model’s own memory or world knowledge. Every travel claim must come from **retrieved embedding-backed chunks** (and optional SQL over stored Wikivoyage rows). Empty or irrelevant retrieval → refuse / “I don’t know.”
3. **Citation rule.** Every user-facing answer must cite the Wikivoyage `source_url`(s) of the chunks or records used. Never invent a URL.
4. **Personal information is out of scope.** If the user asks for personal data about themselves or others (e.g. passport numbers, Aadhaar, bank details, medical records, private contact info, “what is my …”), the bot **must not answer**. Reply that personal information is outside TripWise’s scope and steer back to destination research grounded in Wikivoyage.

---



## Phase map

```text
P0 Product
  → P1 Source recon + knowledge foundation (India sample; data/raw|structured|chunks)
      → P2 Scale corpus (full India destination tree / dumps)
      → [optional] Go ingest (concurrent Action API → data/*; then Python embed)
      → P3 Embeddings + vector store (chunks.json → local bge (or Gemini) → pgvector)
      → P4 Scheduler ──┐
      → P5 RAG chat API → P6 Routing → P7 Hybrid → P8 Conversation
        → P9 Recommend → P10 Eval
        → P11 FE Chat UI → P12 FE Research UI → P13 Local runtime (+ optional Supabase DB)
                       cron│
  P4 triggers P1/P2 ingest → P3 re-embed changed chunks <─┘
```

**Stack:** Python / FastAPI (uvicorn), Next.js / TypeScript / Tailwind, PostgreSQL + **pgvector** (local default **or** optional Supabase via `DATABASE_URL`), **Groq (chat LLM)**, **local bge embeddings** (default; Gemini optional fallback). Optional **Go** ingest CLI for faster acquisition into `data/`.

**Monolith.** No microservices, Celery, Redis, or Kubernetes.

**Primary runtime entrypoints (from repo root):**


| Entrypoint                                          | Role                                                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| `python main.py`                                    | Phase 5 FastAPI — `http://127.0.0.1:8000` (`POST /chat`, `GET /health`) |
| `npm run dev`                                       | Phase 11 Next.js UI — `http://localhost:3000` → API                     |
| `python …/run_phase1.py …`                          | Acquire / export India sample → Postgres + `data/*`                     |
| `python …/run_phase2.py ingest-api`                 | Scale India BFS ingest                                                  |
| `python …/run_phase3.py init-db | embed | retrieve | calibrate-gate` | pgvector schema + local/Gemini embed + dry retrieve + gate calibration |
| `python …/run_phase4.py tick | serve`               | Scheduled P2 ingest → P3 embed                                          |
| `phases/backend/go-ingest/bin/tripwise-ingest`      | Optional concurrent Wikivoyage → `data/*`                               |


**Target system (Phases 5–13):**

```text
┌─────────────┐     POST /chat      ┌──────────────────┐
│  Frontend   │ ──────────────────► │  FastAPI backend │
│  Next.js    │ ◄────────────────── │  RAG turn        │
│  :3000      │   answer+evidence   │  :8000 (main.py) │
└─────────────┘                     └────────┬─────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
             PostgreSQL+pgvector      Groq (chat P5)           Local bge embeddings
             local OR Supabase                                 (P3 store + query
             (DATABASE_URL)                                     embed on /chat;
                                                                Gemini optional)
                    ▲
             Scheduler: discover → acquire → extract → chunk → embed
                    ▲
             Wikivoyage Action API (P1/P2 default; optional Go ingest)
             + optional dumps (P2)
             data/raw → data/structured → data/chunks → vectors
```

---



## End-to-end data & chat flow (as implemented)

```text
1. ACQUIRE
   Python P1/P2  OR  Go ingest (workers)
        │
        ▼
   data/raw/*.json  +  data/structured/*.json  +  data/chunks/*.json
   (every artifact has source_url; CC BY-SA attribution)

2. EMBED  (Phase 3)
   run_phase3.py init-db   → CREATE EXTENSION vector; rag_documents / rag_chunks
   run_phase3.py embed     → local bge (default) or Gemini batch embed
                           → skip unchanged content_hash
                           → Gemini-only: pause PARTIAL on free-tier daily 1000-request quota
        │
        ▼
   Postgres/Supabase pgvector (768-d)

3. CHAT  (Phases 5–9 behind main.py)
   POST /chat { message, conversation_id? }
        → P6 route (personal_info → refuse)
        → P8 rewrite with slots
        → P7 hybrid_retrieve (vector gate TRIPWISE_CHAT_MIN_SCORE, then lexical + RRF)
        → weak/empty → "I don't know"
        → Groq generate + citation scrub
        → JSON: answer, evidence[], sources[], refused, …

4. UI  (Phases 11–12)
   npm run dev → ChatApp (frozen chrome: sidebar | thread+composer | right rail)
   Sources in right “Next stop” panel and under assistant bubbles
   Jump-to-latest when scrolled up; trips in localStorage
```

**Secrets** live only in `config/.env` (never commit): `DATABASE_URL`, `GROQ_API_KEY`, and `GEMINI_API_KEY` (Gemini fallback only). Local runtime notes: [docs/LOCAL_RUNTIME.md](LOCAL_RUNTIME.md).

---



## Phase 0 — Product discovery

**Goal:** Define the RAG chatbot product before any code: audience, must-answer journeys, and MVP boundaries.

**Description:** Write what TripWise is and is not. Grounded conversational research over the English Wikivoyage **India** destination tree, with citations. Answers must come from **retrieved embeddings / stored Wikivoyage data**, generated with **Groq** — never from the model alone. Out of scope: booking, live prices, itinerary builder, worldwide crawl, accounts, and **any personal information** (passport, ID numbers, bank/medical/private contact details, “what is my …”). Primary journeys cover destination overview, activities, attractions, transport, stay areas, food, practical tips, comparison, personalized *trip* research (preferences about destinations only), and follow-ups.

**Outcome:** A written product spec. Anyone can state what TripWise is and is not without reading Wikivoyage internals. India-wide coverage and chat-as-UX are explicit MVP requirements.


| In spec                                            | Out of spec                                           |
| -------------------------------------------------- | ----------------------------------------------------- |
| Conversational travel research                     | Ungrounded general-purpose chatbot / LLM-only answers |
| Grounded Q&A from embeddings + citations           | Search-result dump with no synthesis                  |
| Source facts vs AI synthesis vs AI recommendation  | Fake Wikivoyage citations                             |
| Follow-up questions about destinations             | Hour-by-hour itinerary builder                        |
| Full English Wikivoyage **India destination tree** | Worldwide crawl, booking, live prices, accounts       |
| Destination / trip preference questions            | **Personal information** (PII about user or others)   |



| ID  | Journey               | Example                                       |
| --- | --------------------- | --------------------------------------------- |
| A   | Destination research  | Tell me about Jaipur                          |
| B   | Activities            | Best things to do in Delhi                    |
| C   | Attractions           | What attractions should I visit?              |
| D   | Transportation        | How do I get around Delhi?                    |
| E   | Stay areas            | Which area should I stay in?                  |
| F   | Food                  | What food should I try?                       |
| G   | Practical             | What should I know before visiting India?     |
| H   | Comparison            | Delhi vs Mumbai                               |
| I   | Personalized research | 4 days, history and food — what to prioritize |
| J   | Follow-up             | What about something cheaper?                 |


---



## Phase 1 — Source reconnaissance, data acquisition & knowledge foundation

**Goal:** Inspect real English Wikivoyage structure and build a controlled ingest pipeline that stores rich, traceable source text — in PostgreSQL and as JSON under `data/` — without building the chatbot.

**Description:** Use the Wikivoyage **Action API** (`https://en.wikivoyage.org/w/api.php` via `httpx`) to discover, retrieve, parse, extract, validate, and upsert pages. **Do not use Playwright, Selenium, or HTML scraping** — the API returns page ids, revisions, and raw wikitext needed for templates and citations. Default corpus is an **India sample** (configurable seeds/scope so other countries can be added later). Every page writes three JSON artifacts: `data/raw` (API + wikitext), `data/structured` (sections/listings/relationships), and `data/chunks` (citation-ready text units). Every record includes `source_url`. Huge cities keep listings on district pages. No embeddings in this phase — `data/chunks` is the **input** for Phase 3.

**Env (selection):** `WIKIVOYAGE_API_URL`, `WIKIVOYAGE_USER_AGENT` (required by Wikimedia policy), `TRIPWISE_SCOPE_MODE`, `TRIPWISE_SCOPE_ROOT`, `TRIPWISE_SEEDS`, `TRIPWISE_MAX_DEPTH`, `TRIPWISE_REQUEST_DELAY_SECONDS`, `TRIPWISE_BATCH_SIZE`, `DATABASE_URL`.

**Code:** `phases/backend/phase-01-source-knowledge-foundation/`  
**Schema:** [docs/PHASE1_DATA_SCHEMA.md](PHASE1_DATA_SCHEMA.md)

**Commands:**

```bash
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py init-db
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py ingest
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py inspect
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py quality
python phases/backend/phase-01-source-knowledge-foundation/scripts/run_phase1.py export-data
```

**Outcome:** India sample ingested and inspectable; `data/raw|structured|chunks` populated with `source_url` on every file/chunk; quality checks list backing URLs per research question; tests cover classify/extract/validate/dedup. Embeddings, chat, and UI are out of scope.

```text
Wikivoyage Action API
  → discover → retrieve → parse → extract → clean → validate → upsert
  → PostgreSQL (pages, sections, listings, relationships, runs)
  → data/raw + data/structured + data/chunks  (each with source_url)
```

---



## Phase 2 — Scale acquisition to the product corpus

**Goal:** Scale the Phase 1 pipeline to every English Wikivoyage destination whose `isPartOf` ancestry reaches **India** (~1,000+ pages).

**Description:** Reuse Phase 1 extractors and tables. Expand discovery with `TRIPWISE_SCOPE_MODE=scope_root` seeding **India**, following region/city/district children, skipping itineraries and phrasebooks. Outline articles are stored as-is — never filled by an LLM. Continue writing `data/raw|structured|chunks` for each page.

**How to get pages (plain language):** Wikivoyage is a library of destination pages.


| Path                               | Analogy                                                                                          | When to use                                                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `ingest-api` **(default)**         | Start at the **India** book and walk linked shelves over the network                             | Development, testing, and scaling India for this project — works without a dump file                                      |
| `ingest-dump` **(optional)**       | Download the **entire** English Wikivoyage library as one `.xml.bz2`, then keep only India pages | Bulk offline run **only after** a complete local dump file exists (verify size; partial downloads fail or corrupt ingest) |
| **Go ingest (optional, additive)** | Concurrent Action API workers writing the same `data/`* contracts                                | Faster acquisition when Go is installed; still use Python Phase 3 for embed                                               |


`--list` on the dump download helper only **prints the URL** — it does not download. Expected dump size is on the order of ~100+ MB for `enwikivoyage-latest-pages-articles.xml.bz2`; treat smaller files as incomplete.

**Progress:** While ingesting, the CLI prints live lines such as `progress pages=12/50 succeeded=11 failed=0 skipped=1 queue=28 title=Delhi`. After a run, use `coverage` / `inspect` for totals. Denominator is `--max-pages` when set; otherwise API shows open-ended `pages=N` + `queue=Q`, and dump uses the known India in-scope count.

**Code:** `phases/backend/phase-02-scale-india-corpus/` (reuses Phase 1 `tripwise` library)

**Outcome:** Same tables and JSON layout, India tree populated toward ~1,000+ destinations; coverage = processed / discovered with skip/fail reasons and live progress. No chatbot and no embeddings yet (embedding runs in Phase 3 over the chunk files/rows).

```text
Option A (project default):
  seed India → scope_root BFS → Action API → extract/validate/upsert → data/*
  (use --max-pages while testing; raise/remove for fuller coverage)

Option B (optional bulk, complete dump file required):
  enwikivoyage dump → isPartOf ancestry to India → same persist path

Option C (optional Go — see “Optional Go ingest” below):
  concurrent fetch → lightweight section split → data/* → then P3 embed
```

---



## Optional Go ingest (additive; not a numbered phase)

**Goal:** Speed up Wikivoyage **acquisition** into `data/` with concurrent workers, without replacing Python embed, Groq chat, or the Next.js UI.

**Description:** CLI under `phases/backend/go-ingest/`. Reads the same `TRIPWISE_`* / `WIKIVOYAGE_*` env vars from `config/.env`. Fetches pages via the Action API with a worker pool; writes `data/raw`, `data/structured`, and `data/chunks` with `source_url` and CC BY-SA attribution. Uses a **lightweight** wikitext section splitter (not full `mwparserfromhell` parity). Does **not** upsert Phase 1 Postgres page tables and does **not** call the embedding model or Groq. Progress overwrites a **single terminal line** (`ok` / `fail` / `skip` counts).

**Build / run:**

```bash
cd phases/backend/go-ingest
go build -o bin/tripwise-ingest ./cmd/tripwise-ingest
./bin/tripwise-ingest --max-pages 50 --workers 8
# then from repo root:
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
python main.py
```


| Flag / env                           | Meaning                              |
| ------------------------------------ | ------------------------------------ |
| `--max-pages` / `TRIPWISE_MAX_PAGES` | Cap pages this run (`0` = unlimited) |
| `--workers` / `TRIPWISE_BATCH_SIZE`  | Concurrent fetch workers (capped)    |
| `--seeds` / `TRIPWISE_SEEDS`         | Comma-separated start titles         |
| `--data-dir`                         | Output root (default `<repo>/data`)  |


**Outcome:** Faster `data/`* refresh path; Phase 3 embed + Phase 5 chat unchanged. Commands and flags: [README.md](../README.md).

---



## Phase 3 — Embeddings and vector store

**Goal:** Turn Phase 1/2 (or Go) `data/chunks` into **embeddings** stored in **PostgreSQL + pgvector**, so retrieval can find evidence by meaning without calling Wikivoyage per question.

**Description:** This is the embedding and vector-store phase. Read citation-ready chunks from `data/chunks/*.json`. Each chunk already carries `source_url`, title, revision, and text. Create `rag_documents` / `rag_chunks` tables with a pgvector column; embed with the active provider into **768-d** vectors (must match `Vector(768)`). Default provider is **local** `BAAI/bge-base-en-v1.5` via `fastembed` (`LocalEmbeddingClient`, `TRIPWISE_EMBEDDING_PROVIDER=local`) — no Gemini quota, query and document embed both run on the developer machine. Optional fallback: `TRIPWISE_EMBEDDING_PROVIDER=gemini` via `GeminiEmbeddingClient` (`GEMINI_EMBEDDING_MODEL`, default `gemini-embedding-001`). Factory: `make_embedding_client`. Queries for local bge are prefixed with `Represent this sentence for searching relevant passages: `; documents are embedded as given (title / heading / `provider=…|model=…` prefix from `build_embed_text`). MVP keeps Phase 1’s section/listing chunks 1:1 (skip junk text under 40 chars / `TRIPWISE_MIN_CHUNK_CHARS`).

**Batching & pacing (implemented):** Texts are embedded in batches (`TRIPWISE_EMBED_BATCH_SIZE`, default **32**). For Gemini, multiple chunk texts are sent in **one** `embed_content` request and the minimum interval between API **requests** is `TRIPWISE_EMBED_MIN_INTERVAL_SEC` (default **0.35**). Local embed ignores the Gemini interval (no RPM). Idempotent stage `chunk_embed_index` embeds only new/changed `content_hash` values (hashes include `provider=local|model=BAAI/bge-base-en-v1.5` or `provider=gemini|model=…` so a provider/model switch forces re-embed) and prints live single-line `progress embedded=…` updates. Skip checks load `id` + `content_hash` in **one** query (not full 768-d vectors). Writes use PostgreSQL `INSERT … ON CONFLICT` **once per table per batch** so a remote `DATABASE_URL` (Supabase pooler) is not one round-trip per chunk. Gemini path: on **RPM** / transient 503, sleep and retry; on **daily free-tier** exhaustion (~**1000** embed requests/day), pause with status `PARTIAL`, exit 0, and instruct re-run after reset (hash skip resumes). Gemini CLI embed may probe the API; the chat API always constructs the client with `probe=False` so a 429 cannot block startup. Local client init downloads ONNX weights on first use (cached thereafter) and does not call Gemini. No chat generation in this phase — only store vectors that Phase 5 will retrieve with **Groq**.

**Code:** `phases/backend/phase-03-embeddings-vector-store/`  
**Prerequisite:** Postgres with the `vector` extension (`init-db` runs `CREATE EXTENSION IF NOT EXISTS vector`). Same command works against **Supabase** when `DATABASE_URL` points at the pooler URI with `sslmode=require`. Switching from Gemini to local (or the reverse) **requires a full re-embed** into the same table — mixed-model vectors make cosine scores meaningless.

**Commands:**

```bash
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py init-db
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py embed
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py retrieve "Old Delhi eat" --top-k 5
python phases/backend/phase-03-embeddings-vector-store/scripts/run_phase3.py calibrate-gate
```

**Outcome:** PostgreSQL + pgvector populated; every stored vector row retains `source_url` and revision metadata; `chunk_embed_index` can run on changed pages only; retrieve returns top-k chunks **without** an LLM. Chat API and UI remain out of scope. `calibrate-gate` prints a suggested `TRIPWISE_CHAT_MIN_SCORE` from Phase 10 fixture queries (in-corpus vs out-of-corpus best cosine).


| Table           | Role                                                                                      |
| --------------- | ----------------------------------------------------------------------------------------- |
| `rag_documents` | Section- or listing-level text unit + `source_url` + `content_hash`                       |
| `rag_chunks`    | Embedding vector + citation metadata (`source_url`, title, section, revision_id, license) |


```text
data/chunks/*.json
        │
        ▼
  chunk_embed_index
        │  batch texts (default 32) → local bge (default) or Gemini embed_content
        │  skip unchanged content_hash
        │  Gemini-only: PARTIAL pause on free-tier daily quota
        ▼
  PostgreSQL + pgvector  (rag_chunks.embedding, source_url, …)
  (local 127.0.0.1 or Supabase DATABASE_URL)
        │
        ▼
  retrieve top-k  (used by Phase 5 RAG; no generation here)
```

---



## Phase 4 — Scheduler

**Goal:** Keep chatbot knowledge fresh by **re-running backend data stages** on a schedule — ingest, then re-embed changed chunks.

**Description:** A **local** scheduler process (no Docker) ticks daily/weekly via APScheduler in-process, or an OS cron/`launchd` job that calls a one-shot tick. Each tick: Phase 2 discover + acquire + extract → refresh `data/`* → Phase 3 `chunk_embed_index` for changed hashes → optional later lexical rebuild (Phase 7). Not Celery/Redis/Kubernetes CronJobs. Overlap lock on `ingestion_runs`; a failed stage aborts without corrupting the last good index. The chat API keeps reading committed rows and does not need a restart.

**Implemented:** CLI under Phase 4 — `run_phase4.py tick` / `serve`, and `refresh.py` (same orchestrator). Each tick: if any `ingestion_runs` row is `RUNNING` with no `completed_at`, **skip**; else insert a scheduler-owned run, subprocess Phase 2 `ingest-api` → Phase 3 `embed`, then mark `COMPLETED` or `FAILED`. Env such as `TRIPWISE_SCHEDULER_MAX_PAGES` can cap ingest during ticks.

**Code:** `phases/backend/phase-04-scheduler/`

**Outcome:** One scheduled tick executes stages in order under an `ingestion_run` id; overlap lock works; `scripts/refresh.py` uses the same orchestrator. Frontend is never in the graph.

```text
On tick:
  P2 ingest-api (discover + acquire + extract → data/*)
  → P3 chunk_embed_index (changed hashes only)
  → later index stages (e.g. lexical rebuild — SCHEDULER_LEXICAL_STAGE when tsvector lands)
```

---



## Phase 5 — RAG chat API

**Goal:** Expose retrieve-then-generate over HTTP using Phase 3 vectors and **Groq** as the chat LLM. No frontend yet.

**Description:** FastAPI `POST /chat` (served with **uvicorn** via root `main.py` → `run_phase5.py`) loads the user message. **Before generation:** (1) if the ask is **personal information** or otherwise out of scope → return a refusal (no Groq travel answer); (2) **retrieve top-k chunks** via Phase 7 hybrid (query embedded with the same provider as Phase 3 — local bge by default); (3) if retrieval is empty or the best **cosine** score is below **`TRIPWISE_CHAT_MIN_SCORE`** (recalibrate with `run_phase3.py calibrate-gate` after any model switch; **0.64** on `BAAI/bge-base-en-v1.5` @768d over the current India corpus — in-corpus best-cosine ≥ ~0.67, out-of-corpus ≤ ~0.62; not the old Gemini 0.65 scale) → “I don’t know” — **do not let Groq answer from its own knowledge**. Only then assemble context with citation IDs/`source_url` and generate with **Groq** (`GROQ_MODEL`, e.g. `openai/gpt-oss-20b`). Drop any model-invented citations. Prompt rules: use only provided retrieved context; label source facts vs synthesis vs recommendation; hedge stale practical facts; do not browse the live web; never fulfill personal-data requests.

**MVP wiring:** Phases 6–9 are imported on the same process path (`sys.path` for `tripwise_p6`…`tripwise_p9`). Request body accepts `message`, optional `conversation_id`, and `history` (history is accepted for compatibility; follow-ups are driven by **Phase 8 slots** + `conversation_id`, not by replaying `history` into the rewrite). Response JSON includes `request_id`, `answer`, `evidence[]`, `sources[]`, `refused`, `refusal_reason`, and optional recommendation fields from Phase 9.

**Also:** `GET /health` for liveness. Startup constructs the embedding client via `make_embedding_client(..., probe=False)`. Local provider needs no Gemini key and does not probe the Gemini API, so daily-quota 429s cannot take chat down. Gemini fallback still requires `GEMINI_API_KEY` but also skips the fatal startup probe.

**Code:** `phases/backend/phase-05-rag-chat-api/`  
**Entrypoint:** `main.py` at repo root.

**Outcome:** `/chat` returns `answer`, `evidence[]`, `sources[]` (each with real Wikivoyage `source_url`) when retrieval succeeds; personal-info and empty-retrieval cases return explicit refusals. API tests cover journeys A–G plus personal-info refusal; Groq path tested; `request_id` logged.

```text
message → scope check (refuse personal info)
  → P8 slot rewrite (conversation_id)
  → hybrid retrieve (pgvector + lexical; query embed = active provider)
  → no/weak hits (cosine < TRIPWISE_CHAT_MIN_SCORE) → "I don't know"
  → context + source_url IDs → Groq chat
  → answer + evidence + sources (+ optional recommendation)
```

---



## Phase 6 — Query routing and structured retrieval

**Goal:** Stop treating every chat turn as the same blind vector search.

**Description:** Classify intent and entities (destination, attraction, transport, food, practical, comparison, follow-up, **personal_info / out_of_scope**, unanswerable, etc.). Personal-info and clear out-of-scope intents **short-circuit** to a refusal — no embedding retrieval needed for an answer. For in-scope travel intents, combine title/entity filters with vector search over stored embeddings. Expand huge-city questions to district children (e.g. Delhi/Mumbai parents) unless the user asked only for an overview. Example: “What currency in India?” → country practical docs + filters; “Lively nightlife” → semantic search over district Drink/Understand; “What is my passport number?” → refuse.

**Implemented:** Heuristic router in `tripwise_p6/router.py` with a small hard-coded India destination list (`KNOWN_DESTINATIONS`). Unknown place names fall through to unfiltered search + the Phase 5/7 relevance gate (often “I don’t know” when cosine is weak).

**Code:** `phases/backend/phase-06-query-routing/`

**Outcome:** Same `/chat` API routes by intent/entity; personal-info refusals are reliable; entity and practical questions beat Phase 5 vector-only on a small eval subset. No frontend, BM25 index table, or cross-encoder yet.

---



## Phase 7 — Hybrid retrieval and reranking

**Goal:** Improve exact-name and “vibe” retrieval only when metrics show lift.

**Description:** Fuse **vector** retrieval with a **lexical** pass behind `/chat`. Optional rerank (top 20 → top 5) enabled **only if** eval shows improvement (`enable_rerank` defaults **off**). If a proper lexical index (e.g. `tsvector`) is added later, register rebuild stage `SCHEDULER_LEXICAL_STAGE` so Phase 4 refreshes it after ingest/embed.

**Implemented:** Lexical candidates use distinctive query tokens with **ILIKE / token overlap** over stored chunk text (not a full BM25 engine yet). Fusion is **RRF** with `k=60`. The **cosine relevance gate** still applies to vector hits first — lexical alone cannot rescue queries that fail the min-score gate. Rerank remains reserved/off.

**Code:** `phases/backend/phase-07-hybrid-retrieval/`

**Outcome:** Documented A/B vs Phase 6; default path is hybrid RRF with gate; scheduler pipeline notes lexical rebuild for when tsvector lands. No new databases or frontend work.

---



## Phase 8 — Conversation

**Goal:** Make follow-ups work on the API so “which is cheaper?” does not require repeating the city.

**Description:** Maintain short-term slots (`active_destination`, `compared_destinations`, `last_listing_ids`, `last_domain`, last ~10 turns) and rewrite the query with that context. No user accounts and no long-term PII. New `conversation_id` clears slots.

**Implemented:** In-process `ConversationStore` (`tripwise_p8/memory.py`) tracks `active_destination`, `compared_destinations`, and `last_domain`; short follow-ups (≤8 words) are rewritten as `"<text> (regarding <destination>)"`. `last_listing_ids` is **spec only — not implemented yet**. Slots are **lost when the API process restarts**. The UI stores `conversation_id` (and trips) in **localStorage** and sends it on `/chat`.

**Code:** `phases/backend/phase-08-conversation/`

**Outcome:** Multi-turn API pairs pass (Journey J). Frontend history chrome is in Phases 11–12.

---



## Phase 9 — Comparison and recommendations

**Goal:** Support Journey H and labeled recommendations as API fields — never as fake source facts.

**Description:** When comparing two India destinations, retrieve evidence for both and return trade-offs with evidence IDs/`source_url`s. Optional `recommendation` field is clearly AI-labeled and omitted when unsupported.

**Implemented:** Comparison path retrieves per entity and interleaves evidence; Groq may return a labeled `recommendation`. A `trade_offs` field exists on the API contract; current turn assembly may still return an empty `trade_offs` list pending richer extraction. UI Recommendation / Trade-offs panels consume whatever the API returns (Phase 12).

**Code:** `phases/backend/phase-09-comparison-recommendations/`

**Outcome:** `/chat` can return `recommendation` plus evidence for two destinations (e.g. Delhi vs Mumbai). Comparison/research layout is Phase 12; no booking.

---



## Phase 10 — RAG evaluation

**Goal:** Judge the system by retrieval quality and faithfulness, not by fluent-sounding prose.

**Description:** Build ~30–50 questions across journeys A–J, stratified across India, plus multi-turn and known-absent cases (e.g. Kyoto when Japan is not in corpus). Measure retrieval@k, faithfulness, citation correctness (`source_url` match), unsupported-claim rate, and p95 latency. Compare chunking, hybrid, and rerank choices. Unit/integration tests use fixture wikitext — not live Wikimedia in CI.

**Implemented:** Fixtures under `phases/backend/phase-10-rag-evaluation/`; report at [docs/eval/REPORT.md](eval/REPORT.md). Offline routing/refusal coverage in pytest. Live faithfulness/latency remains manual via `TRIPWISE_RUN_INTEGRATION=1`.

**Code:** `phases/backend/phase-10-rag-evaluation/`

**Outcome:** Eval report in `docs/eval/` vs Phase 5 baseline; at least one backend improvement is compared to baseline.

---



## Phase 11 — Frontend: baseline chat UI

**Goal:** Put a real chat interface on the Phase 5+ API, separate from backend phases.

**Description:** Next.js + Tailwind chat thread (fonts: Fraunces + Source Sans 3; trail/skyline CSS tokens). Brand: **TripWise** (sidebar wordmark + document title “TripWise: Travel Research Chat”). Layout is a **viewport-locked** shell (`h-dvh overflow-hidden`): left **TripSidebar** (~280px)  center **scrollable thread + fixed composer**  right **RightRail** (~280px on `lg+`). User sends a message; the assistant reply renders as Markdown (tables for lists) with **Copy / Share** icons below it. Clickable Wikivoyage `source_url`s appear in the right-hand **Next stop** panel (**Sources** + **Ask next**) **and** as an inline Sources block under assistant bubbles. The API still returns `evidence[]` but the UI does not display raw evidence rows. Follow-ups reuse `conversation_id`; trips are stored in `localStorage`. Empty state: “Where are you headed?” with Wikivoyage-grounded supporting copy. Composer: bottom bar without a heavy top divider; Enter sends; placeholder about destinations / food / transit. **Jump to latest** control appears when the user scrolls up in the thread (ChatGPT-style centered affordance). Theme toggle supported. API base: `NEXT_PUBLIC_TRIPWISE_API_URL` (default `http://127.0.0.1:8000`).

**Run:** from repo root `npm run dev` (delegates to `phases/frontend/phase-11-chat-ui`).

**Code:** `phases/frontend/phase-11-chat-ui/`

**Outcome:** Browser completes journeys A–G and a basic follow-up; citations are clickable; empty and error states work; chrome stays frozen while only the thread scrolls. No destination-card product work required in this phase (cards appear via Phase 12 imports).

---



## Phase 12 — Frontend: travel-research UI

**Goal:** Make the chat feel like travel research, not a generic chatbot clone.

**Description:** Same `/chat` API. Richer UI modules live under `phases/frontend/phase-12-research-ui` and are imported into the Phase 11 app as `@research/`*: Recommendation / Trade-offs, suggested follow-ups, optional destination or attraction cards, comparison-oriented presentation. Chat thread stays primary; citations always visible.

**Code:** `phases/frontend/phase-12-research-ui/` (consumed by Phase 11)

**Outcome:** Journeys A–J completable in the UI. No new backend retrieval, accounts, or maps-as-product.

---



## Phase 13 — Deployment planning / local runtime

**Goal:** Document how to run `db` + `api` + `scheduler` + frontend **locally** — without Docker or Kubernetes cloud hosting.

**Description:** Capture local runtime notes in [docs/LOCAL_RUNTIME.md](LOCAL_RUNTIME.md) and the root README. Stack today: PostgreSQL + Phase CLIs; Phase 5 via uvicorn (`main.py`); Phase 4 via `serve` (APScheduler) or OS cron/`launchd` calling `tick`. Explicitly **no Docker/Compose** and no Kubernetes.

**Optional managed Postgres (Supabase):** Point only `DATABASE_URL` at a Supabase Postgres URI (prefer **Session/Transaction pooler**, port **6543**, append `?sslmode=require`). Direct `db.<ref>.supabase.co:5432` may be **IPv6-only** and fail on IPv4-only networks — use the pooler host (`aws-0-<region>.pooler.supabase.com`) with user `postgres.<project_ref>`. In the Supabase SQL editor: `CREATE EXTENSION IF NOT EXISTS vector;` then run existing `run_phase3.py init-db` + `embed`. **Do not** put the `https://….supabase.co` API URL or publishable/anon keys into `DATABASE_URL`. Local bge embeddings are computed on that machine and **written into Supabase pgvector** — Supabase is the store, not the embedding provider.

**Optional Vercel (UI + chat API):** Root [`vercel.json`](../vercel.json) builds Phase 11 Next.js and Python functions [`api/chat.py`](../api/chat.py) / [`api/health.py`](../api/health.py). Routes `/chat` and `/health` map to those functions. On Vercel, embeddings are **forced to Gemini** (no ONNX in the serverless bundle) — re-embed Supabase with `TRIPWISE_EMBEDDING_PROVIDER=gemini` before production chat. Ingest, Go, and Phase 4 stay local. Conversation slots remain process-local (may reset on cold start).

**Optional Go ingest:** See section above; documented in LOCAL_RUNTIME.

**Outcome:** Local runtime documentation is accurate. No containers or K8s hosting implemented. Managed Postgres is DB-only.

---



## Cross-cutting rules (all implementation phases)

- **Chat LLM = Groq.** Do not treat the model as a knowledge base.
- **Retrieve from embeddings (pgvector), then generate.** Empty or irrelevant retrieval → “I don’t know.” Never invent travel facts.
- **Refuse personal information** about the user or others (IDs, financial, medical, private contact, “what is my …”). Out of scope for TripWise.
- **Cite** `source_url` **from retriever metadata only** — never invent URLs.
- Separate **source facts**, **AI synthesis**, and **AI recommendation** (synthesis/recommendation only over retrieved evidence).
- Secrets in `config/.env`. Never commit them. Phase 3 default (`local`) needs no Gemini key; Phase 5 needs `GROQ_API_KEY` (chat). `GEMINI_API_KEY` is only required when `TRIPWISE_EMBEDDING_PROVIDER=gemini`.
- Wikivoyage text is CC BY-SA 4.0; attribute via revision/history links. No image ingest in MVP.
- Structured JSON logs (`run_id` / `request_id`, operation, status). Do not log secrets or raw user PII.
- Country-agnostic domain model; v1 focus = India.
- **Do not confuse env knobs:** `TRIPWISE_BATCH_SIZE` (Python ingest batch / Go worker default) ≠ `TRIPWISE_EMBED_BATCH_SIZE` (texts per embed call).

---



## Logging, errors, security


| Failure                              | Behavior                                                                        |
| ------------------------------------ | ------------------------------------------------------------------------------- |
| Wikimedia timeout / 429              | backoff; fail the page or stage                                                 |
| Parse / unknown template             | skip + WARNING/ERROR                                                            |
| Embedding / LLM failure              | no empty vectors; generic 5xx to the user                                       |
| Gemini embed RPM 429                 | Gemini path only: sleep / retry (`call_with_quota_retry`)                        |
| Gemini embed daily free-tier 429     | Gemini path: pause embed as `PARTIAL`; `/chat` does not probe, so local provider stays up |
| Local ONNX model missing             | Fail embed/API with install hint (`pip install -r requirements.txt`)             |
| Overlapping scheduler tick           | skip + WARNING                                                                  |
| Supabase DNS / IPv6-only direct host | use pooler URI + `sslmode=require`                                              |


---



## Risks


| Risk                              | Mitigation                                                                                    |
| --------------------------------- | --------------------------------------------------------------------------------------------- |
| Hallucinated travel facts         | Retrieve from embeddings only; refuse on empty context; Groq sees retrieved chunks only       |
| LLM answering without retrieval   | Hard gate: no generation call unless retrieval returned usable chunks (except scope refusals) |
| Personal information requests     | Route as `personal_info` / out_of_scope; fixed refusal; do not retrieve or invent PII         |
| Fake citations                    | Citation IDs / `source_url` from retriever only                                               |
| Huge-city listings on parent page | Expand to district children                                                                   |
| Thin Outline articles             | Ingest as missing; do not invent                                                              |
| Stale visas/prices                | Phase 4 scheduler + hedge in prompt                                                           |
| Groq outage / quota               | Fail the turn with a clear error; do not invent answers without retrieval                     |
| Gemini free-tier embed quota      | Default is local bge (no quota). Gemini fallback: batch requests; PARTIAL resume |
| Scheduler overlap                 | `ingestion_runs` lock; abort without corrupting last good index                               |
| CC BY-SA                          | Revision links; no image ingest                                                               |
| Scope creep                       | India ancestry filter; no worldwide dump; no Celery                                           |
| Supabase connectivity             | Prefer pooler + SSL; never use https API host as `DATABASE_URL`                               |


---



## Tests & quality

```bash
pytest -m 'not integration' -q
```

- `pytest.ini` collects `tests/project` and `phases/backend/phase-*/tests`
- Integration tests require `TRIPWISE_RUN_INTEGRATION=1` (live embeddings/Groq/DB)
- Project entrypoint smoke: `tests/project/`
- Eval fixtures / report: [docs/eval/REPORT.md](eval/REPORT.md)

---



## Implementation status

**Done:** Phase 1 ingest + JSON artifacts; Phase 2 India scale pipeline (API + optional dump); optional **Go ingest** → `data/`*; Phase 3 embeddings → pgvector with **local bge default** (`BAAI/bge-base-en-v1.5`, 768-d), Gemini optional fallback, hash skip, batch embed, and Gemini free-tier **PARTIAL** pause; Phase 4 local scheduler (`tick` / `serve`); Phase 5 FastAPI `POST /chat` (uvicorn via `main.py`, Groq) with hard cosine relevance gate (recalibrate after model switch via `calibrate-gate`); Phase 6 heuristic routing; Phase 7 hybrid (vector + lexical RRF, rerank off); Phase 8 in-process conversation slots (lost on restart; UI `conversation_id` in localStorage); Phase 9 comparison / recommendation fields; Phase 10 offline eval (routing/refusal) + report; Phases 11–12 Next.js UI (frozen chrome, jump-to-latest, Sources rail + inline sources, research panels); Phase 13 local runtime docs with **optional Supabase** `DATABASE_URL`.

**Current corpus (on disk, approximate):** ~**487** page JSON files under `data/raw|structured|chunks`, ~**11,000** chunk records — still a **partial** India tree vs the full ~1,000+ destination target. Raise `TRIPWISE_MAX_PAGES` (or run uncapped ingest / Go ingest), then re-run `embed` (hash skip resumes; local provider has no daily cap).

**Known limits:** router entity list is a small hard-coded India set (`KNOWN_DESTINATIONS`; unknown places fall through to unfiltered search + the relevance gate → "I don't know"); Phase 7 lexical pass is token/ILIKE matching, not a real BM25/tsvector index; live faithfulness/latency eval is manual (`TRIPWISE_RUN_INTEGRATION=1`); Gemini fallback still has free-tier ~1000 embed **requests**/day (local bge does not; `/chat` does not probe Gemini); Go ingest lacks full wikitext/parser parity and does not upsert Phase 1 Postgres page tables; Phase 5 turn assembly returns `trade_offs=[]` even though Phase 9 `compare.py` models trade-offs; Phase 8 has no `last_listing_ids` and memory is process-local.