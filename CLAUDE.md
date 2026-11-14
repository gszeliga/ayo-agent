# CLAUDE.md

AYO Plant Copilot: an AI agent that guides industrial plant teams through structured
problem solving. This repo holds the FastAPI service and the knowledge ingestion
pipeline (RAG): Markdown upload -> chunks -> Voyage embeddings -> Postgres + pgvector.

**Keep this file up to date.** When a step changes commands, layout, conventions or
working rules, update this file in that step's commit.

## Where things stand

- **Active (2026-11-12): conversation engine core.** Spec
  `plans/claude-code-prompt-conversation-engine.md`; decisions (which override the spec where
  they differ), steps E1-E11 and log in `plans/engine-progress.md`. **Read both first.**
  E11 is billed (live test, manual conversations, `ayo-llm-check` rerun): give call counts
  and a cost estimate and wait for the user's OK.
- Done (2026-11-12): LLM provider through OpenRouter (L1-L6; spec
  `plans/claude-code-prompt-llm-provider.md`, decisions and log in `plans/llm-progress.md`).
  L7, the billed check run, is superseded by E11 of the engine milestone (decision 10 in
  `plans/engine-progress.md`). Do not run `ayo-llm-check run` or the OpenRouter live tests
  without the user's OK.
- Done (2026-11-10): test search screen in the UI (`/search`; decision 8 and steps
  U12-U13 in `plans/ui-progress.md`).
- **Paused (2026-11-10): search and retrieval evaluation.** Spec
  `plans/claude-code-prompt-search-eval.md`; decisions (which override the spec where they
  differ), steps S1-S5 and log in `plans/search-progress.md`. **Read both first.** S1 and S2
  are done (`POST /admin/search` is live). The evaluation harness (S3-S5) is parked until
  the user has agreed the case format with ayo (decision 10 there); do not resume it
  without the user saying so. Exact vector search:
  `docs/decisions/0002-filtered-vector-search.md`.
- Done (2026-11-10): status filter and bulk reprocess (B5, U10, U11; decision 7 in
  `plans/ui-progress.md`). Deployment (D1) is parked (decision 6 there).
- Done (2026-11-05): admin UI (React + Vite + TS in `ui/`, details in `ui/README.md`).
  Decisions (deployment: decision 5), progress log, final report and "Open items" in
  `plans/ui-progress.md`.
- Done (2026-11-02): documents CRUD. Spec `plans/claude-code-prompt-documents-crud.md`;
  plan, agreed deviations, progress log, final report and "Open items" in
  `plans/crud-progress.md` (the reference for its decisions).
- Done: the ingestion slice. Spec `plans/claude-code-prompt-markdown-ingestion.md`; its
  decisions and log in `plans/progress.md` (still the reference for earlier decisions).
- The spec files (`plans/claude-code-prompt-*.md`) are intentionally **untracked**; never
  commit them.
- Decision records: `docs/decisions/`.

## How we work (user's rules)

- **Baby steps.** One small step at a time. Before starting a step, write a short brief:
  what it delivers, files, design choices and deviations, tests. Wait for approval.
- Keep `README.md` current: any step that adds or changes an endpoint, a setting or a
  command updates it in the same commit.
- After the step: update the active milestone's progress file (now
  `plans/engine-progress.md`), make **exactly one commit** (code + tests + log together),
  summarise what changed and what to check, then **stop** for review.
  Never chain steps, even when told to "continue".
- **Push only when the user asks**, and never force-push.
- Tell the user before deviating from the spec; record agreed deviations under
  "Decisions" in that progress file.
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
uv run pytest -m live                     # real Voyage + OpenRouter calls (needs the keys)
uv run ruff check . && uv run ruff format --check .
scripts/dev_db.sh up|down                 # local dev DB: pgvector/pgvector:0.8.7-pg18-trixie on localhost:5433
scripts/db_shell.sh [local|remote|migrations] [--write] [-- psql args]   # psql; remote is read-only by default
uv run alembic upgrade head               # migrations (uses MIGRATIONS_DATABASE_URL, else DATABASE_URL)
uv run ayo-copilot                        # run the API on 127.0.0.1:8000
uv run python scripts/export_openapi.py   # regenerate docs/openapi.json (--check: verify only)
uv run ayo-llm-check models --model ID     # OpenRouter listing: tools, context, prices, ZDR (free)
uv run ayo-llm-check run --models A,B --runs 3   # tool-calling check: REAL, billed calls (cap: --max-calls)
# UI (in ui/, pnpm; details in ui/README.md)
pnpm install && pnpm dev                  # http://localhost:5173 (API needs CORS_ALLOWED_ORIGINS=http://localhost:5173)
pnpm check                                # gen:api:check + lint + format:check + typecheck + test
pnpm gen:api                              # regenerate ui/src/api/schema.d.ts from docs/openapi.json
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
                       CORS middleware, lifespan: prompts, pool, embedder, LLM provider, DB_LOG_LEVEL, dimension check
  errors.py            ApiError + handlers: every error is {"detail": [{type, loc, msg}]}
  schemas.py           IngestResponse, Document, Chunk, DocumentUpdate, Page[T] -> *Page, Search*, errors
  dependencies.py      get_settings / get_pool / get_embedder / get_embedding_monitor / get_llm_provider / get_prompts (request.state)
  routers/admin.py     /admin: upload, list, get, content, chunks, rename, reprocess, delete, bulk delete, search, tenants, settings, health (provisional X-API-Key auth, size limits)
  routers/copilot.py   /copilot: send a message, get a session (own key dependency), LLM errors -> 502/503
  documents.py         admin read/write operations on stored documents (own transactions)
  health.py            /admin/health: check_database, EmbeddingMonitor (cached probe), TrackedEmbedder
  search.py            search(): embed_query, then exact vector search in one read-only transaction
  openapi.py           render_openapi() for the committed contract docs/openapi.json
  config.py            DatabaseSettings (Alembic), BuildSettings (app build: docs, CORS),
                       LLMSettings (ayo-llm-check), ConversationSettings < Settings
  db/pool.py           open_pool (register_vector per connection), set_db_log_level
  db/repository.py     hand-written SQL: upsert_document, replace_chunks, search_chunks, ...
  db/conversations.py  hand-written SQL for cases, events, actions, links, traces (TraceRecord)
  ingestion/chunking.py    normalize_markdown, chunk_markdown (header + recursive splitters, small-chunk policy)
  ingestion/signatures.py  content/chunk/embed signatures, make_doc_id, CHUNKER_VERSION
  ingestion/embedding.py   Embedder protocol (embed_documents, embed_query), VoyageEmbedder (httpx2), FakeEmbedder
  ingestion/storage.py     tenant and source_key validation (name is historical)
  ingestion/service.py     the pipeline: ingest_document, reprocess_document and their stages
  llm/types.py         ToolSpec, ToolCall, Message, Usage, LLMResponse (self-validating; content not in repr)
  llm/errors.py        LLMError and subclasses (safe messages, optional status)
  llm/provider.py      LLMProvider protocol (sync), check_request
  llm/build.py         build_llm_provider (no request, no key check), describe_llm_provider (startup log)
  llm/fake.py          FakeLLMProvider (scripted, records calls) and response helpers
  llm/check/           ayo-llm-check core: scenarios.py (DRAFT tools, prompts, nine scenarios),
                       evaluate.py (verdicts), runner.py (runs, metrics, Wilson CIs), report.py,
                       catalog.py (models listing), cli.py (ayo-llm-check)
  conversation/case.py     CaseSnapshot (Case, Event, Action) and TurnChanges (what a turn accepted)
  conversation/phases.py   TRANSITIONS, exit criteria (missing_for), describe_missing / describe_targets
  conversation/tools.py    TOOLS (one ToolDef per tool: spec, phases, handler), tools_for_phase, execute_tool
  conversation/prompt_files.py  load_prompts (string.Template, once at startup) -> PromptSet
  conversation/prompts/    draft prompt files (Spanish): base.md, one per phase, glossary.md
  conversation/context.py  build_system_prompt (parts, delimited data blocks), build_messages (window)
  conversation/query.py    build_query: the retrieval query from the case state
  conversation/reply.py    compose_reply and the fallback message
  conversation/store.py    resolve_case (race-safe), load_snapshot, commit_turn (version check), read_session
  conversation/engine.py   TurnEngine.handle_turn: model loop, phase hops, caps, retrieval, trace, commit
  conversation/channels.py IncomingMessage, ChannelAdapter, WebAdapter, handle_message (resolve case + turn)
  llm/openrouter.py    OpenRouterProvider (httpx2): serializers, error mapping, parse_completion,
                       retries (Retry-After, budget), one log line per call with generation ids
migrations/            Alembic; 0001 = documents + chunks (vector(1024), HNSW cosine)
                       0002 = documents.chunk_count/size_bytes/*_config + list index
                       0003 = problems, problem_events, actions, conversation_links, turn_traces
scripts/               dev_db.sh, db_shell.sh (psql; no tests, a personal tool), export_openapi.py
docs/                  openapi.json (generated, committed), decisions/
eval/llm/              ayo-llm-check reports (git-ignored) and example-report.json (scripted)
tests/{unit,api,integration,live}/, tests/fixtures/ (Spanish Markdown)
ui/                    admin UI: React + Vite + TS, Tailwind v4 + shadcn/ui; layout in ui/README.md
  src/api/schema.d.ts  generated from docs/openapi.json (never edit)
```

## Conventions

- Python 3.12, uv, ruff (line length 100). Type annotations on new code. English for
  code, comments, logs and API messages; test fixtures use realistic Spanish text.
- psycopg 3 + psycopg_pool + pgvector, hand-written SQL, **no ORM** (SQLAlchemy is only
  there because Alembic needs it).
- Repository functions take a connection and never commit; the service owns transactions.
  The embedding provider is called outside any transaction.
- LLM calls log metadata only (models, attempts, tokens, cost, tool names, generation
  ids): never prompts, messages, tool arguments, text or reasoning; tests check every path.
- Vector search is exact (ADR 0002): never rely on the HNSW index for filtered queries.
  Search queries are as sensitive as documents: never log the query or the chunks found.
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
  every documented status must be triggered for real in `tests/api/test_contract.py`.
  Then run `pnpm gen:api` in `ui/` and commit `ui/src/api/schema.d.ts` too
  (`pnpm gen:api:check` fails otherwise). The UI's routes share the origin with these paths
  in production, so a new top-level API path must not clash with a UI route
  (`ui/src/paths.test.ts`). Tests build the app with
  `create_app(docs_enabled=True)` so they never read `.env` (CORS is then off).
- `{doc_id}` path parameters use `DOC_ID_PATTERN` (malformed -> 422, unknown -> 404
  `document_not_found`). Every `/admin` and `/copilot` route needs the key:
  `tests/api/test_admin_auth.py` and `test_copilot_auth.py` enumerate them from the OpenAPI
  document, so never hide such a route from it. The contract test covers both prefixes.
- UI (`ui/`): TypeScript strict, ESLint type-aware + Prettier (width 100, no semicolons,
  single quotes); `pnpm check` must pass. TypeScript stays on 5.x until typescript-eslint
  and openapi-typescript support 7. Theme colours only through the tokens in
  `src/index.css`. Tests use MSW; unhandled requests fail. English UI copy. API calls go
  through `useApiClient()` + `unwrap()`, errors are `ApiError`. UI routes never start with
  an API path (`/admin`, `/health`, `/docs`, `/redoc`, `/openapi.json`).
- Integration tests (`tests/integration/`, `tests/api/`; fixtures in `tests/conftest.py`)
  use the `db_pool` fixture (tables truncated before each test) or `scratch_database_url`
  (a throwaway database) for migration-level tests.
