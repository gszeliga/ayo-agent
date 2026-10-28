# AYO Plant Copilot

AI agent that guides industrial plant teams through structured problem solving. This
repository holds the API and the knowledge ingestion pipeline (RAG).

Upload a Markdown document and the API splits it into chunks along its headings, embeds
each chunk with [Voyage AI](https://www.voyageai.com/), and stores the document and its
vectors in Postgres with pgvector, ready for similarity search.

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

### Against a Neon dev branch

Never use the production branch for development. In `.env`:

```sh
DATABASE_URL=postgresql://<role>:<password>@<endpoint>-pooler.<region>.aws.neon.tech/<db>?sslmode=require
MIGRATIONS_DATABASE_URL=postgresql://<role>:<password>@<endpoint>.<region>.aws.neon.tech/<db>?sslmode=require
ALLOW_REMOTE_DATABASE=true
```

The app uses the pooled endpoint; migrations need the direct one (without `-pooler`),
because the pooled one runs PgBouncer. Environment variables win over `.env`, so one
command can still use the local database:
`DATABASE_URL=postgresql://ayo:ayo@localhost:5433/ayo ALLOW_REMOTE_DATABASE=false uv run ...`

## Uploading a document

```sh
curl -H "X-API-Key: $ADMIN_API_KEY" \
  -F file=@tests/fixtures/pro-014-control-sellado.md \
  -F tenant=acme \
  http://127.0.0.1:8000/admin/documents
```

```json
{"doc_id": "upload-…", "status": "indexed", "chunk_count": 5, "embedding_model": "voyage-4", "embed_signature": "17047d562b7e"}
```

That's `201`. Sending the same file again gives `200` and `{"doc_id": "upload-…", "status": "up_to_date"}`,
without calling Voyage. Changing the file, or the chunking or embedding settings,
reindexes it. `-F force=true` reindexes anyway. Optional fields: `title`, and `source_key`
(identifies the document within the tenant; the file name by default).

Errors all have one shape, told apart by `type`:

```json
{"detail": [{"type": "file_empty", "loc": ["body", "file"], "msg": "file is empty"}]}
```

`/docs` lists every status and `type`. The `X-API-Key` authentication is provisional:
one shared key, to be replaced by real identity and per-tenant permissions.

## Tests

```sh
uv run pytest                        # everything except `live`; integration tests need Docker
uv run pytest -m "not integration"   # no Docker, no database
uv run pytest -m live                # one real Voyage request (needs VOYAGE_API_KEY)
uv run ruff check . && uv run ruff format --check .
```

Integration tests start their own Postgres container (testcontainers), separate from the
dev database, and are skipped with a clear message when Docker is not available. To use
an existing server instead, set `TEST_DATABASE_URL` (a pgvector-enabled Postgres; each
test run creates and drops its own databases). Neon URLs are refused. Tests never read
`.env`. Why this setup: `docs/decisions/0001-test-database.md`.

## API contract

`docs/openapi.json` is the OpenAPI spec, generated from the code and committed, so API
changes show up in review. After changing the API, regenerate it (a test fails until you
do):

```sh
uv run python scripts/export_openapi.py          # --check only verifies
```

## Configuration

All settings come from environment variables, or from the `.env` file at the project root
(found whatever the working directory; set `AYO_ENV_FILE` in the environment to use
another file). Environment variables win over the file. Empty values (`KEY=`) count as
unset, so a required one makes startup fail. Copy `.env.example` to `.env` to start.
Never commit `.env`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ayo:ayo@localhost:5433/ayo` | Postgres with pgvector. The default is the local dev database; never point it at production by accident. |
| `MIGRATIONS_DATABASE_URL` | *(unset: uses `DATABASE_URL`)* | Database URL for Alembic only. With Neon, use the direct endpoint here (the pooled one runs PgBouncer). |
| `ALLOW_REMOTE_DATABASE` | `false` | `DATABASE_URL` and `MIGRATIONS_DATABASE_URL` must point at `localhost` unless this is `true`. A guard against using a remote database by accident. |
| `DB_LOG_LEVEL` | `WARNING` | Level of psycopg's logs: `INFO` shows pool events (connection requested, given, returned), `DEBUG` also connection attempts. Hosts and ports are logged, never passwords. |
| `ADMIN_API_KEY` | *(required)* | Provisional admin key, sent as the `X-API-Key` header. |
| `MAX_UPLOAD_BYTES` | `5242880` (5 MiB) | Larger uploads are rejected with `413`. |
| `DOCS_ENABLED` | `true` | Serve `/docs`, `/redoc` and `/openapi.json`. They are public when on: restrict access in front of the app (proxy or private network) if needed. |
| `CHUNK_SIZE` | `800` | Target chunk size, **in characters**. |
| `CHUNK_OVERLAP` | `80` | Characters shared by consecutive chunks of a long section. Must be smaller than `CHUNK_SIZE`. |
| `MIN_CHUNK_SIZE` | `100` | Chunks shorter than this (in characters) are merged with a neighbour of the same section. This is a starting value to tune, not a validated number. See "Chunking" below. |
| `EMBEDDING_PROVIDER` | `voyage` | `voyage`, or `fake` (deterministic vectors, no network; for tests). |
| `EMBEDDING_MODEL` | `voyage-4` | Voyage model name. |
| `EMBEDDING_DIMENSIONS` | `1024` | Vector size; must match the database column, and at most 2000 (pgvector HNSW limit). |
| `VOYAGE_API_KEY` | *(required with `voyage`)* | Voyage AI API key. |
| `VOYAGE_BASE_URL` | `https://api.voyageai.com/v1` | Voyage API base URL. |
| `EMBEDDING_BATCH_SIZE` | `128` | Texts per embedding request (Voyage allows at most 1000). |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Timeout per embedding request. |
| `EMBEDDING_MAX_RETRIES` | `3` | Retries on `429`, `5xx`, timeouts and connection errors, with exponential backoff and jitter. Other errors fail at once. |

Changing `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MIN_CHUNK_SIZE`, `EMBEDDING_MODEL` or
`EMBEDDING_DIMENSIONS` changes the document signatures, so the next upload of each
document reprocesses it.

## Chunking

Markdown is split by `#`, `##` and `###` headings (`MarkdownHeaderTextSplitter`), and
long sections are then split by characters (`RecursiveCharacterTextSplitter`). Each chunk
keeps its heading path, e.g. `PRO-014 Control de sellado > 3. Pasos`.

Small chunks are merged, never silently discarded, because a short chunk can be the
critical one (for example "Temperatura máxima: 180 °C"). The rules, in order:

1. No content at all (every line is blank, a separator such as `---`, or a page number):
   dropped. A file left with no chunks at all is rejected (`422`, "no indexable content").
2. Shorter than `MIN_CHUNK_SIZE` and followed by a chunk of the same section (same
   heading path or a subsection of it): merged forward into it. This covers lead-ins
   like "Los pasos son:".
3. Shorter than `MIN_CHUNK_SIZE` and last in its section: merged backward into the
   previous chunk of the same section, as long as the result stays within
   1.5 × `CHUNK_SIZE`.
4. Otherwise kept as its own chunk.

Chunks are never merged across unrelated sections.

## Layout

```
src/ayo_copilot/   the app: API (app.py, routers/, schemas.py, errors.py), settings,
                   database access (db/), ingestion pipeline (ingestion/)
migrations/        Alembic migrations
scripts/           dev_db.sh, export_openapi.py
docs/              openapi.json, decisions/ (architecture decision records)
tests/             unit/, api/, integration/, live/, fixtures/ (Spanish Markdown)
```

`CLAUDE.md` has the working conventions and a file-by-file map.
