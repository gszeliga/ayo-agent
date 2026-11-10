# AYO Plant Copilot

AI agent that guides industrial plant teams through structured problem solving. This
repository holds the API and the knowledge ingestion pipeline (RAG).

Upload a Markdown document and the API splits it into chunks along its headings, embeds
each chunk with [Voyage AI](https://www.voyageai.com/), and stores the document and its
vectors in Postgres with pgvector, ready for similarity search.

The `/admin` API manages those documents for an admin UI: list and inspect them (Markdown,
chunks), rename, replace, reprocess after a settings change, and delete them; and search
them with a question, as the copilot will.

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

## Endpoints

All under `/admin` need the `X-API-Key` header. `/docs` has every status, error `type`
and example.

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
| `GET /health` | Liveness, no key |

## Uploading a document

```sh
curl -H "X-API-Key: $ADMIN_API_KEY" \
  -F file=@tests/fixtures/pro-014-control-sellado.md \
  -F tenant=acme \
  http://127.0.0.1:8000/admin/documents
```

```json
{"doc_id": "upload-…", "status": "indexed", "chunk_count": 5, "embedding_model": "voyage-4", "embed_signature": "17047d562b7e…"}
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

## Reading documents

Every `/admin` route needs the `X-API-Key` header. A document is addressed by the
`doc_id` that the upload and the listing return.

```sh
H="X-API-Key: $ADMIN_API_KEY"
API=http://127.0.0.1:8000/admin/documents

curl -H "$H" "$API?tenant=acme&q=sellado&sort=-updated_at&limit=25&offset=0"  # list
curl -H "$H" "$API?status=outdated"                                         # outdated ones
curl -H "$H" "$API/upload-1890b5dc5335"                                      # one document
curl -H "$H" "$API/upload-1890b5dc5335/content"                              # its Markdown
curl -H "$H" "$API/upload-1890b5dc5335/chunks?limit=50&offset=0"             # its chunks
```

- **List**: a page `{"items": [...], "total": N, "limit": N, "offset": N}`. Filters:
  `tenant`, `q` (case-insensitive substring of the title or the source key), `status`
  (`indexed` or `outdated` against the current settings: the documents
  `GET /admin/settings` counts as outdated, whatever the reason). `sort` is
  one of `updated_at`, `created_at`, `title`, `chunk_count`, with `-` for descending
  (default `-updated_at`). `limit` is 1 to 100 (default 25).
- **One document**: the same object as a list item. `status` is `indexed`, or `outdated`
  when the chunking or embedding settings changed since it was indexed (`outdated_reason`
  says which).
- **Content**: the stored Markdown as `text/markdown; charset=utf-8`, after normalization
  (no BOM, LF line endings).
- **Chunks**: a page of `{chunk_index, heading, chunk_text, char_count, embedding}` in
  order. `limit` is 1 to 200 (default 50). `embedding` is null unless
  `include_embedding=true`, which is heavy (one float per dimension, per chunk).

An unknown `doc_id` gives `404` (`document_not_found`); a malformed one gives `422`.

## Renaming a document

```sh
curl -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"title": "PRO-014 Control de sellado (rev. 3)"}' \
  "$API/upload-1890b5dc5335"
```

Returns the renamed document. Only `title` (trimmed, 1 to 200 characters) and
`updated_at` change; nothing is re-chunked or re-embedded, and renaming to the current
title changes nothing. Any other field in the body is a `422`.

## Replacing a document

Upload the new file with the document's `tenant` and `source_key` (both are in every
listed item); the `doc_id` stays the same:

```sh
curl -H "$H" -F file=@pro-014-v2.md -F tenant=acme \
  -F source_key=pro-014-control-sellado.md -F "title=PRO-014 Control de sellado (rev. 3)" \
  "$API"
```

Changed content answers `201` with `indexed`; identical content `200` with `up_to_date`.
The upload sets the title again (the `title` field, else the first `# ` heading, else the
file name), so send `title` to keep a rename.

## Reprocessing a document

After changing the chunking or embedding settings (`CHUNK_SIZE`, `EMBEDDING_MODEL`, ...),
documents indexed before show `"status": "outdated"`; `GET /admin/documents?status=outdated`
lists them. Reprocess one from its stored Markdown, without uploading it again:

```sh
curl -X POST -H "$H" "$API/upload-1890b5dc5335/reprocess"
```

The answer has the upload's shape, always with `200`: `indexed` (re-chunked and
re-embedded) or `up_to_date` (nothing to do, no Voyage call). `?force=true` reprocesses
anyway. The title, the Markdown and `updated_at` are kept. A document indexed before its
settings were recorded (`outdated_reason: unknown`) but still matching them just gets
them recorded. `409 document_changed` means a newer upload replaced the document
meanwhile (nothing was written); `502` means Voyage failed (nothing was written either).

## Deleting a document

```sh
curl -X DELETE -H "$H" "$API/upload-1890b5dc5335"   # 204, no body
```

Removes the document and its chunks for good (no undo, no audit table yet: the only trace
is a log line with `doc_id`, tenant and chunk count). A second delete answers `404`.
Uploading the same file name for the same tenant afterwards creates a new document with
the same `doc_id`.

## Deleting several documents

```sh
curl -H "$H" -H "Content-Type: application/json" \
  -d '{"doc_ids": ["upload-1890b5dc5335", "upload-4be0c2a91d7f"]}' "$API/delete"
# {"deleted": [{"doc_id": "upload-1890b5dc5335", "tenant": "acme", "chunk_count": 12}],
#  "not_found": ["upload-4be0c2a91d7f"]}
```

1 to 100 distinct ids, deleted with their chunks in one transaction (all or none). Ids with
no document come back in `not_found`, not as an error, so repeating the request is safe.
A `POST` rather than `DELETE`, since proxies may drop a body on `DELETE`. Each deleted
document gets the same log line as a single delete.

## Searching

```sh
curl -H "$H" -H "Content-Type: application/json" \
  -d '{"query": "¿Qué herramienta uso si tengo muchos tipos de defecto?",
       "tenants": ["cliente-acme", "ayo"], "top_k": 5, "debug": true}' \
  "http://127.0.0.1:8000/admin/search"
# {"query": "¿Qué herramienta uso si tengo muchos tipos de defecto?",
#  "results": [{"rank": 1, "similarity": 0.8734, "chunk_id": "0b9f6c1e-...",
#    "chunk_index": 3, "heading": "Método Pareto > Cuándo aplicarlo", "chunk_text": "...",
#    "char_count": 148, "doc_id": "upload-3f9a1c2b7d4e", "document_title": "Método Pareto",
#    "source_key": "pareto.md", "tenant": "ayo", "embedder_outdated": false}],
#  "skipped": {"embedder_mismatch": 0},
#  "debug": {"embedded_query": "...", "input_type": "query", "embedder_config": "...",
#    "chunker_config": "...", "timings_ms": {"embed": 41.2, "search": 6.3, "total": 47.5}}}
```

What the copilot would retrieve for a question. The query is embedded as a search query
(Voyage `input_type: "query"`), then compared by cosine similarity with every chunk that
passes the filters: an exact search, so the same request on the same data always gives
the same answer (`docs/decisions/0002-filtered-vector-search.md`). Results are ordered by
`similarity` (1 - cosine distance, 4 decimals), ties by chunk id.

| Field | Default | Meaning |
|---|---|---|
| `query` | required | 1 to 2000 characters after trimming |
| `tenants` | `null` (all) | 1 to 50 tenant ids. The production agent will search one customer plus `ayo`, never across customers |
| `top_k` | 5 | 1 to 50 |
| `min_similarity` | `null` | 0 to 1; weaker results are dropped |
| `doc_ids` | `null` (all) | 1 to 50 document ids, to debug one document |
| `include_outdated` | `false` | Also search documents embedded with another model, flagged `embedder_outdated` |
| `debug` | `false` | Fill `debug` (otherwise `null`) with the text embedded, the configs and timings |

Send `null`, not `[]`, for no filter: an empty list is a `422`. Unknown tenants or ids are
not errors; they just add no results.

Vectors of different embedding models are not comparable, so documents embedded with
another model (or an unknown one) are skipped and counted in `skipped.embedder_mismatch`:
reprocess them. A change of the chunking settings alone skips nothing. If the embedding
provider fails, the answer is `502 embedding_failed` and nothing is searched. Neither the
query nor the results are logged: only tenants, counts and durations.

## Tenants

```sh
curl -H "$H" "http://127.0.0.1:8000/admin/tenants"
# [{"tenant": "acme", "document_count": 4, "chunk_count": 57}]
```

Every tenant with stored documents, ordered by tenant, with its document and chunk counts
(for a tenant filter). Not paginated; a tenant whose last document is deleted disappears.

## Indexing settings

```sh
curl -H "$H" "http://127.0.0.1:8000/admin/settings"
# {"chunking": {"chunker_version": "md-header+recursive@v3", "chunk_size": 800, ...,
#   "chunker_config": "md-header+recursive@v3/size=800/..."},
#  "embedding": {"provider": "voyage", "model": "voyage-4", "dimensions": 1024,
#   "batch_size": 128, "embedder_config": "voyage-4/document/1024"},
#  "uploads": {"max_upload_bytes": 5242880},
#  "documents": {"total": 12, "indexed": 9,
#   "outdated": {"unknown": 0, "chunker_changed": 2, "embedder_changed": 1}}}
```

Read-only: the chunking, embedding and upload settings new uploads and reprocesses use
(from the environment; no keys, URLs or database settings), and how many documents across
all tenants are `indexed` with them or `outdated`, by the same reasons as each document's
`outdated_reason`. The two config strings are the ones documents are compared with.

## Service status

```sh
curl -H "$H" "http://127.0.0.1:8000/admin/health"                # refresh=true: check again
# {"status": "ok",
#  "database": {"status": "up", "latency_ms": 4, "error": null, "location": "local",
#   "postgres_version": "18.6", "pgvector_version": "0.8.7"},
#  "embeddings": {"status": "up", "provider": "voyage", "checked_at": "2026-11-05T10:14:03Z",
#   "latency_ms": 180, "error": null, "cached": false,
#   "last_success_at": "2026-11-05T09:58:41Z", "last_error_at": null, "last_error": null}}
```

Always `200`; a service that is down shows as `"status": "degraded"` with its `error`. The
database gets one query (2 s timeout) on every request, which also reads the PostgreSQL
and pgvector versions; `location` says where it runs as a category only (`local`, `neon`
for a `*.neon.tech` host, `remote`), never the host. The embedding provider gets one
request for a single word (5 s timeout, no retries), and the result is kept for 60 s, a
failure included; `refresh=true` checks again, and nothing is checked in the background.
`last_success_at`, `last_error_at` and `last_error` describe the last real embedding calls
(uploads, reprocesses) since the service started. The public `/health` stays liveness only.

## Browser clients (CORS)

A UI served from another origin needs `CORS_ALLOWED_ORIGINS`, for example
`CORS_ALLOWED_ORIGINS=http://localhost:5173`. Listed origins may use `GET`, `POST`,
`PATCH` and `DELETE` with the `X-API-Key` and `Content-Type` headers; no cookies or other
credentials. Any other origin gets no CORS headers, so the browser keeps the answers from
it. The setting is read when the app is built, so changing it needs a restart.

The API key is sent by the browser, so anyone using the UI can see it: fine for internal
or development use, not for a public UI (real authentication will replace the key).

## Admin UI

The browser UI lives in `ui/` (React + Vite + TypeScript): documents, upload and replace,
rename, reprocess, delete, indexing settings and service status, light and dark themes;
see [`ui/README.md`](ui/README.md). In short: `cd ui && pnpm install && pnpm dev`, with the API
started with `CORS_ALLOWED_ORIGINS=http://localhost:5173`. Its API types are generated
from `docs/openapi.json`, so an API change also runs `pnpm gen:api` there.

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
| `CORS_ALLOWED_ORIGINS` | *(empty: CORS off)* | Comma-separated browser origins allowed to call the API, such as `http://localhost:5173,https://admin.example.com`. Each is `http(s)://host[:port]`, without path or trailing slash; `*` is refused. See "Browser clients (CORS)". |
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
