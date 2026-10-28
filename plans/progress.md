# Ingestion slice: plan and progress

Spec: `plans/claude-code-prompt-markdown-ingestion.md`. This file holds the agreed deviations and the progress log; resume from the first unchecked item under "Next".

## Decisions from Q&A (these override the spec)
- **Naming:** rename the package to `ayo_copilot`, `bootstrap.py` to `app.py` and `create_agent()` to `create_app()`. Update `[project.scripts]` and `main()` (which keeps `factory=True`) to match. The existing `/health` route stays.
- **Test DB:** testcontainers is the leading candidate. It only needs the Docker daemon, which is running here (Compose is not installed). Step 0 still compares all six options in `docs/decisions/0001-test-database.md` and waits for your approval. For the dev DB used for manual runs, a scripted `docker run pgvector/pgvector:<pg-version>` (as `make`/`scripts` commands) replaces Compose.
- **Neon = production.** No test command ever touches it, and the production branch is never used for dev runs.
  - Amended 2026-10-22 (step 5x): local manual runs may use a Neon **`dev` branch**. One gitignored `.env` holds the real `VOYAGE_API_KEY` and the Neon dev-branch URL; there is no separate env file. Tests never read `.env`.
- **Embeddings: hosted Voyage AI, as the original spec says.** `VoyageEmbedder` is a thin httpx client (`input_type="document"`), sitting behind the `Embedder` protocol alongside `FakeEmbedder` for tests.
  - Before writing the client, check the official Voyage docs for the current model names, output dimensions, per-request limits and request shape. The working assumption is `voyage-4` at 1024 dims.
  - The API key goes only into the gitignored `.env` as `VOYAGE_API_KEY`. It never goes into any committed file, log or test fixture, and `.env.example` holds a placeholder.
  - The `live` test does one real upload against Voyage and is skipped when there's no key.

- **Markdown stored in Postgres, not on disk (2026-10-27, deviation from the spec):** `documents.markdown text not null` replaces `markdown_path`, and is written in the same transaction as the chunks. Reasons: one store, so the database and the file can never disagree; it survives container deployments (Neon keeps it). `KNOWLEDGE_DIR` and the atomic file write are removed. The original is still kept, because chunks can't rebuild it and reprocessing after a chunker or model change needs it.
- **Zero-chunk uploads are rejected (2026-10-27):** a file that is valid UTF-8 and not empty but produces no chunks (only headings, separators, page numbers) gets `InvalidInputError` -> `422` "no indexable content", like an empty file. Implemented in 6b.
- **One error format, FastAPI's validation-error shape (2026-10-28, the spec defines none):** every error body is `{"detail": [{"type", "loc", "msg"}]}`, so callers parse one shape and branch on `type`. Ours never carry `input` (no content echoed back); FastAPI's own 422s keep it. Codes: `invalid_api_key` (401, `["header","x-api-key"]`), `file_too_large` (413), `file_extension`/`file_encoding`/`file_empty`/`file_no_content` (422, `["body","file"]`), `tenant_invalid`, `source_key_invalid` (422, the field; `["body","file"]` when source_key came from the file name), `embedding_failed` (502, `[]`). Starlette's HTTP errors map to the status phrase (`bad_request`, `not_found`, `method_not_allowed`), unhandled exceptions to a JSON 500 `internal_error`.

## Repo findings to report
- **Security:** `ayodb.connect`, which holds the Neon (now production) connection string with its password, was committed in `2799800` and **pushed to origin/main**. Deleting it in `d48b9bd` doesn't remove it from history. Rotate the Neon password. Rewriting history is your call; I won't do it.
- The Voyage key was pasted into the chat, so it is now in this session's transcript. Rotate it if that matters to you.

## Order of work (small commits, no push)
0. Step 0: research the DB options (current versions), write the ADR, **stop for approval**.
1. Rename the package. Add tooling: dependencies (psycopg[binary,pool], pgvector, pydantic-settings, langchain-text-splitters, httpx, alembic, python-multipart, testcontainers[postgres] for dev, pytest, ruff, openapi-spec-validator), pytest markers, ruff config, `.env.example`, `.env` in `.gitignore`.
2. `config.py`, `ingestion/signatures.py` and `ingestion/storage.py` validation, test-first.
3. `ingestion/chunking.py`, test-first, with Spanish fixtures and merging of heading-only chunks.
4. `ingestion/embedding.py`: `VoyageEmbedder` and `FakeEmbedder`, tested with `httpx.MockTransport`.
5. Alembic migration (`vector(1024)`, HNSW cosine index), `db/pool.py` and `db/repository.py` (`similar_chunks`), plus integration tests.
   - 5x. Local runs against real services: the single `.env` holds `VOYAGE_API_KEY`, `DATABASE_URL` (Neon dev branch, pooled endpoint, `sslmode=require`), `MIGRATIONS_DATABASE_URL` (direct endpoint, for Alembic) and `ALLOW_REMOTE_DATABASE=true`. Settings guard: a non-localhost `DATABASE_URL` is refused unless `ALLOW_REMOTE_DATABASE=true`. To use the local Docker DB instead, override `DATABASE_URL` in the shell (environment variables win over `.env`). `.env.example` documents both setups. Prerequisite: rotate the Neon password, or use a new role for the dev branch.
6. `ingestion/service.py`, `schemas.py`, `routers/admin.py` and the lifespan (pool plus a dimension check against the DB). API and OpenAPI tests, `scripts/export_openapi.py` and `docs/openapi.json`.
7. README, a manual run (FakeEmbedder, then real Voyage) and the final report.

## Verification
- `uv run pytest`: unit and API tests run with no DB or network; integration tests use testcontainers, or are skipped with a clear message if Docker is missing.
- `uv run ruff check .` and `uv run ruff format --check .`.
- Migrations apply from scratch with one command.
- Manual upload through Swagger UI (Authorize, then Try it out) and with `curl`.

## Progress log (update after every small step; resume from the first unchecked item)
Working rule: baby steps. One small step, update this log, then STOP and wait for the user to review and approve before starting the next step. Exactly one commit per step (code + tests + this log together; no separate log-only commits).

### Done
- [x] Spec read; repo, tools and git history inspected (Docker 29.7.2 with daemon running, no Compose; local PG 18.6 without pgvector; Python 3.12.0; uv 0.13.1).
- [x] Q&A resolved (see Decisions above).
- [x] `.gitignore`: added `.env` and `voyage.ai` (uncommitted change). `.env` created (mode 600) with `VOYAGE_API_KEY`.
- [x] Step 0 research, versions checked on 2026-10-22:
  - pgvector 0.8.7; Docker image `pgvector/pgvector:pg18-trixie` (also `0.8.7-pg18-trixie`), updated 2026-10-01.
  - testcontainers 4.15.0 (2026-07-24).
  - pytest-postgresql 9.1.1 (2026-10-04); needs local PG binaries plus pgvector.
  - pgserver 0.1.4 (2024-06-08); repo inactive since 2024-06. Looks unmaintained.
  - sqlite-vec 0.1.9 (2026-03-31), pre-v1. Vectors live in `vec0` virtual tables; experimental IVF/DiskANN/rescore ANN indexes added via recent PRs (#273-#278), no HNSW. No `vector` type, no `<=>`, no row locking (`FOR UPDATE SKIP LOCKED`). Not viable.
  - Neon free plan: 10 branches/project, 100 CU-h/month, 0.5 GB, scale-to-zero after 5 min.
  - pgvector (Python) 0.5.1, psycopg 3.3.6.

### Next
- [x] 0a. sqlite-vec index support checked (see above).
- [-] 0b. Skipped: did not check the Manjaro pgvector package (command was rejected); recorded as unverified in the ADR.
- [x] 0c. `docs/decisions/0001-test-database.md` written (status: proposed). Recommends testcontainers + `scripts/dev_db.sh` (docker run, port 5433), truncation per test, `TEST_DATABASE_URL` escape hatch with a Neon guard.
- [x] 0d. ADR 0001 approved on 2026-10-22: testcontainers, Postgres 18 (`pgvector/pgvector:0.8.7-pg18-trixie`).
- [x] H1. `ayodb.connect` removed from local `main` history via filter-branch (new root 761207f, head 5235df5). Old commits still kept locally in `backup/pre-secret-removal`, `refs/original/` and the reflog; purge them after the push.
- [x] H2. Force-pushed with the user's confirmation (origin/main d48b9bd -> ed02094). Local backup, refs/original and reflog purged; old commit 2799800 gone locally. It may still be reachable on GitHub by SHA until GitHub support purges cached views.
- [x] 1a. Renamed: project `ayo-copilot`, package `src/ayo_copilot`, `app.py` with `create_app()`, script `ayo-copilot`. App builds, `/health` route present.
- [x] 1b. Dev tooling: dev group (pytest 9.1.1, ruff 0.17.1, httpx2 2.16), markers `integration`/`live` (`live` deselected by default), ruff config (`*.md` excluded, because ruff formats Python blocks inside Markdown), `tests/api/test_health.py` passing. Existing code ruff-formatted.
  - Note: Starlette 1.9's TestClient needs `httpx2` (pydantic/httpx2, declared in Starlette's `full` extra), not `httpx`. In step 4, decide whether the Voyage client uses `httpx2` too; tell the user, since the spec says `httpx`.
- [x] 1c. `config.py` (pydantic-settings 2.16.1) + 8 unit tests, `.env.example`, `data/` ignored. Voyage key required when `EMBEDDING_PROVIDER=voyage`; `fake` provider for tests; dims capped at 2000 (HNSW). Tests use `_env_file=None` so they never read the real `.env`. Embedding batch, timeout and retry defaults are placeholders until step 4 checks the Voyage docs. Other runtime deps are added in the step that needs them.
- [x] 2a. `ingestion/signatures.py` (sig, content_hash, chunker/embedder descriptors, chunk/embed signature, make_doc_id) and `normalize_markdown` in `ingestion/chunking.py`; 11 unit tests.
  - Deviation to report: the CHUNKER descriptor also includes `min=<CHUNK_MIN_SIZE>` (`md-header+recursive@v1/size=800/overlap=80/min=50/breadcrumb=1`), because the minimum size changes the chunks.
  - Normalization also converts lone `\r` to `\n`.
- [x] 2b. `ingestion/storage.py`: `InvalidInputError`, `validate_tenant` (fullmatch), `normalize_source_key` (NFC, rejects control chars, keeps only the last `/` or `\\` component, rejects empty/`.`/`..`, max 255 chars); 38 tests including traversal inputs. Behaviour: `../../etc/passwd` becomes `passwd` (accepted, as "file name only"), while `..` is rejected.
- [x] 2c. `markdown_path` (validates tenant and the `upload-<12 hex>` doc_id, resolved path must stay under `knowledge_dir`) and `write_markdown_atomic` (mkstemp in the same dir, fsync, `os.replace`, temp file removed on failure); 7 tests including a failed rename that keeps the previous file. When to write relative to the DB commit is decided in step 6 (service).
- [x] 3a+3b (one commit, as agreed). Chunker per the **updated small-chunk requirements** (they supersede the spec's "merge or drop" line):
  - `split_markdown` is library only (MarkdownHeaderTextSplitter h1-h3 with `strip_headers=True`, then RecursiveCharacterTextSplitter with `add_start_index=True`). It is our code only in that `"  \n"` (how the header splitter renders blank lines) becomes `"\n\n"` again, so paragraph breaks are restored.
  - `apply_small_chunk_policy(pieces, min_size, max_merged)` is our own merge step on the library output: (1) drop if `has_content` is false (blank, separators, page number), (2) merge forward if the next piece is the same section or a subsection, (3) else merge backward into the same section if the result is within 1.5x `CHUNK_SIZE`, (4) else keep. The merged piece takes the receiver's heading path. Pieces of one section are joined by offsets, so the overlap isn't repeated; others are joined with `"\n\n"`.
  - Setting renamed `chunk_min_size` -> `MIN_CHUNK_SIZE`, default 100. The CHUNKER signature bumped to `md-header+recursive@v2/size=../overlap=../min=../merge=fwd,back1.5x,keep/breadcrumb=1`.
  - README: configuration table + chunking rules. `.env.example` updated.
  - Tests: 61 in `test_chunking.py` (end to end and the merge step alone, plus the invariants: every body line in some chunk, every heading in some path, all words in order when overlap=0). 126 tests in total.
- [x] 4a. Voyage docs checked on 2026-10-22 (research only, no code; this log edit goes into the 4b commit):
  - `POST {base}/embeddings`, `Authorization: Bearer`, body `input` (list, at most 1000 items), `model`, `input_type` (`document`/`query`/null), `truncation` (default true), `output_dimension` (256/512/1024/2048, default 1024), `output_dtype` (default `float`), `encoding_format` (null/`base64`). Response: `data[].embedding` and `data[].index`, plus `usage.total_tokens`; errors carry `detail`.
  - `voyage-4`: 32K-token context, 1024 dims by default, 320K total tokens per request. Tier 1: 8M TPM / 2000 RPM. Working assumption confirmed.
  - Errors: retry 429 and 500/502/503/504 with exponential backoff and jitter (Voyage suggests about 128 docs per batch). Fail fast on 400/401/403.
  - httpx 0.28.1 (last release 2024-12) is only a transitive dependency through langchain-core. httpx2 2.16.0 (pydantic fork, released 2026-10-21) is already in the dev group for TestClient. Proposal approved 2026-10-22: httpx2, not the spec's `httpx` (deviation to report).
- [x] 4b. `ingestion/embedding.py` (sync; the service is sync too, decide again in step 6 if needed):
  - `Embedder` protocol (`embed_documents`), `EmbeddingError` (message holds only the HTTP status or the error class; never the key, the texts or the response body; nothing chained), `build_embedder(settings)`.
  - `FakeEmbedder`: unit vectors from SHA-256 of the text, records `calls` (empty input is not a call).
  - `VoyageEmbedder`: httpx2 client (`client=` and `sleep=` injectable), `input_type=document`, explicit `output_dimension`, `output_dtype=float`, `truncation=false`, batches of `EMBEDDING_BATCH_SIZE`. Retries 429/500/502/503/504, timeouts and connection errors with full-jitter backoff (at most 1, 2, 4 s ...); other 4xx fail at once. Checks the response count, the indexes and the dimensions. No token-based batch splitting: 128 chunks of about 800 chars is far below 320K tokens.
  - `httpx2` moved from dev to runtime deps. `EMBEDDING_BATCH_SIZE` capped at 1000 (Voyage limit). README rows updated.
  - Tests: 34 in `test_embedding.py` + 1 config test; `tests/live/test_voyage_live.py` (reads the key from env or `.env`, skipped without one) **ran once and passed** against real Voyage (2 texts, 1024 dims). 160 tests by default, 1 deselected.
- [x] 5a. Alembic + initial migration + migration integration tests:
  - Deps: `psycopg[binary]` 3.3.6 and `alembic` 1.20.1 (pulls in SQLAlchemy 2.1.6; Alembic needs it, and the app itself stays on hand-written psycopg SQL). Dev: `testcontainers[postgres]` 4.15.0, imported from `testcontainers.community.postgres` (the old path is deprecated).
  - `config.py`: new `DatabaseSettings` base (only `database_url`), which `Settings` extends, so Alembic needs no admin key.
  - `alembic.ini` (no URL in it), `migrations/env.py` (URL from `Config.attributes` in tests, else `DATABASE_URL`; rewritten to `postgresql+psycopg://`; online mode only), `migrations/versions/0001_initial_schema.py` as hand-written SQL.
  - **Deviations from the spec schema, to report:** (1) no separate `documents (tenant)` index, because the `unique (tenant, source_type, source_key)` index already starts with `tenant`; (2) the HNSW index is named `chunks_embedding_hnsw_idx`; (3) `vector(1024)` is fixed in the migration (a dimension change needs a new migration; the lifespan check in step 6 catches a mismatch); (4) downgrade drops the tables but leaves the `vector` extension.
  - Tests: `tests/integration/conftest.py` (session server from `TEST_DATABASE_URL` or a testcontainer; skipped with a clear message without Docker; refuses Neon URLs), `scratch_database_url` (a fresh database per test, dropped with force). `tests/integration/support.py` (`is_neon_url`, `with_database`, `alembic_config`) and its 8 unit tests. 7 migration tests: schema from scratch (extension, tables, `vector(1024)`, HNSW cosine), downgrade then upgrade again, cascade, the 3 unique constraints, dimension enforced.
  - Verified: 175 passed (about 9 s warm, 47 s with the first image pull); with no Docker, 7 skipped with the message; a Neon `TEST_DATABASE_URL` is refused; `uv run alembic history` works.
- [x] 5b. Dev DB script, connection pool, shared test DB (brief given before starting, as now agreed for every step):
  - Deps: `psycopg[binary,pool]` (psycopg-pool 3.3.3) and `pgvector` 0.5.1 (no numpy needed; values come back as `pgvector.Vector`).
  - `scripts/dev_db.sh up|down`: container `ayo-dev-db`, same image as the tests, `127.0.0.1:5433`, user/password/db `ayo`, named volume `ayo-dev-db-data` mounted at `/var/lib/postgresql` (PG 18 layout). `up` creates, restarts or reports "already running", then waits up to 30 s for `pg_isready`; `down` only stops it. Checked by hand: up, up again, `alembic upgrade head`, down, up (revision `0001` still there), down twice, bad argument (exit 2).
  - `db/pool.py`: `open_pool(url, *, min_size=1, max_size=5, timeout=10)`, pool named `ayo`. Each connection runs `register_vector`, then commits, because psycopg_pool discards connections that `configure` leaves in a transaction. Waits for `min_size` connections, so a bad URL or a missing `vector` extension fails at startup (`PoolTimeout`). Pool sizes are arguments, not settings, for now.
  - **psycopg logging (user request):** psycopg already logs through `logging`: logger `psycopg` (connection attempts at DEBUG, host and port only; checked in the source) and its child `psycopg.pool` (pool events at INFO). psycopg sets it to WARNING. New setting `DB_LOG_LEVEL` (in `DatabaseSettings`, default `WARNING`) and `set_db_log_level()`. **Wiring is left for step 6:** the lifespan calls `set_db_log_level`, and `main()` needs a root handler (`logging.basicConfig`), otherwise INFO records go nowhere.
  - Fixtures: session `migrated_database_url` (`ayo_test_<random>`, `alembic upgrade head` once, dropped at the end), session pool, function `db_pool` (truncates `documents, chunks` first). Small ADR deviation (truncation in `db_pool`, not autouse), noted in the ADR.
  - Tests: 7 in `tests/integration/test_pool.py` (vector round trip as parameter and from `chunks`, two simultaneous connections both configured, fail fast without the extension, truncation shown by two tests inserting the same `doc_id`, DEBUG logs show the pool and connection attempts but never the password of a throwaway role), 1 unit test for `set_db_log_level`, 1 config test. 184 passed, 1 deselected; ruff clean.
- [x] 5c. `db/repository.py` (brief given and approved before starting):
  - Dataclasses `DocumentRecord`, `ChunkRecord` (index, heading, text, embedding, metadata), `SimilarChunk` (doc_id, chunk_index, heading, chunk_text, distance).
  - `upsert_document(conn, doc) -> UUID`: `ON CONFLICT (tenant, source_type, source_key)`, which updates title, path, hash, signatures, sets `chunked_at`/`embedded_at`/`updated_at` to `now()` and keeps `created_at`.
  - `replace_chunks(conn, document_id, chunks)`: delete, then `executemany` insert (embedding as `pgvector.Vector`, metadata as `Jsonb`). It must run after `upsert_document` in the same transaction, because that row lock serializes concurrent replacements of the same document.
  - `similar_chunks(conn, *, tenant, embedding, limit=5)`: cosine `<=>`, nearest first, joined to `documents` for the tenant filter.
  - No function commits; the caller owns the transaction. Building the `metadata` (doc_id, tenant) is left to the service (step 6).
  - **Noted for later (not done):** with HNSW and many tenants, the tenant filter is applied after the index scan and can return fewer than `limit` rows; a real search endpoint should enable pgvector's iterative scans (`hnsw.iterative_scan`). It's documented in the docstring.
  - **Left for step 6:** a lookup of the stored `embed_signature` for the `up_to_date` check (it wasn't in the 5c brief).
  - Tests: 8 in `tests/integration/test_repository.py` (insert, update of the same row keeping `created_at`, old chunks removed, heading/metadata/embedding stored, failure midway keeps the previous document and chunks, `similar_chunks` order and exact match first, tenant isolation, a concurrent second upload blocks on the row lock and then wins cleanly). 192 passed, 1 deselected; ruff clean.
- [x] 5x. Real services from the single `.env`:
  - `DatabaseSettings`: `MIGRATIONS_DATABASE_URL` (optional; `migrations_url()` falls back to `DATABASE_URL`, used by `migrations/env.py`) and `ALLOW_REMOTE_DATABASE` (default false; both URLs must point at localhost/127.0.0.1/::1 or a Unix socket otherwise; the error names the setting and host, never the password).
  - **Fixed an existing leak:** Pydantic validation errors echoed the raw input (`input_value={...}`), which could print a database URL with its password, or the admin key. Now `hide_input_in_errors=True`.
  - `.env.example` documents setup A (local Docker) and B (Neon dev branch: pooled URL for the app, direct URL for migrations, `sslmode=require`) and the one-command shell override. README rows added.
  - Tests: 10 new in `test_config.py`. 202 passed, 1 deselected; ruff clean.
  - **Manual check against the Neon dev branch on 2026-10-27** (the user filled `.env`; URLs never printed): Postgres 18.6, pgvector **0.8.6** available (tests use 0.8.7; patch-level difference). The database was empty. `alembic upgrade head` through the direct endpoint (the `-pooler` suffix removed in-process, since `.env` has no `MIGRATIONS_DATABASE_URL` yet) -> `0001 (head)`, HNSW index present. `open_pool` on the pooled endpoint: ready in 5.7 s (probably a scale-to-zero cold start). Prepared statements through PgBouncer work (12 repeats on one connection, and repeats across two), so `prepare_threshold=None` is **not** needed. upsert + replace_chunks + similar_chunks in a rolled-back transaction: exact match first, 0 rows left.
  - Not confirmed in the session: that the Neon password was rotated (role `ayodb_owner`) and that this endpoint is the dev branch, not production (the user was asked to use the dev branch).
- Step 6 split (agreed 2026-10-27): 6a lifespan and startup checks; 6b `ingestion/service.py` (pipeline, signatures, ordering, disk write); 6c `schemas.py` + `routers/admin.py` + API tests; 6d OpenAPI polish, `scripts/export_openapi.py`, `docs/openapi.json`, contract tests.
- [x] 6a. Lifespan and startup checks:
  - `create_app(settings=None)`: settings are read from the environment **at startup** (in the lifespan), not at `create_app()`, so the app can be built without any configuration (needed for `/health` and the OpenAPI tests). 6d may revisit this for `DOCS_ENABLED`.
  - Lifespan: applies `DB_LOG_LEVEL`, opens the pool (`POOL_OPEN_TIMEOUT_SECONDS = 30`, for Neon cold starts), checks the dimensions, yields `{"settings", "pool"}` (read through `request.state`), closes the pool on shutdown. `StartupError` messages: unreachable DB or no `vector` extension -> host + "check DATABASE_URL and that the migrations ran" (the exact cause is in the `psycopg.pool` WARNING log); no `chunks` table -> "run the migrations"; mismatch -> "chunks.embedding is vector(1024) but EMBEDDING_DIMENSIONS=512: add a migration or change the setting".
  - `repository.embedding_dimensions(conn)` reads `atttypmod` of `chunks.embedding` (None if the table is missing).
  - `main()`: `logging.basicConfig(level=INFO)`, so app and psycopg logs show next to uvicorn's.
  - `/health` unchanged; its test now runs without the lifespan (no DB).
  - Tests: 5 in `tests/integration/test_app_startup.py` (pool open/close and `/health`, dimension mismatch, no extension with the log cause, no table, log level applied). 207 passed, 1 deselected; ruff clean.
  - Manual: `uv run ayo-copilot` against the local dev DB with `DB_LOG_LEVEL=INFO` shows the pool events and "database ready at 'localhost', vector(1024)"; `/health` 200; `EMBEDDING_DIMENSIONS=512` exits with the clear message.
- [x] 6a.1. Markdown in Postgres instead of on disk (see Decisions):
  - Migration `0001` edited in place (only the Neon dev branch had it applied): `markdown text not null` instead of `markdown_path`.
  - `DocumentRecord.markdown`; the upsert writes and updates it.
  - Removed `markdown_path`, `write_markdown_atomic`, `DOC_ID_PATTERN` from `ingestion/storage.py` (it keeps tenant/source_key validation only; the name is now a little off, left as is) and `tests/unit/test_storage_write.py` (7 tests). Removed `KNOWLEDGE_DIR` from config, `.env.example`, README, ADR. `data/` stays in `.gitignore`.
  - Tests: migration test checks `markdown` is `text not null`; repository tests check it is updated by the upsert and unchanged after a failed transaction. 200 passed, 1 deselected; ruff clean.
- [x] 6b. `ingestion/service.py` (brief approved, minus the disk write after 6a.1):
  - Neon dev branch reset first, with the user's OK (both tables had 0 rows): `alembic downgrade base` + `upgrade head` through the direct endpoint -> `0001`, `markdown text not null`, HNSW index present.
  - Stages: `decode_markdown` (UTF-8 or `InvalidInputError`, normalized, blank -> "file is empty"), `chunk_document` (zero chunks -> "file has no indexable content"), `embedding_text` (`"{heading_path}\n\n{text}"`, just the text when there is no path), `embed_chunks`, `replace_document_chunks` (one transaction: upsert with the Markdown, then chunks; metadata `{doc_id, tenant}`; `heading` = heading path or NULL).
  - `ingest_document(...)`: validate tenant and source_key (default: the file name, last path component), decode, signatures; if not `force` and the stored `embed_signature` matches -> `up_to_date` (no chunking, no provider call, no write); else chunk, embed (outside any transaction), store. Returns `IngestResult(doc_id, status, chunk_count, embedding_model, embed_signature[:12])`. One INFO log line per upload: doc_id, tenant, status, chunks, ms (never content).
  - Title: given (trimmed) > first `# ` heading outside code fences > file name.
  - `repository.get_embed_signature(conn, doc_id)` (deferred from 5c).
  - **Chunker fix found by the zero-chunk rule:** `has_content` judged a whole piece, so `"---\n\n- 4 -"` (separator + page number) counted as content. Now a piece has content if any of its lines does. This changes chunker output, so `CHUNKER_VERSION` -> `md-header+recursive@v3`. Side effect: a piece made only of bare numbers on separate lines (e.g. `12\n13`) is now dropped too.
  - Tests: 16 unit (`tests/unit/test_service.py`), 3 new `has_content` cases, 19 integration (`tests/integration/test_ingestion_service.py`): indexed with exact embedder input and metadata, identical -> up_to_date with no provider call and no DB change, CRLF = no change, force, modified content, config changes (size/model/min) reprocess, provider failure (new doc: nothing; update: unchanged), failure inside the transaction keeps the previous version and the next upload heals it, two tenants, source_key from a Windows path, given title/source_key, invalid inputs touch neither the provider nor the DB, similarity finds an uploaded section. 239 passed, 1 deselected; ruff clean.
- [x] Housekeeping (2026-10-27): `CLAUDE.md` added (project summary, working and safety rules, commands, layout, conventions); keep it updated in each step's commit when something it describes changes.
- [x] 6c. `POST /admin/documents` (brief approved 2026-10-28 with the error format above):
  - `routers/admin.py`: sync `def`, multipart `file`, `tenant`, `title`, `source_key`, `force`. 201 indexed / 200 up_to_date / 401 / 413 / 422 / 502. Provisional auth: `APIKeyHeader("X-API-Key", auto_error=False)` on the router, `secrets.compare_digest` on bytes (non-ASCII keys get 401, not 500), `WWW-Authenticate: APIKey`.
  - 413 twice: `UploadLimitRoute` (custom `APIRoute`) rejects `Content-Length` > `MAX_UPLOAD_BYTES` + 64 KiB multipart allowance **before** FastAPI parses the body (a dependency can't: FastAPI parses the form first); the endpoint then reads at most `MAX_UPLOAD_BYTES`+1 bytes. Starlette still buffers what it receives: this protects processing, not bandwidth (a hard cap belongs in the proxy).
  - `errors.py`: `ApiError` + handlers for it, Starlette `HTTPException` and `Exception`. `schemas.py`: `IngestResponse`, `ErrorItem`, `ErrorResponse`. `dependencies.py`: `get_settings`/`get_pool`/`get_embedder` from `request.state`.
  - Lifespan builds the embedder (`build_embedder`) after the dimension check and closes it on shutdown when it has `close()`.
  - `InvalidInputError(message, *, field, code)`: all 7 raise sites set both; messages unchanged.
  - New dependency `python-multipart`. DB fixtures moved from `tests/integration/conftest.py` to `tests/conftest.py` so `tests/api` can use them.
  - Tests: 27 in `tests/api/test_upload.py` (integration): indexed/up_to_date/force/`.MD`/given source_key; 401 x4 with no provider call or write; 413 by header and by read (at-limit file accepted); 422 for each file code (content never in the body), tenant, source_key field vs derived from the file name; FastAPI's 422 in the same shape; 502 with the cause only in the log; 404/405 (`Allow`)/400 malformed multipart/JSON 500. Unit tests assert `field`/`code`. 265 passed, 1 deselected; ruff clean.
  - Manual (local dev DB, FakeEmbedder, curl): 201, 200, 201 with force, 422 tenant, 413 for a 6 MB file; logs show only doc_id/tenant/status/counts/ms. The local dev DB still had the pre-6a.1 schema (`markdown_path`, empty tables): reset with `alembic downgrade base` + `upgrade head`.
- [x] 6c.1. Settings hardening (brief approved 2026-10-28):
  - `.env` is found from any working directory: `config.default_env_file()` = `AYO_ENV_FILE` if set in the environment, else `<project root>/.env` (from `config.py`'s location). Installed as a package the path points nowhere and only real env vars apply. The lifespan logs which file was used (path only).
  - `env_ignore_empty=True`: `KEY=` counts as unset, so an empty `VOYAGE_API_KEY` or `ADMIN_API_KEY` fails at startup instead of at the first upload. `min_length=1` on both secrets also refuses `""` passed to the constructor. Side effect: an empty `DATABASE_URL` falls back to the local dev default.
  - Tests: 11 new in `tests/unit/test_config.py` (default path independent of cwd, override, file read, env beats file, empty values via env and via file, empty constructor values, empty DATABASE_URL). 276 passed, 1 deselected; ruff clean.
  - Manual: from the scratchpad directory `Settings()` reads the repo's `.env` (Neon dev host, Voyage key set). It also showed the real `.env` has **no `ADMIN_API_KEY`**, so the API cannot start with it as is (true before this step too).
- [ ] 6d. **Next.** OpenAPI polish (title/version from package metadata/description/tags, endpoint docs with examples for each status), `scripts/export_openapi.py`, `docs/openapi.json`, contract tests, `openapi-spec-validator` (dev). Revisit reading settings at startup vs `DOCS_ENABLED` at build time.
- [ ] 7. README (local DB, running, tests, `curl` example), manual run (FakeEmbedder, then real Voyage), final report (list every deviation from the spec).
 as listed in "Order of work", each broken into small commits and logged here.

### Open items
- **2026-10-28: 6c and 6c.1 done and committed (not pushed).** Resume at 6d: write its brief first.
- `.env` has no `ADMIN_API_KEY` (found 2026-10-28): the user needs to add one before running the API against it. 6d documents the single error shape (`ErrorResponse`) per status.
- 2026-10-27: resumed at 5b. New working rule: before starting each step, write a short brief (what it delivers, files, design choices and deviations, tests).
- **Awaiting user confirmation (asked after step 3):** chunk-policy interpretations: (1) "same section" = one path equal to, or a subsection of, the other, and the merged piece keeps the receiver's path; (2) heading-only sections never become pieces (the heading lives on in the path), and a heading with no content anywhere below it is dropped by rule 1; (3) the 1.5x cap applies only to backward merges; (4) same-section overlapping pieces are joined at their offsets, without repeating the overlap; (5) page-number patterns: `12`, `Página 3`, `pág. 3 de 10`, `3 / 10`, `- 4 -`, `(4)`.
- Workflow reminders: push only when the user asks (they asked on 2026-10-22 after 5a; a normal push, never a force-push); the spec file `plans/claude-code-prompt-markdown-ingestion.md` is intentionally left untracked; the log-update edits go into the next step's commit.
- **Before any search endpoint (added 2026-10-27):** HNSW applies the tenant filter after the index scan (`hnsw.ef_search` = 40 candidates), so a small tenant can get fewer than `limit` results, or none. Fix when search is built: `SET LOCAL hnsw.iterative_scan = relaxed_order` + materialized CTE re-sorted with `ORDER BY distance + 0` (PG17+); consider a real `tenant` column on `chunks` (no join; enables partitioning by tenant); test recall on a dataset large enough that the planner uses the index. Ref: pgvector README, "Filtering" and "Iterative Index Scans" (>= 0.8.0; we run 0.8.7).
- Neon password must be rotated by the user (history rewrite does not revoke a leaked secret). Still unconfirmed on 2026-10-27 (`.env` uses role `ayodb_owner`). `.env` has no `MIGRATIONS_DATABASE_URL` yet (suggested to the user: the direct endpoint, without `-pooler`).
- Possible rename: `ingestion/storage.py` -> `validation.py` (only validation left after 6a.1). Not requested yet.
