import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool, PoolTimeout

from ayo_copilot.config import BuildSettings, Settings, database_host, default_env_file
from ayo_copilot.conversation.prompt_files import PromptError, PromptSet, load_prompts
from ayo_copilot.db.pool import open_pool, set_db_log_level
from ayo_copilot.db.repository import embedding_dimensions
from ayo_copilot.errors import install_error_handlers
from ayo_copilot.health import EmbeddingMonitor, TrackedEmbedder
from ayo_copilot.ingestion.embedding import (
    Embedder,
    FakeEmbedder,
    VoyageEmbedder,
    build_embedder,
)
from ayo_copilot.llm.build import build_llm_provider, describe_llm_provider
from ayo_copilot.routers import admin, copilot
from ayo_copilot.schemas import HealthResponse

logger = logging.getLogger(__name__)

# Generous, because a Neon compute that scaled to zero takes a few seconds to wake up.
POOL_OPEN_TIMEOUT_SECONDS = 30.0

API_DESCRIPTION = """\
Backend of the AYO Plant Copilot, an AI agent that guides industrial plant teams through
structured problem solving. This API loads the plant knowledge (procedures, manuals) the
copilot retrieves from, and searches it the way the copilot will; the `/copilot`
endpoints talk to the copilot itself.

## Authentication

The `/admin` and `/copilot` endpoints need the header `X-API-Key`. In this page, click
**Authorize** and paste the key, then use **Try it out**. The key is **provisional**: one
shared key, to be replaced by real user identity and per-tenant permissions.

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
| `session_not_found` | 404 | `["path", "session_id"]` |
| `tenant_mismatch` | 422 | `["body", "tenant"]` |
| `case_closed`, `case_changed` | 409 | `[]` |
| `llm_unavailable`, `llm_rate_limited`, `llm_credits`, `llm_auth`, `llm_error` | 502 | `[]` |
| `llm_not_configured` | 503 | `[]` |
| `document_changed` | 409 | `[]` |
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
    {
        "name": "search",
        "description": "Try questions against the knowledge base: the chunks the copilot"
        " would retrieve, with their similarity.",
    },
    {
        "name": "settings",
        "description": "The current indexing settings and how the stored documents compare"
        " with them. Read-only; no secrets.",
    },
    {
        "name": "copilot",
        "description": "Talk to the copilot: send a session's messages, and inspect the"
        " session's case.",
    },
    {
        "name": "health",
        "description": "Liveness of the service (public), and the status of the database"
        " and the embedding provider (behind the key).",
    },
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
        prompts = _load_prompts(resolved)
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
            # Uploads, reprocesses and searches go through the tracker, so /admin/health can report
            # their last outcome; the monitor checks the provider itself, on demand.
            tracked = TrackedEmbedder(embedder)
            # No request and no key check here: without OPENROUTER_API_KEY the app still
            # starts, and only a model call fails (LLMConfigError, a 503 on /copilot).
            llm = build_llm_provider(resolved)
            logger.info("%s", describe_llm_provider(llm, resolved))
            try:
                # Endpoints read these through `request.state` (see dependencies.py).
                yield {
                    "settings": resolved,
                    "pool": pool,
                    "embedder": tracked,
                    "embedding_monitor": EmbeddingMonitor(embedder, tracked),
                    "llm": llm,
                    "prompts": prompts,
                }
            finally:
                # FakeEmbedder holds no resources and has no close().
                tracked.close()
                close = getattr(llm, "close", None)
                if close is not None:
                    close()
        finally:
            pool.close()

    return lifespan


def _load_prompts(settings: Settings) -> PromptSet:
    """Render the prompt files, or refuse to start (the error names the file only)."""
    try:
        prompts = load_prompts()
    except PromptError as error:
        raise StartupError(f"prompts: {error}") from None
    logger.info(
        "prompts: version=%s files=%d sha256=%s",
        settings.prompts_version,
        prompts.file_count,
        prompts.sha256[:12],
    )
    return prompts


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

    Only `BuildSettings` (docs, CORS) are read now, because FastAPI needs them up front.
    Passing `docs_enabled` without `settings` skips even that and leaves CORS off (tests,
    the OpenAPI export).
    """
    build: BuildSettings | None = settings
    if build is None and docs_enabled is None:
        build = BuildSettings()
    if docs_enabled is None:
        docs_enabled = build.docs_enabled
    cors_origins = build.cors_allowed_origins if build is not None else []
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
    if cors_origins:
        # Answers preflights before routing, so they need no API key; errors get the
        # headers too, so the UI can read them.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type"],
            allow_credentials=False,
        )
        logger.info("CORS allowed origins: %s", ", ".join(cors_origins))
    install_error_handlers(app)
    app.include_router(admin.router)
    app.include_router(copilot.router)

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
