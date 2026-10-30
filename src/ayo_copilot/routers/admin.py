"""Admin endpoints: upload, list and inspect knowledge documents.

Authentication is **provisional**: one shared key in `ADMIN_API_KEY`, sent as `X-API-Key`.
It will be replaced by real identity and per-tenant authorization.
"""

import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, Security, UploadFile
from fastapi import Path as PathParam
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import DEFAULT_SORT
from ayo_copilot.dependencies import get_embedder, get_pool, get_settings
from ayo_copilot.documents import read_document, read_document_page, read_markdown
from ayo_copilot.errors import ApiError
from ayo_copilot.ingestion.embedding import Embedder, EmbeddingError
from ayo_copilot.ingestion.service import ingest_document
from ayo_copilot.ingestion.signatures import DOC_ID_PATTERN
from ayo_copilot.ingestion.storage import TENANT_PATTERN, InvalidInputError
from ayo_copilot.schemas import (
    DOCUMENT_EXAMPLE,
    Document,
    DocumentPage,
    DocumentSort,
    ErrorResponse,
    IngestResponse,
)

logger = logging.getLogger(__name__)

# Room for the boundaries and the small form fields around the file in a multipart body.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

_api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="AdminApiKey",
    description="Provisional shared admin key (`ADMIN_API_KEY`).",
    auto_error=False,
)


def _error(type: str, loc: list[str | int], msg: str, **extra: object) -> dict[str, object]:
    return {"detail": [{"type": type, "loc": loc, "msg": msg, **extra}]}


def _examples(**examples: tuple[str, dict[str, object]]) -> dict[str, object]:
    """OpenAPI `content` with named JSON examples: name -> (summary, value)."""
    return {
        "application/json": {
            "examples": {
                name: {"summary": summary, "value": value}
                for name, (summary, value) in examples.items()
            }
        }
    }


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
    tags=["documents"],
    dependencies=[Depends(require_admin_key)],
    route_class=UploadLimitRoute,
    responses={
        401: {
            "model": ErrorResponse,
            "description": "`X-API-Key` is missing or wrong.",
            "content": _examples(
                invalid_api_key=(
                    "Missing or wrong key",
                    _error(
                        "invalid_api_key", ["header", "x-api-key"], "invalid or missing API key"
                    ),
                )
            ),
        }
    },
)

INDEXED = {
    "doc_id": "upload-1890b5dc5335",
    "status": "indexed",
    "chunk_count": 12,
    "embedding_model": "voyage-4",
    "embed_signature": "17047d562b7e",
}

UPLOAD_DESCRIPTION = """Index one Markdown file for a tenant, so the copilot can retrieve it.

The file is split into chunks along its headings (each chunk keeps its heading path),
each chunk is embedded, and the document, its Markdown and its chunks are stored in one
transaction. A document is identified by `tenant` + `source_key` (by default the file
name): uploading it again replaces its previous version.

**Idempotent.** If the content and the chunking and embedding settings are the same as
the stored version, nothing is done and the answer is `200 up_to_date`, without calling
the embedding provider. Send `force=true` to reindex anyway.

| Status | Meaning |
|---|---|
| `201` | Indexed (new document, or a changed one). |
| `200` | Already up to date: nothing was done. |
| `401` | `X-API-Key` missing or wrong. |
| `413` | The file is larger than `MAX_UPLOAD_BYTES` (default 5 MiB). |
| `422` | Not a `.md` file, not UTF-8, empty, nothing to index, or an invalid field. |
| `502` | The embedding provider failed after retries. Nothing was stored. |

Errors use the API's error format (see the API description) and are told apart by
`detail[].type`.
"""


@router.post(
    "/documents",
    status_code=201,
    operation_id="upload_document",
    summary="Upload a Markdown document",
    description=UPLOAD_DESCRIPTION,
    response_model_exclude_none=True,
    responses={
        201: {
            "description": "Indexed: the document was chunked, embedded and stored.",
            "content": _examples(indexed=("Indexed", INDEXED)),
        },
        200: {
            "model": IngestResponse,
            "description": "Already up to date: same content and settings, nothing was done.",
            "content": _examples(
                up_to_date=(
                    "Up to date",
                    {"doc_id": "upload-1890b5dc5335", "status": "up_to_date"},
                )
            ),
        },
        413: {
            "model": ErrorResponse,
            "description": "The file is larger than `MAX_UPLOAD_BYTES`.",
            "content": _examples(
                file_too_large=(
                    "File too large",
                    _error("file_too_large", ["body", "file"], "file exceeds 5242880 bytes"),
                )
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "The file or a field is not acceptable. `type` is one of"
            " `file_extension`, `file_encoding`, `file_empty`, `file_no_content`,"
            " `source_key_invalid`, or a FastAPI validation code such as `missing` or"
            " `string_pattern_mismatch`.",
            "content": _examples(
                file_extension=(
                    "Not a .md file",
                    _error("file_extension", ["body", "file"], "file must have a .md extension"),
                ),
                file_encoding=(
                    "Not UTF-8",
                    _error("file_encoding", ["body", "file"], "file is not valid UTF-8"),
                ),
                file_no_content=(
                    "Nothing to index",
                    _error("file_no_content", ["body", "file"], "file has no indexable content"),
                ),
                missing=(
                    "Missing field (FastAPI validation)",
                    _error("missing", ["body", "tenant"], "Field required", input=None),
                ),
                string_pattern_mismatch=(
                    "Invalid tenant (FastAPI validation)",
                    _error(
                        "string_pattern_mismatch",
                        ["body", "tenant"],
                        f"String should match pattern '{TENANT_PATTERN}'",
                        input="Acme Corp",
                        ctx={"pattern": TENANT_PATTERN},
                    ),
                ),
            ),
        },
        502: {
            "model": ErrorResponse,
            "description": "The embedding provider failed after retries. Nothing was stored;"
            " retrying later is safe.",
            "content": _examples(
                embedding_failed=(
                    "Provider failure",
                    _error("embedding_failed", [], "embedding provider failed"),
                )
            ),
        },
    },
)
def upload_document(
    response: Response,
    file: Annotated[UploadFile, File(description="The Markdown file (`.md`, UTF-8).")],
    tenant: Annotated[
        str,
        Form(
            pattern=TENANT_PATTERN,
            description="Tenant (plant or customer) the document belongs to: lowercase"
            " letters, digits and hyphens, 2 to 63 characters.",
            examples=["acme"],
        ),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    title: Annotated[
        str | None,
        Form(
            description="Title to store. Default: the first `# ` heading, else the file name.",
            examples=["PRO-014 Control de sellado"],
        ),
    ] = None,
    source_key: Annotated[
        str | None,
        Form(
            description="Name that identifies the document within the tenant; an upload with"
            " the same one replaces it. Paths are reduced to their last component. Default:"
            " the file name.",
            examples=["pro-014-control-sellado.md"],
        ),
    ] = None,
    force: Annotated[
        bool,
        Form(description="Reindex even when the stored version is up to date."),
    ] = False,
) -> IngestResponse:
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


DOC_ID_PARAM = (
    "Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`."
)
NOT_FOUND = _error("document_not_found", ["path", "doc_id"], "document not found")
NOT_FOUND_RESPONSE: dict[str, object] = {
    "model": ErrorResponse,
    "description": "No document has this `doc_id`.",
    "content": _examples(document_not_found=("Unknown document", NOT_FOUND)),
}
DOC_ID_422_RESPONSE: dict[str, object] = {
    "model": ErrorResponse,
    "description": "`doc_id` is not a document id (FastAPI validation): it never matches"
    " a document.",
    "content": _examples(
        string_pattern_mismatch=(
            "Malformed id",
            _error(
                "string_pattern_mismatch",
                ["path", "doc_id"],
                f"String should match pattern '{DOC_ID_PATTERN}'",
                input="pro-014.md",
                ctx={"pattern": DOC_ID_PATTERN},
            ),
        )
    ),
}


def _not_found() -> ApiError:
    return ApiError(404, "document_not_found", "document not found", ["path", "doc_id"])


LIST_DESCRIPTION = """List the stored documents, one page at a time, newest change first.

Filter by `tenant` and by `q`, a case-insensitive substring of the title or the source key
(`%` and `_` match themselves). `total` counts every match, so a client can page with
`offset` until it has `total` items; the order is stable across pages, even on ties.

Each item carries a `status` computed now against the current settings: `outdated` means
the chunking or embedding settings changed since the document was indexed.

| Status | Meaning |
|---|---|
| `200` | A page, possibly empty. |
| `401` | `X-API-Key` missing or wrong. |
| `422` | A query parameter is out of range or not allowed (FastAPI validation). |
"""


@router.get(
    "/documents",
    operation_id="list_documents",
    summary="List documents",
    description=LIST_DESCRIPTION,
    responses={
        200: {
            "description": "A page of documents.",
            "content": _examples(
                page=(
                    "One page",
                    {"items": [DOCUMENT_EXAMPLE], "total": 1, "limit": 25, "offset": 0},
                ),
                empty=("No match", {"items": [], "total": 0, "limit": 25, "offset": 0}),
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "A query parameter is not acceptable. `type` is a FastAPI validation"
            " code such as `literal_error` (unknown `sort`), `greater_than_equal` or"
            " `less_than_equal` (`limit`, `offset`) or `string_pattern_mismatch` (`tenant`).",
            "content": _examples(
                literal_error=(
                    "Unknown sort key",
                    _error(
                        "literal_error",
                        ["query", "sort"],
                        "Input should be 'updated_at', '-updated_at', 'created_at',"
                        " '-created_at', 'title', '-title', 'chunk_count' or '-chunk_count'",
                        input="size",
                        ctx={
                            "expected": "'updated_at', '-updated_at', 'created_at',"
                            " '-created_at', 'title', '-title', 'chunk_count' or"
                            " '-chunk_count'"
                        },
                    ),
                ),
                less_than_equal=(
                    "Page too large",
                    _error(
                        "less_than_equal",
                        ["query", "limit"],
                        "Input should be less than or equal to 100",
                        input="500",
                        ctx={"le": 100},
                    ),
                ),
            ),
        },
    },
)
def list_documents(
    settings: Annotated[Settings, Depends(get_settings)],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    tenant: Annotated[
        str | None,
        Query(
            pattern=TENANT_PATTERN,
            description="Only this tenant's documents.",
            examples=["acme"],
        ),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            max_length=200,
            description="Case-insensitive substring of the title or the source key.",
            examples=["sellado"],
        ),
    ] = None,
    sort: Annotated[
        DocumentSort,
        Query(
            description="Sort key; prefix `-` for descending. Ties are broken by an internal"
            " id, so the order is stable.",
            examples=["-updated_at"],
        ),
    ] = DEFAULT_SORT,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Page size, 1 to 100.", examples=[25])
    ] = 25,
    offset: Annotated[
        int, Query(ge=0, description="Number of matching documents to skip.", examples=[0])
    ] = 0,
) -> DocumentPage:
    rows, total = read_document_page(
        pool, tenant=tenant, q=q or None, sort=sort, limit=limit, offset=offset
    )
    return DocumentPage(
        items=[Document.from_row(row, settings) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


GET_DESCRIPTION = """One document, with the same fields as an item of the listing.

| Status | Meaning |
|---|---|
| `200` | The document. |
| `401` | `X-API-Key` missing or wrong. |
| `404` | No document has this `doc_id`. |
| `422` | `doc_id` is malformed (FastAPI validation). |
"""


@router.get(
    "/documents/{doc_id}",
    operation_id="get_document",
    summary="Get a document",
    description=GET_DESCRIPTION,
    responses={
        200: {
            "description": "The document.",
            "content": _examples(document=("A document", DOCUMENT_EXAMPLE)),
        },
        404: NOT_FOUND_RESPONSE,
        422: DOC_ID_422_RESPONSE,
    },
)
def get_document(
    doc_id: Annotated[
        str,
        PathParam(
            pattern=DOC_ID_PATTERN, description=DOC_ID_PARAM, examples=["upload-1890b5dc5335"]
        ),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
) -> Document:
    row = read_document(pool, doc_id)
    if row is None:
        raise _not_found()
    return Document.from_row(row, settings)


CONTENT_DESCRIPTION = """The stored Markdown, as `text/markdown; charset=utf-8`.

It is the uploaded file after normalization (no byte order mark, LF line endings), so its
SHA-256 is the document's `content_hash`. Errors are JSON, like everywhere else.

| Status | Meaning |
|---|---|
| `200` | The Markdown. |
| `401` | `X-API-Key` missing or wrong. |
| `404` | No document has this `doc_id`. |
| `422` | `doc_id` is malformed (FastAPI validation). |
"""

MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"
MARKDOWN_EXAMPLE = (
    "# PRO-014 Control de sellado\n\n## Paso 1\n\nComprobar la presión de la junta antes"
    " de cada turno y anotar el valor en el registro.\n"
)


@router.get(
    "/documents/{doc_id}/content",
    operation_id="get_document_content",
    summary="Get a document's Markdown",
    description=CONTENT_DESCRIPTION,
    # Plain `Response`: no JSON 200 is documented, and the errors stay `application/json`.
    response_class=Response,
    responses={
        200: {
            "description": "The stored Markdown.",
            "content": {
                MARKDOWN_MEDIA_TYPE: {
                    "schema": {"type": "string"},
                    "examples": {"markdown": {"summary": "A procedure", "value": MARKDOWN_EXAMPLE}},
                }
            },
        },
        404: NOT_FOUND_RESPONSE,
        422: DOC_ID_422_RESPONSE,
    },
)
def get_document_content(
    doc_id: Annotated[
        str,
        PathParam(
            pattern=DOC_ID_PATTERN, description=DOC_ID_PARAM, examples=["upload-1890b5dc5335"]
        ),
    ],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
) -> Response:
    markdown = read_markdown(pool, doc_id)
    if markdown is None:
        raise _not_found()
    return Response(markdown, media_type=MARKDOWN_MEDIA_TYPE)
