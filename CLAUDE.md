# CLAUDE.md

AYO Plant Copilot: an AI agent that guides industrial plant teams through structured
problem solving. This repo holds the FastAPI service and the knowledge ingestion
pipeline (RAG): Markdown upload -> chunks -> Voyage embeddings -> Postgres + pgvector.

**Keep this file up to date.** When a step changes commands, layout, conventions or
working rules, update this file in that step's commit.

## Where things stand

- **Active milestone: documents CRUD.** Spec `plans/claude-code-prompt-documents-crud.md`;
  plan, agreed deviations and progress log in `plans/crud-progress.md`. **Read it first**;
  resume from the first unchecked item, and check "Open items".
- Done: the ingestion slice. Spec `plans/claude-code-prompt-markdown-ingestion.md`; its
  decisions and log in `plans/progress.md` (still the reference for earlier decisions).
- Both spec files are intentionally **untracked**; never commit them.
- Decision records: `docs/decisions/`.

## How we work (user's rules)

- **Baby steps.** One small step at a time. Before starting a step, write a short brief:
  what it delivers, files, design choices and deviations, tests. Wait for approval.
- Keep `README.md` current: any step that adds or changes an endpoint, a setting or a
  command updates it in the same commit.
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
uv run python scripts/export_openapi.py   # regenerate docs/openapi.json (--check: verify only)
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
  app.py               create_app(settings=None, *, docs_enabled=None), API description/tags,
                       lifespan: pool, embedder, DB_LOG_LEVEL, dimension check
  errors.py            ApiError + handlers: every error is {"detail": [{type, loc, msg}]}
  schemas.py           IngestResponse, Document, Chunk, DocumentUpdate, Page[T] -> *Page, errors
  dependencies.py      get_settings / get_pool / get_embedder (from request.state)
  routers/admin.py     /admin: upload, list, get, content, chunks, rename, reprocess (provisional X-API-Key auth, size limits)
  documents.py         admin read/write operations on stored documents (own transactions)
  openapi.py           render_openapi() for the committed contract docs/openapi.json
  config.py            DatabaseSettings (Alembic), DocsSettings (app build) < Settings
  db/pool.py           open_pool (register_vector per connection), set_db_log_level
  db/repository.py     hand-written SQL: upsert_document, replace_chunks, similar_chunks, ...
  ingestion/chunking.py    normalize_markdown, chunk_markdown (header + recursive splitters, small-chunk policy)
  ingestion/signatures.py  content/chunk/embed signatures, make_doc_id, CHUNKER_VERSION
  ingestion/embedding.py   Embedder protocol, VoyageEmbedder (httpx2), FakeEmbedder
  ingestion/storage.py     tenant and source_key validation (name is historical)
  ingestion/service.py     the pipeline: ingest_document, reprocess_document and their stages
migrations/            Alembic; 0001 = documents + chunks (vector(1024), HNSW cosine)
                       0002 = documents.chunk_count/size_bytes/*_config + list index
scripts/               dev_db.sh, export_openapi.py
docs/                  openapi.json (generated, committed), decisions/
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
- Settings tests pass `_env_file=None` (or a tmp file) so they never read the real `.env`.
  `.env` is read from the project root whatever the cwd (`AYO_ENV_FILE` overrides it);
  empty values count as unset.
- Errors: raise `ApiError(status, type, msg, loc)` in routers; never `HTTPException` with a
  string detail. Service validation raises `InvalidInputError(msg, field=..., code=...)`.
- OpenAPI is part of the product: every endpoint has summary, description, tags,
  `operation_id` and every status in `responses` with examples; every schema field has a
  description (`tests/api/test_openapi.py` enforces it). **Never put `null` in an
  object-level example** (FastAPI drops it: `exclude_none` in `get_openapi`): a model with
  nullable fields gets examples per field only, and Swagger builds the sample from them.
  Every example must validate against its schema (tested, strictly). After any API change, re-export
  `docs/openapi.json` and commit it in the same commit (a snapshot test fails otherwise);
  every documented status must be triggered for real in `tests/api/test_contract.py`. Tests build the app with
  `create_app(docs_enabled=True)` so they never read `.env`.
- `{doc_id}` path parameters use `DOC_ID_PATTERN` (malformed -> 422, unknown -> 404
  `document_not_found`). Every `/admin` route needs the key: `tests/api/test_admin_auth.py`
  enumerates them from the OpenAPI document, so never hide an `/admin` route from it.
- Integration tests (`tests/integration/`, `tests/api/`; fixtures in `tests/conftest.py`)
  use the `db_pool` fixture (tables truncated before each test) or `scratch_database_url`
  (a throwaway database) for migration-level tests.
