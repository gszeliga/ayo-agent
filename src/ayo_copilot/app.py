import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from psycopg_pool import ConnectionPool, PoolTimeout

from ayo_copilot.config import DocsSettings, Settings, database_host, default_env_file
from ayo_copilot.db.pool import open_pool, set_db_log_level
from ayo_copilot.db.repository import embedding_dimensions
from ayo_copilot.errors import install_error_handlers
from ayo_copilot.ingestion.embedding import (
    Embedder,
    FakeEmbedder,
    VoyageEmbedder,
    build_embedder,
)
from ayo_copilot.routers import admin
from ayo_copilot.schemas import HealthResponse

logger = logging.getLogger(__name__)

# Generous, because a Neon compute that scaled to zero takes a few seconds to wake up.
POOL_OPEN_TIMEOUT_SECONDS = 30.0

API_DESCRIPTION = """\
Backend of the AYO Plant Copilot, an AI agent that guides industrial plant teams through
structured problem solving. This API loads the plant knowledge (procedures, manuals) the
copilot retrieves from.

## Authentication

The `/admin` endpoints need the header `X-API-Key`. In this page, click **Authorize** and
paste the key, then use **Try it out**. The key is **provisional**: one shared key, to be
replaced by real user identity and per-tenant permissions.

## Errors

Every error has the same body, the shape FastAPI uses for request validation errors:

```json
{"detail": [{"type": "file_empty", "loc": ["body", "file"], "msg": "file is empty"}]}
```

Branch on `type`, a stable code; `msg` is for humans. `loc` names the input at fault, or
is `[]`. Only FastAPI's own validation errors (such as `missing`) add `input` and `ctx`.

| `type` | Status | `loc` |
|---|---|---|
| `invalid_api_key` | 401 | `["header", "x-api-key"]` |
| `file_too_large` | 413 | `["body", "file"]` |
| `file_extension`, `file_encoding`, `file_empty`, `file_no_content` | 422 | `["body", "file"]` |
| `source_key_invalid` | 422 | `["body", "source_key"]` (`["body", "file"]` if derived) |
| FastAPI codes (`missing`, `string_pattern_mismatch`, `literal_error`, ...) | 422 | the field |
| `document_not_found` | 404 | `["path", "doc_id"]` |
| `embedding_failed` | 502 | `[]` |

Requests the framework rejects use the same body: a malformed body is `400 bad_request`,
an unknown path `404 not_found`, a wrong method `405 method_not_allowed`, and an
unexpected failure `500 internal_error`.
"""

OPENAPI_TAGS = [
    {
        "name": "documents",
        "description": "Upload, list and inspect the Markdown documents the copilot"
        " retrieves from.",
    },
    {"name": "health", "description": "Liveness of the service."},
]


class StartupError(RuntimeError):
    """The app cannot serve requests with this configuration and database."""


def _make_lifespan(
    settings: Settings | None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[dict]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
        if settings is None:
            env_file = default_env_file()
            if env_file.is_file():
                logger.info("settings: environment and %s", env_file)
            else:
                logger.info("settings: environment only, no file at %s", env_file)
        resolved = settings or Settings()
        set_db_log_level(resolved.db_log_level)
        host = database_host(resolved.database_url.get_secret_value())

        # Opening the pool blocks the event loop, which is fine before serving starts.
        try:
            pool = open_pool(
                resolved.database_url.get_secret_value(), timeout=POOL_OPEN_TIMEOUT_SECONDS
            )
        except PoolTimeout:
            # The pool logs the underlying error as a WARNING from `psycopg.pool`.
            raise StartupError(
                f"could not connect to the database at {host!r}: check DATABASE_URL and that"
                " the migrations ran (`uv run alembic upgrade head`)"
            ) from None
        try:
            _check_embedding_dimensions(pool, resolved.embedding_dimensions)
            logger.info("database ready at %r, vector(%d)", host, resolved.embedding_dimensions)
            embedder = build_embedder(resolved)
            _log_embedder(embedder, resolved)
            try:
                # Endpoints read these through `request.state` (see dependencies.py).
                yield {"settings": resolved, "pool": pool, "embedder": embedder}
            finally:
                # FakeEmbedder holds no resources and has no close().
                close = getattr(embedder, "close", None)
                if close is not None:
                    close()
        finally:
            pool.close()

    return lifespan


def _log_embedder(embedder: Embedder, settings: Settings) -> None:
    """Say which embedder was built (never the key). Fake vectors are useless for retrieval."""
    if isinstance(embedder, FakeEmbedder):
        logger.warning(
            "embedder: fake (deterministic vectors, no network) dimensions=%d:"
            " not for real retrieval",
            embedder.dimensions,
        )
    elif isinstance(embedder, VoyageEmbedder):
        logger.info(
            "embedder: voyage model=%s dimensions=%d batch_size=%d base_url=%s",
            embedder.model,
            embedder.dimensions,
            embedder.batch_size,
            settings.voyage_base_url,
        )
    else:
        logger.info("embedder: %s", type(embedder).__name__)


def _check_embedding_dimensions(pool: ConnectionPool, expected: int) -> None:
    with pool.connection() as conn:
        actual = embedding_dimensions(conn)
    if actual is None:
        raise StartupError(
            "table chunks not found: run the migrations (`uv run alembic upgrade head`)"
        )
    if actual != expected:
        raise StartupError(
            f"the database column chunks.embedding is vector({actual}) but"
            f" EMBEDDING_DIMENSIONS={expected}: add a migration or change the setting"
        )


def create_app(settings: Settings | None = None, *, docs_enabled: bool | None = None) -> FastAPI:
    """Build the app. Settings are read from the environment at startup unless given.

    Only `DOCS_ENABLED` is read now, because FastAPI needs the docs URLs up front; pass
    `docs_enabled` to skip even that (tests, the OpenAPI export).
    """
    if docs_enabled is None:
        docs_enabled = (settings or DocsSettings()).docs_enabled
    app = FastAPI(
        title="AYO Plant Copilot API",
        version=version("ayo-copilot"),
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=_make_lifespan(settings),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    install_error_handlers(app)
    app.include_router(admin.router)

    @app.get(
        "/health",
        tags=["health"],
        operation_id="health",
        summary="Check that the service is up",
        description="Answers as soon as the process serves requests. It does not check the"
        " database or the embedding provider.",
    )
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app
