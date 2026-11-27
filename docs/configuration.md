# Configuration

All settings come from environment variables, or from the `.env` file at the project root
(found whatever the working directory; set `AYO_ENV_FILE` in the environment to use
another file). Environment variables win over the file. Empty values (`KEY=`) count as
unset, so a required one makes startup fail. Copy `.env.example` to `.env` to start.
Never commit `.env`.

## Database and app

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ayo:ayo@localhost:5433/ayo` | Postgres with pgvector. The default is the local dev database; never point it at production by accident. |
| `MIGRATIONS_DATABASE_URL` | *(unset: uses `DATABASE_URL`)* | Database URL for Alembic only. With Neon, use the direct endpoint here (the pooled one runs PgBouncer). |
| `ALLOW_REMOTE_DATABASE` | `false` | `DATABASE_URL` and `MIGRATIONS_DATABASE_URL` must point at `localhost` unless this is `true`. A guard against using a remote database by accident. |
| `DB_LOG_LEVEL` | `WARNING` | Level of psycopg's logs: `INFO` shows pool events (connection requested, given, returned), `DEBUG` also connection attempts. Hosts and ports are logged, never passwords. |
| `ADMIN_API_KEY` | *(required)* | Provisional admin key, sent as the `X-API-Key` header. `docling-import-files` sends it too. |
| `MAX_UPLOAD_BYTES` | `5242880` (5 MiB) | Larger uploads are rejected with `413`. |
| `DOCS_ENABLED` | `true` | Serve `/docs`, `/redoc` and `/openapi.json`. They are public when on: restrict access in front of the app (proxy or private network) if needed. |
| `CORS_ALLOWED_ORIGINS` | *(empty: CORS off)* | Comma-separated browser origins allowed to call the API, such as `https://admin.example.com,http://192.168.1.50:5173`. Each is `http(s)://host[:port]`, without path or trailing slash; `*` is refused. See [Browser clients (CORS)](#browser-clients-cors). |

## Chunking and embeddings

Changing these makes documents `outdated`: see
[Reprocessing a document](knowledge-base.md#reprocessing-a-document).

| Variable | Default | Description |
|---|---|---|
| `CHUNK_SIZE` | `800` | Target chunk size, **in characters**. |
| `CHUNK_OVERLAP` | `80` | Characters shared by consecutive chunks of a long section. Must be smaller than `CHUNK_SIZE`. |
| `MIN_CHUNK_SIZE` | `100` | Chunks shorter than this (in characters) are merged with a neighbour of the same section. This is a starting value to tune, not a validated number. See [Chunking](knowledge-base.md#chunking). |
| `EMBEDDING_PROVIDER` | `voyage` | `voyage`, or `fake` (deterministic vectors, no network; for tests). |
| `EMBEDDING_MODEL` | `voyage-4` | Voyage model name. |
| `EMBEDDING_DIMENSIONS` | `1024` | Vector size; must match the database column, and at most 2000 (pgvector HNSW limit). |
| `VOYAGE_API_KEY` | *(required with `voyage`)* | Voyage AI API key. |
| `VOYAGE_BASE_URL` | `https://api.voyageai.com/v1` | Voyage API base URL. |
| `EMBEDDING_BATCH_SIZE` | `128` | Texts per embedding request (Voyage allows at most 1000). |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Timeout per embedding request. |
| `EMBEDDING_MAX_RETRIES` | `3` | Retries on `429`, `5xx`, timeouts and connection errors, with exponential backoff and jitter. Other errors fail at once. |

## Language model

Language model settings (through [OpenRouter](https://openrouter.ai)), used by the
copilot endpoints. None of them is required: the app starts and everything else works
without a key, which is only needed when a model is called.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openrouter` | The only provider for now. |
| `OPENROUTER_API_KEY` | *(unset)* | OpenRouter API key. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL. |
| `LLM_MODEL` | `mistralai/mistral-small-3.2-24b-instruct` | Default model (OpenRouter id); each call can override it. Provisional, to confirm with the tool-calling check. |
| `LLM_TEMPERATURE` | `0.2` | Sent with every call (0 to 2), because upstream providers' own defaults differ. Low, so tool calls are consistent. |
| `LLM_MAX_TOKENS` | `1024` | Maximum output tokens per call; reasoning tokens count against it. |
| `LLM_TIMEOUT_SECONDS` | `60` | Read timeout per request. |
| `LLM_MAX_RETRIES` | `2` | Retries on timeouts, connection errors, `408`, `429` and `5xx` (also when OpenRouter reports them inside a `200`), waiting as `Retry-After` asks or with exponential backoff and jitter (at most 10 s). `400`, `401`, `402` and `403` fail at once. |
| `LLM_RETRY_BUDGET_SECONDS` | `90` | No wait or retry that would end past this many seconds after the first attempt: the call fails at once instead (a running request still gets its full read timeout). |
| `LLM_DATA_COLLECTION` | `deny` | `deny` routes only to upstream providers that neither store nor train on prompts, which will hold customer content. `allow` lifts that. |
| `LLM_ZDR` | `false` | `true` routes only to Zero Data Retention endpoints: stricter, but fewer providers per model. |
| `LLM_REASONING_EFFORT` | *(unset: the model's default)* | `none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`. Reasoning tokens are billed as output; `none` turns reasoning off where the model allows it. |
| `LLM_APP_URL`, `LLM_APP_TITLE` | *(unset)* | Optional OpenRouter attribution headers (`HTTP-Referer`, `X-OpenRouter-Title`). |

## Conversation engine

Conversation engine settings, used by the copilot endpoints (see [copilot.md](copilot.md)). None is required. Invalid values (an unknown phase, a time zone that does not exist,
malformed JSON) stop the app at startup.

| Variable | Default | Description |
|---|---|---|
| `RETRIEVAL_PHASES` | `analyse` | Comma-separated phases whose turns search the knowledge base: `understand`, `challenge`, `analyse`, `action`, `followup`. Empty: no phase searches. |
| `RETRIEVAL_TOP_K` | `5` | Chunks retrieved per turn, 1 to 50. |
| `RETRIEVAL_MIN_SIMILARITY` | *(unset: keep all)* | Drop retrieved chunks below this similarity, 0 to 1. No validated value yet. |
| `COMMON_TENANT` | `ayo` | Tenant searched together with the case's own: the shared knowledge. Never another customer's. |
| `CONTEXT_MAX_MESSAGES` | `12` | Messages of the current phase sent to the model, at most. |
| `MAX_TOOL_ROUNDS` | `6` | Model calls per turn, at most. |
| `MAX_PHASE_HOPS` | `1` | Phase changes accepted within one turn; `0`: the phase only changes between messages. |
| `TURN_TIMEOUT_SECONDS` | `90` | Time budget per turn, checked between model calls (a call in flight has the LLM timeouts). |
| `MAX_USER_MESSAGE_CHARS` | `4000` | Longest user message accepted. |
| `FIELD_MAX_CHARS` | `500` | Each case fact is cut to this length when shown to the model. |
| `PROMPTS_VERSION` | `draft-1` | Recorded in every turn trace. Bump it whenever the prompt files change. 1 to 64 characters, no spaces. |
| `APP_TIMEZONE` | `Europe/Madrid` | IANA time zone of "today" for the model (so "el viernes" becomes a date). |
| `LLM_MODEL_BY_PHASE` | *(empty)* | Optional JSON mapping a phase to a model, such as `{"analyse": "<model id>"}`; phases without an entry use `LLM_MODEL`. |
| `SUMMARY_MODEL` | *(unset: `LLM_MODEL`)* | Model of the case summary (`POST /admin/cases/{case_id}/summary`); `GET /admin/settings` reports the one in use. |
| `SUMMARY_MAX_TOKENS` | `800` | Output cap of the case summary. |
| `SUMMARY_MAX_MESSAGES` | `40` | Latest messages the summary is given, besides the whole case record. |
| `SUMMARY_PROMPTS_VERSION` | `summary-draft-1` | Stored with each summary. Bump it whenever `summary.md` changes. 1 to 64 characters, no spaces. |

The prompt files are not settings: see
[Editing the prompt files](copilot.md#editing-the-prompt-files).

## Browser clients (CORS)

A UI served from another origin needs `CORS_ALLOWED_ORIGINS`, for example
`CORS_ALLOWED_ORIGINS=https://admin.example.com`. The admin UI's `pnpm dev` and
`pnpm preview` don't: they proxy the API's paths, so the UI and the API share one origin
([ui/README.md](../ui/README.md#setup)). Listed origins may use `GET`, `POST`,
`PATCH` and `DELETE` with the `X-API-Key` and `Content-Type` headers; no cookies or other
credentials. Any other origin gets no CORS headers, so the browser keeps the answers from
it. The setting is read when the app is built, so changing it needs a restart.

The API key is sent by the browser, so anyone using the UI can see it: fine for internal
or development use, not for a public UI (real authentication will replace the key).
