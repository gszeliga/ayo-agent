# Operations

Running the service against real infrastructure: a Neon dev branch, a psql shell on the
app's databases, and the service status. Settings are in
[configuration.md](configuration.md).

## Against a Neon dev branch

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

Neon closes idle connections (the pooler's idle timeout, the compute suspending after a
few idle minutes). The app's pool checks each connection before handing it out and
replaces a closed one, and closes its own after 4 idle minutes, so a request after a quiet
spell does not fail with `SSL connection has been closed unexpectedly`. The check costs one
round-trip per request; `DB_LOG_LEVEL=WARNING` still shows `discarding closed connection`
when it replaces one.

## A psql shell

```sh
scripts/db_shell.sh                  # local dev DB (localhost:5433)
scripts/db_shell.sh remote           # DATABASE_URL (shell, then .env), read-only
scripts/db_shell.sh migrations       # MIGRATIONS_DATABASE_URL, read-only
scripts/db_shell.sh remote --write   # read-write; asks you to type the host first
scripts/db_shell.sh remote -- -c 'select count(*) from documents'   # extra psql args after --
```

Needs `psql`. The URL goes to psql as `PG*` variables, so the password never shows in `ps`.
Read-only is enforced by the server (`default_transaction_read_only` as a startup option)
and uses the direct endpoint, because Neon's pooler rejects startup options.

## Service status

```sh
H="X-API-Key: $ADMIN_API_KEY"
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

## Logs

`ayo-copilot` logs to the console: the app's own lines (ids, tenants, counts, durations,
never document or conversation content) and uvicorn's access log, one line per request
with the client, method, path and status. **The access log drops the query string**
(`src/ayo_copilot/access_log.py`), because a query can carry content: `GET
/admin/cases?q=...` searches case text, and is logged as `"GET /admin/cases HTTP/1.1" 200`.
A proxy or platform in front of the service keeps its own access log; configure it not to
record query strings either.

At startup the app logs the database's schema revision (Alembic's `alembic_version`)
against the one the code expects (`SCHEMA_REVISIONS` in `src/ayo_copilot/db/schema.py`):

```text
database schema: revision 0004 (current)
database schema: revision 0003, outdated (code expects 0004): run `uv run alembic upgrade head`
database schema: revision 0005 unknown to this code (expects 0004): the database is newer
  than the code, or was migrated from another branch
database schema: no Alembic revision recorded: run `uv run alembic upgrade head`
```

All but the first are warnings, and the app still starts: an outdated schema fails only
where the code needs what is missing. A database without the `chunks` table stops startup
as before. Against Neon, run the migrations on the direct endpoint (see above).
