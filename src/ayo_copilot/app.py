import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from psycopg_pool import ConnectionPool, PoolTimeout

from ayo_copilot.config import Settings, database_host, default_env_file
from ayo_copilot.db.pool import open_pool, set_db_log_level
from ayo_copilot.db.repository import embedding_dimensions
from ayo_copilot.errors import install_error_handlers
from ayo_copilot.ingestion.embedding import build_embedder
from ayo_copilot.routers import admin

logger = logging.getLogger(__name__)

# Generous, because a Neon compute that scaled to zero takes a few seconds to wake up.
POOL_OPEN_TIMEOUT_SECONDS = 30.0


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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Settings are read from the environment at startup unless given."""
    app = FastAPI(title="AYO Copilot API", lifespan=_make_lifespan(settings))
    install_error_handlers(app)
    app.include_router(admin.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
