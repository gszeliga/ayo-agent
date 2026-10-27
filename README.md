# AYO Plant Copilot

AI agent that guides industrial plant teams through structured problem solving. This
repository holds the API and the knowledge ingestion pipeline (RAG).

> The rest of this README (local database, running the app, tests, `curl` example) is
> written in a later step. See `plans/progress.md`.

## Configuration

All settings come from environment variables, or from a `.env` file in the project root.
Copy `.env.example` to `.env` to start. Never commit `.env`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ayo:ayo@localhost:5433/ayo` | Postgres with pgvector. The default is the local dev database; never point it at production by accident. |
| `MIGRATIONS_DATABASE_URL` | *(unset: uses `DATABASE_URL`)* | Database URL for Alembic only. With Neon, use the direct endpoint here (the pooled one runs PgBouncer). |
| `ALLOW_REMOTE_DATABASE` | `false` | `DATABASE_URL` and `MIGRATIONS_DATABASE_URL` must point at `localhost` unless this is `true`. A guard against using a remote database by accident. |
| `DB_LOG_LEVEL` | `WARNING` | Level of psycopg's logs: `INFO` shows pool events (connection requested, given, returned), `DEBUG` also connection attempts. Hosts and ports are logged, never passwords. |
| `ADMIN_API_KEY` | *(required)* | Provisional admin key, sent as the `X-API-Key` header. |
| `KNOWLEDGE_DIR` | `data/knowledge` | Uploaded Markdown is stored at `{KNOWLEDGE_DIR}/{tenant}/upload/{doc_id}.md`. |
| `MAX_UPLOAD_BYTES` | `5242880` (5 MiB) | Larger uploads are rejected with `413`. |
| `DOCS_ENABLED` | `true` | Serve `/docs`, `/redoc` and `/openapi.json`. |
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

1. No content at all (blank, separators such as `---`, only a page number): dropped.
2. Shorter than `MIN_CHUNK_SIZE` and followed by a chunk of the same section (same
   heading path or a subsection of it): merged forward into it. This covers lead-ins
   like "Los pasos son:".
3. Shorter than `MIN_CHUNK_SIZE` and last in its section: merged backward into the
   previous chunk of the same section, as long as the result stays within
   1.5 × `CHUNK_SIZE`.
4. Otherwise kept as its own chunk.

Chunks are never merged across unrelated sections.
