# CLAUDE.md

AYO Plant Copilot: an AI agent that guides industrial plant teams through structured
problem solving. This repo holds the FastAPI service and the knowledge ingestion
pipeline (RAG): Markdown upload -> chunks -> Voyage embeddings -> Postgres + pgvector.

**Keep this file up to date.** When a step changes commands, layout, conventions or
working rules, update this file in that step's commit.

## Where things stand

- Spec: `plans/claude-code-prompt-markdown-ingestion.md` (intentionally **untracked**; never commit it).
- Plan, agreed deviations from the spec, and the progress log: `plans/progress.md`.
  **Read it first**; resume from the first unchecked item, and check "Open items".
- Decision records: `docs/decisions/`.

## How we work (user's rules)

- **Baby steps.** One small step at a time. Before starting a step, write a short brief:
  what it delivers, files, design choices and deviations, tests. Wait for approval.
- After the step: update `plans/progress.md`, make **exactly one commit** (code + tests
  + log together), summarise what changed and what to check, then **stop** for review.
  Never chain steps, even when told to "continue".
- **Push only when the user asks**, and never force-push.
- Tell the user before deviating from the spec; record agreed deviations under
  "Decisions" in `plans/progress.md`.
- Commit messages end with the `Co-Authored-By` line given by the harness.

## Safety rules

- **Neon = production.** Tests never touch it. Manual runs may use the Neon **dev
  branch** only. Anything destructive on a remote database (downgrades, drops) needs the
  user's explicit OK first, after checking what is there.
- Secrets live only in the gitignored `.env` (also ignored: `ayodb.connect`, `voyage.ai`).
  Never print, log, commit or paste them into the chat. Show URLs with the password
  redacted (`sed -E 's#://[^@]*@#://***@#g'`) or print only the host.
- Never log document content (customer data) or API keys. Logs carry `doc_id`, tenant,
  counts and durations.

## Commands

```sh
uv sync                                   # install
uv run pytest                             # unit + API + integration (testcontainers); `live` deselected
uv run pytest -m "not integration"        # no Docker, no database
uv run pytest -m live                     # one real Voyage call (needs VOYAGE_API_KEY)
uv run ruff check . && uv run ruff format --check .
scripts/dev_db.sh up|down                 # local dev DB: pgvector/pgvector:0.8.7-pg18-trixie on localhost:5433
uv run alembic upgrade head               # migrations (uses MIGRATIONS_DATABASE_URL, else DATABASE_URL)
uv run ayo-copilot                        # run the API on 127.0.0.1:8000
```

Integration tests start a Postgres container (Docker daemon required; no Compose here)
and are skipped with a clear message without Docker. `TEST_DATABASE_URL` overrides the
container; Neon URLs are refused.

`.env` currently points `DATABASE_URL` at the Neon dev branch (pooled endpoint) with
`ALLOW_REMOTE_DATABASE=true`. For the local DB, override in the shell:
`DATABASE_URL=postgresql://ayo:ayo@localhost:5433/ayo ALLOW_REMOTE_DATABASE=false uv run ...`.
Migrations on Neon must use the direct endpoint (host without `-pooler`).

## Layout

```
src/ayo_copilot/
  __init__.py          main(): logging.basicConfig + uvicorn (factory=True)
  app.py               create_app(settings=None), lifespan: pool, DB_LOG_LEVEL, dimension check
  config.py            DatabaseSettings (DB only, used by Alembic) < Settings (pydantic-settings)
  db/pool.py           open_pool (register_vector per connection), set_db_log_level
  db/repository.py     hand-written SQL: upsert_document, replace_chunks, similar_chunks, ...
  ingestion/chunking.py    normalize_markdown, chunk_markdown (header + recursive splitters, small-chunk policy)
  ingestion/signatures.py  content/chunk/embed signatures, make_doc_id, CHUNKER_VERSION
  ingestion/embedding.py   Embedder protocol, VoyageEmbedder (httpx2), FakeEmbedder
  ingestion/storage.py     tenant and source_key validation (name is historical)
  ingestion/service.py     the pipeline: ingest_document and its stages
migrations/            Alembic; 0001 = documents + chunks (vector(1024), HNSW cosine)
tests/{unit,api,integration,live}/, tests/fixtures/ (Spanish Markdown)
```

## Conventions

- Python 3.12, uv, ruff (line length 100). Type annotations on new code. English for
  code, comments, logs and API messages; test fixtures use realistic Spanish text.
- psycopg 3 + psycopg_pool + pgvector, hand-written SQL, **no ORM** (SQLAlchemy is only
  there because Alembic needs it).
- Repository functions take a connection and never commit; the service owns transactions.
  The embedding provider is called outside any transaction.
- HTTP client is `httpx2` (pydantic's fork), not `httpx`; tests mock it with `MockTransport`.
- Changing chunking behaviour or the embedded text format: bump `CHUNKER_VERSION`.
  Changing the vector size needs a new migration (startup checks it).
- Settings tests pass `_env_file=None` so they never read the real `.env`.
- Integration tests use the `db_pool` fixture (tables truncated before each test) or
  `scratch_database_url` (a throwaway database) for migration-level tests.
