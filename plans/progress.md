# Ingestion slice: plan and progress

Spec: `plans/claude-code-prompt-markdown-ingestion.md`. This file holds the agreed deviations and the progress log; resume from the first unchecked item under "Next".

## Decisions from Q&A (these override the spec)
- **Naming:** rename the package to `ayo_copilot`, `bootstrap.py` to `app.py` and `create_agent()` to `create_app()`. Update `[project.scripts]` and `main()` (which keeps `factory=True`) to match. The existing `/health` route stays.
- **Test DB:** testcontainers is the leading candidate. It only needs the Docker daemon, which is running here (Compose is not installed). Step 0 still compares all six options in `docs/decisions/0001-test-database.md` and waits for your approval. For the dev DB used for manual runs, a scripted `docker run pgvector/pgvector:<pg-version>` (as `make`/`scripts` commands) replaces Compose.
- **Neon = production.** No test or dev command ever touches it, and its URL is never read by default.
- **Embeddings: hosted Voyage AI, as the original spec says.** `VoyageEmbedder` is a thin httpx client (`input_type="document"`), sitting behind the `Embedder` protocol alongside `FakeEmbedder` for tests.
  - Before writing the client, check the official Voyage docs for the current model names, output dimensions, per-request limits and request shape. The working assumption is `voyage-4` at 1024 dims.
  - The API key goes only into the gitignored `.env` as `VOYAGE_API_KEY`. It never goes into any committed file, log or test fixture, and `.env.example` holds a placeholder.
  - The `live` test does one real upload against Voyage and is skipped when there's no key.

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
6. `ingestion/service.py`, `schemas.py`, `routers/admin.py` and the lifespan (pool plus a dimension check against the DB). API and OpenAPI tests, `scripts/export_openapi.py` and `docs/openapi.json`.
7. README, a manual run (FakeEmbedder, then real Voyage) and the final report.

## Verification
- `uv run pytest`: unit and API tests run with no DB or network; integration tests use testcontainers, or are skipped with a clear message if Docker is missing.
- `uv run ruff check .` and `uv run ruff format --check .`.
- Migrations apply from scratch with one command.
- Manual upload through Swagger UI (Authorize, then Try it out) and with `curl`.

## Progress log (update after every small step; resume from the first unchecked item)
Working rule: baby steps. One small step, then update this log, then continue.

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
- [ ] 2b. `ingestion/storage.py`: `validate_tenant`, `normalize_source_key` (NFC, basename only, no `..`, no control chars, reject empty) with path-traversal tests; then atomic write (`write_markdown_atomic`).
- [ ] 3+. Remaining steps as listed in "Order of work", each broken into small commits and logged here.

### Open items
- Neon password must be rotated by the user (history rewrite does not revoke a leaked secret).
