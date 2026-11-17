# AYO Plant Copilot

AI agent that guides industrial plant teams through structured problem solving. This
repository holds the API and the knowledge ingestion pipeline (RAG).

Upload a Markdown document and the API splits it into chunks along its headings, embeds
each chunk with [Voyage AI](https://www.voyageai.com/), and stores the document and its
vectors in Postgres with pgvector, ready for similarity search.

The `/admin` API manages those documents for an admin UI: list and inspect them (Markdown,
chunks), rename, replace, reprocess after a settings change, and delete them; and search
them with a question, as the copilot does.

The `/copilot` API is the copilot itself: it guides a plant team through five phases,
from a vague problem to a closed case with its actions.

## Quick start (local)

Needs [uv](https://docs.astral.sh/uv/) and Docker.

```sh
uv sync                        # install
cp .env.example .env           # then set ADMIN_API_KEY (and VOYAGE_API_KEY, or use the fake embedder)
scripts/dev_db.sh up           # Postgres 18 + pgvector on localhost:5433 (data kept in a Docker volume)
uv run alembic upgrade head    # create the tables
uv run ayo-copilot             # API on http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000/docs>, click **Authorize**, paste your `ADMIN_API_KEY`, and
upload a file with **Try it out**. `scripts/dev_db.sh down` stops the database.

Without a Voyage key, set `EMBEDDING_PROVIDER=fake`: deterministic vectors, no network.
Uploads work, but the vectors carry no meaning, so the app logs a warning at startup.

For a Neon dev branch or a psql shell, see [docs/operations.md](docs/operations.md).

## Where to find what

| File | What you find there |
|---|---|
| [docs/knowledge-base.md](docs/knowledge-base.md) | Uploading, reading, renaming, replacing, reprocessing and deleting documents; tenants; indexing settings; chunking |
| [docs/search.md](docs/search.md) | Searching the knowledge base: the request, the filters, how results are ranked |
| [docs/copilot.md](docs/copilot.md) | Talking to the copilot; inspecting its cases; the flow of a turn, the phase rules, the tools, the trace; editing the prompt files |
| [docs/configuration.md](docs/configuration.md) | Every setting, by group; browser clients (CORS) |
| [docs/operations.md](docs/operations.md) | A Neon dev branch, the psql shell, the service status, what the logs hold |
| [docs/development.md](docs/development.md) | Tests, the API contract, the tool-calling check (`ayo-llm-check`) |
| [ui/README.md](ui/README.md) | The admin UI |
| [docs/decisions/](docs/decisions/) | Architecture decision records |
| [CLAUDE.md](CLAUDE.md) | Working conventions and a file-by-file map |

## Endpoints

All under `/admin` and `/copilot` need the `X-API-Key` header. `/docs` has every status,
error `type` and example.

| Method and path | Purpose |
|---|---|
| `POST /admin/documents` | Upload a Markdown file; the same `tenant` + `source_key` replaces it |
| `GET /admin/documents` | List documents (filter by tenant, text or status; sort, paginate) |
| `GET /admin/documents/{doc_id}` | One document, with its `status` |
| `GET /admin/documents/{doc_id}/content` | Its stored Markdown |
| `GET /admin/documents/{doc_id}/chunks` | Its chunks, optionally with vectors |
| `PATCH /admin/documents/{doc_id}` | Rename it |
| `POST /admin/documents/{doc_id}/reprocess` | Re-chunk and re-embed it with the current settings |
| `DELETE /admin/documents/{doc_id}` | Delete it and its chunks |
| `POST /admin/documents/delete` | Delete up to 100 documents at once |
| `POST /admin/search` | Find the chunks nearest to a question (filter by tenant or document) |
| `GET /admin/tenants` | Tenants with document and chunk counts |
| `GET /admin/settings` | Current indexing settings and document counts by status |
| `GET /admin/health` | Status of the database and the embedding provider |
| `POST /copilot/messages` | Send a session's message to the copilot; get its reply and the phase |
| `GET /copilot/sessions/{session_id}` | A session's case: phase, facts, annotations, actions, messages |
| `GET /admin/cases` | The copilot's cases from every channel (filter by tenant, phase, open or closed, text) |
| `GET /admin/cases/{case_id}` | One case: header, facts, annotations, actions (with `overdue`), AI summary |
| `GET /admin/cases/{case_id}/turns` | A case's turns, oldest first, in pages: messages and trace |
| `DELETE /admin/cases/{case_id}` | Delete a case for good, with its messages, actions, links and traces |
| `GET /health` | Liveness, no key |

The `X-API-Key` authentication is provisional: one shared key, to be replaced by real
identity and per-tenant permissions.

## Everyday commands

```sh
uv sync                                   # install
uv run pytest                             # tests (integration ones need Docker); see docs/development.md
uv run ruff check . && uv run ruff format --check .
scripts/dev_db.sh up|down                 # local dev database on localhost:5433
scripts/db_shell.sh [local|remote|migrations]   # psql; remote is read-only by default
uv run alembic upgrade head               # migrations
uv run ayo-copilot                        # the API on http://127.0.0.1:8000
uv run python scripts/export_openapi.py   # regenerate docs/openapi.json (--check: verify only)
uv run ayo-llm-check models --model ID    # a model's tool support and prices (free)
uv run ayo-transcript SESSION_ID          # a copilot session as Markdown in eval/conversations/
```

## Admin UI

The browser UI lives in `ui/` (React + Vite + TypeScript): `cd ui && pnpm install && pnpm dev`,
with the API started with `CORS_ALLOWED_ORIGINS=http://localhost:5173`. See
[ui/README.md](ui/README.md).

## Layout

```
src/ayo_copilot/   the app: API (app.py, routers/, schemas.py, errors.py), settings,
                   database access (db/), ingestion pipeline (ingestion/), language
                   model access (llm/), conversation engine and prompts (conversation/)
migrations/        Alembic migrations
scripts/           dev_db.sh, db_shell.sh, export_openapi.py
docs/              the topic docs above, openapi.json, decisions/ (architecture decision records)
tests/             unit/, api/, integration/, live/, fixtures/ (Spanish Markdown)
ui/                the admin UI
```

`CLAUDE.md` has the working conventions and a file-by-file map.
