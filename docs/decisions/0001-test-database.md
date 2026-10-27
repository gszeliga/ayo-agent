# 0001: Local database for integration tests

- Status: accepted (2026-10-22)
- Date: 2026-10-22

## Context

The ingestion pipeline stores chunks in Postgres with pgvector and relies on
features specific to them: the `vector` type, the `<=>` cosine distance
operator, HNSW indexes, `ON CONFLICT`, transactional chunk replacement, and
later `FOR UPDATE SKIP LOCKED` for the worker queue. Integration tests need a
real database that behaves like production (Neon). Unit and API tests must not
need a database at all.

What this machine has (checked on 2026-10-22):

| Tool | Status |
|---|---|
| Docker | 29.7.2, daemon running |
| Docker Compose | **not installed** (`docker compose` is an unknown command, no `docker-compose`) |
| psql / PostgreSQL | 18.6, installed locally; pgvector is **not** installed in it |
| Python | 3.12.0 |
| uv | 0.13.1 |

Current versions: pgvector 0.8.7 (Docker image `pgvector/pgvector:0.8.7-pg18-trixie`,
published 2026-10-01), testcontainers 4.15.0, pytest-postgresql 9.1.1,
pgserver 0.1.4, sqlite-vec 0.1.9.

## Options

### 1. Docker Compose with `pgvector/pgvector`

A `compose.yaml` with a dev database and a test database.

- Fidelity: full (real Postgres plus pgvector, same image family as many hosted setups).
- Startup: the container stays up between runs, so test runs pay no startup cost.
- Without Docker: no.
- CI: maps directly onto a GitHub Actions `services:` container.
- Isolation: up to the test fixtures.
- Here: **Compose is not installed**. It would need an extra package (`docker-compose`) for little gain over a plain `docker run`.

### 2. testcontainers-python

`PostgresContainer("pgvector/pgvector:0.8.7-pg18-trixie")` is started once per
pytest session and thrown away afterwards.

- Fidelity: full, the same image as option 1.
- Startup: a few seconds per test session once the image is pulled (the first pull is a one-time download of about 150 MB). Not measured here yet.
- Without Docker: no. It needs the Docker daemon only, **not Compose**.
- CI: works on GitHub's Ubuntu runners, which ship Docker; no `services:` block needed.
- Isolation: a fresh database every session, so no leftover state between runs; per-test isolation is still up to the fixtures.
- With uv: just a dev dependency (`testcontainers[postgres]`). `uv run pytest` is the only command.
- Here: **works** (Docker daemon is running).

### 3. pytest-postgresql

Starts a temporary Postgres from locally installed binaries (`postgresql_proc`).

- Fidelity: full, **if** pgvector is compiled against the local Postgres. Here PostgreSQL 18.6 is installed without pgvector. On Manjaro, pgvector would have to come from a distro/AUR package or a source build (`make && sudo make install`). I did not check which; **unverified**.
- Startup: fast (`initdb` plus start, about 1–2 s).
- Without Docker: yes. This is its main advantage.
- CI: needs Postgres and pgvector installed on the runner (apt `postgresql-18-pgvector` from PGDG), which adds setup steps.
- Ties the test environment to whatever Postgres version the host OS ships, which can drift from production.

### 4. pgserver (pip-installable embedded Postgres)

- Its README says it bundles Postgres binaries plus pgvector for Linux, macOS and Windows.
- Maintenance: last release 0.1.4 on 2024-06-08, and no pushes to the repo since 2024-06. **Looks unmaintained**; the bundled Postgres/pgvector versions are over two years old (pgvector has shipped several releases since, now 0.8.7).
- Verdict: attractive idea, but too stale to rely on.

### 5. SQLite with a vector extension (sqlite-vec)

Verified rather than assumed:

- sqlite-vec is pre-v1 ("expect breaking changes"). Vectors live in `vec0` virtual tables, not in a column type on a normal table, so the `chunks` table would need a different design.
- No `vector` type, no `<=>` operator, no `vector_cosine_ops`, no HNSW. Approximate-nearest-neighbour (ANN) indexes (IVF, DiskANN, rescore) are being added as experimental features.
- `ON CONFLICT` exists in SQLite, but with different semantics around partial indexes. There is no row-level locking, so no `FOR UPDATE SKIP LOCKED`. Transactions lock the whole database.
- `uuid`, `jsonb`, `timestamptz` and `gen_random_uuid()` do not exist.
- Verdict: **not viable**. Every query and the migrations would need a second dialect, and the tests would prove nothing about the production SQL.

### 6. Hosted database (a Neon branch) for CI only

- Fidelity: highest, since it is the production provider.
- Cost: network dependency on every CI run, cold starts (compute scales to zero after 5 min), credentials stored in CI, free-plan limits (10 branches per project, 100 CU-hours/month, 0.5 GB).
- Risk: CI turns flaky when Neon or the network has trouble, and a misconfigured URL could point tests at production. Neon is our production environment, so test tooling should stay away from it.
- Verdict: not as the default. Maybe later for a nightly smoke test against a dedicated branch.

## Comparison

| Criterion | Compose | testcontainers | pytest-postgresql | pgserver | sqlite-vec | Neon branch |
|---|---|---|---|---|---|---|
| Production fidelity (pgvector, HNSW, locking) | full | full | full if pgvector installed | old versions | no | full |
| Startup | none (already running) | ~seconds / session | ~1–2 s | ~1–2 s | instant | network + cold start |
| Works without Docker | no | no | yes | yes | yes | yes |
| CI fit | service container | runs as is | extra install steps | pip only | pip only | secrets + network |
| Isolation | fixtures | fresh DB per session | fresh DB per session | fresh DB per session | file per test | branch per run |
| Works on this machine now | no (no Compose) | **yes** | not without installing pgvector | unknown | yes, but useless | yes |

## Decision

**testcontainers** with `pgvector/pgvector:0.8.7-pg18-trixie` for integration
tests, plus a plain `docker run` script for the dev database. No Compose.

- Integration tests get a session-scoped fixture that starts the container
  and runs `alembic upgrade head` once.
- The fixture **skips** every `@pytest.mark.integration` test with a clear
  message ("Docker is not available: integration tests skipped") when the
  Docker daemon can't be reached. Unit and API suites never touch it.
- Escape hatch: if `TEST_DATABASE_URL` is set, the fixture uses that database
  instead of starting a container (for example a CI service container, or a
  machine without Docker). It refuses to run if the URL host looks like Neon,
  to protect production.
- Dev database: `scripts/dev_db.sh up|down` runs the same image as a
  long-lived container with a named volume on port 5433. Port 5433 avoids a
  clash with the locally installed Postgres on 5432.

### Per-test isolation: truncation

Each integration test runs against the shared session database, and an
autouse fixture runs `TRUNCATE documents, chunks RESTART IDENTITY CASCADE`
**before** each test. `KNOWLEDGE_DIR` points to pytest's `tmp_path`.

> Implementation note (step 5b): the truncation lives in the `db_pool` fixture
> rather than an autouse one. The shared database is only reachable through
> `db_pool`, so every test that uses it still starts with empty tables, and
> tests that don't use it don't trigger the truncation.

Why not wrap each test in a transaction and roll it back: the code under test
opens its own transactions from the pool and commits them, and two of the
tests check exactly that behaviour (atomic chunk replacement, nothing written
when the provider fails, concurrent uploads). An outer rollback transaction
would hide the real commit semantics, or force the repository to accept an
injected connection only for tests. Truncating two tables takes milliseconds.
A schema per test would add migration time to every test for no extra benefit.

The migration tests (upgrade from scratch, downgrade) use their own
throwaway database, created inside the same container, so they don't disturb the shared schema.

### Commands (to be documented in the README)

```sh
scripts/dev_db.sh up               # start the dev database (docker run, port 5433)
uv run alembic upgrade head        # apply migrations to the dev database
uv run pytest                      # unit + API; integration via testcontainers or skipped
uv run pytest -m "not integration" # explicitly without a database
```

## Consequences

- Docker is required to run integration tests locally. Without Docker they are
  skipped, not failed. `TEST_DATABASE_URL` or pytest-postgresql (after
  installing pgvector) remain fallbacks.
- Dev and test use Postgres 18, as agreed.
