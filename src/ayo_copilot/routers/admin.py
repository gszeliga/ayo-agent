"""Admin endpoints: knowledge upload.

Authentication is **provisional**: one shared key in `ADMIN_API_KEY`, sent as `X-API-Key`.
It will be replaced by real identity and per-tenant authorization.
"""

import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, Security, UploadFile
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.dependencies import get_embedder, get_pool, get_settings
from ayo_copilot.errors import ApiError
from ayo_copilot.ingestion.embedding import Embedder, EmbeddingError
from ayo_copilot.ingestion.service import ingest_document
from ayo_copilot.ingestion.storage import InvalidInputError
from ayo_copilot.schemas import IngestResponse

logger = logging.getLogger(__name__)

# Room for the boundaries and the small form fields around the file in a multipart body.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_admin_key(
    key: Annotated[str | None, Security(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    expected = settings.admin_api_key.get_secret_value().encode()
    # Bytes, because compare_digest refuses non-ASCII str.
    if key is None or not secrets.compare_digest(key.encode(), expected):
        raise ApiError(
            401,
            "invalid_api_key",
            "invalid or missing API key",
            ["header", "x-api-key"],
            headers={"WWW-Authenticate": "APIKey"},
        )


def _too_large(max_bytes: int) -> ApiError:
    return ApiError(413, "file_too_large", f"file exceeds {max_bytes} bytes", ["body", "file"])


class UploadLimitRoute(APIRoute):
    """Rejects a too-large `Content-Length` before FastAPI parses the multipart body.

    Without the header (chunked uploads) the endpoint's own read limit still applies.
    Either way Starlette buffers what it receives, so this protects processing, not
    bandwidth: a hard cap belongs in the proxy in front of the app.
    """

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def limited_handler(request: Request) -> Response:
            max_bytes = request.state.settings.max_upload_bytes
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > max_bytes + MULTIPART_OVERHEAD_BYTES:
                raise _too_large(max_bytes)
            return await handler(request)

        return limited_handler


router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_admin_key)],
    route_class=UploadLimitRoute,
)


@router.post("/documents", status_code=201)
def upload_document(
    response: Response,
    file: Annotated[UploadFile, File()],
    tenant: Annotated[str, Form()],
    settings: Annotated[Settings, Depends(get_settings)],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    title: Annotated[str | None, Form()] = None,
    source_key: Annotated[str | None, Form()] = None,
    force: Annotated[bool, Form()] = False,
) -> IngestResponse:
    """Index a Markdown file: 201 when (re)indexed, 200 when already up to date."""
    filename = file.filename or ""
    if not filename.lower().endswith(".md"):
        raise ApiError(422, "file_extension", "file must have a .md extension", ["body", "file"])

    # Sync endpoint (runs in the threadpool), so read the spooled file directly.
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise _too_large(settings.max_upload_bytes)

    try:
        result = ingest_document(
            settings=settings,
            pool=pool,
            embedder=embedder,
            tenant=tenant,
            filename=filename,
            content=content,
            title=title,
            source_key=source_key,
            force=force,
        )
    except InvalidInputError as exc:
        # Without a source_key, the service derives it from the file name.
        field = "file" if exc.field == "source_key" and source_key is None else exc.field
        raise ApiError(422, exc.code, str(exc), ["body", field]) from None
    except EmbeddingError as exc:
        # The cause stays in the log; provider messages carry no document content.
        logger.warning("embedding failed tenant=%s: %s", tenant, exc)
        raise ApiError(502, "embedding_failed", "embedding provider failed") from None

    if result.status == "up_to_date":
        response.status_code = 200
    return IngestResponse.from_result(result)
