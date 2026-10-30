"""Request and response bodies of the API. Every field is described for the OpenAPI docs."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import ChunkRow, DocumentRow
from ayo_copilot.ingestion.service import IngestResult, document_status

# The sort keys of `db.repository.SORT_KEYS`, each also with `-` for descending.
DocumentSort = Literal[
    "updated_at",
    "-updated_at",
    "created_at",
    "-created_at",
    "title",
    "-title",
    "chunk_count",
    "-chunk_count",
]


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(
        description="Always `ok` when the process is serving.", examples=["ok"]
    )


class IngestResponse(BaseModel):
    """The outcome of an upload. Sent without the optional fields when `up_to_date`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "doc_id": "upload-1890b5dc5335",
                    "status": "indexed",
                    "chunk_count": 12,
                    "embedding_model": "voyage-4",
                    "embed_signature": "17047d562b7e",
                }
            ]
        }
    )

    doc_id: str = Field(
        description="Stable id of the document, derived from the tenant and the source key.",
        examples=["upload-1890b5dc5335"],
    )
    status: Literal["indexed", "up_to_date"] = Field(
        description="`indexed`: chunked, embedded and stored (HTTP 201). `up_to_date`: the"
        " stored version has the same content and settings, nothing was done (HTTP 200).",
        examples=["indexed"],
    )
    chunk_count: int | None = Field(
        default=None,
        ge=1,
        description="Number of chunks stored. Only when `indexed`.",
        examples=[12],
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model used for the chunks. Only when `indexed`.",
        examples=["voyage-4"],
    )
    embed_signature: str | None = Field(
        default=None,
        description="First 12 hex characters of the signature that decides whether a later"
        " upload is `up_to_date`. Only when `indexed`.",
        examples=["17047d562b7e"],
    )

    @classmethod
    def from_result(cls, result: IngestResult) -> "IngestResponse":
        return cls(
            doc_id=result.doc_id,
            status=result.status,
            chunk_count=result.chunk_count,
            embedding_model=result.embedding_model,
            embed_signature=result.embed_signature,
        )


class ErrorItem(BaseModel):
    """One error. The items of FastAPI's `HTTPValidationError` have this shape too."""

    type: str = Field(
        description="Stable, machine-readable error code: branch on this, not on `msg`.",
        examples=["file_empty"],
    )
    loc: list[str | int] = Field(
        description='Where the error is: `["body", "<field>"]`, `["header", "x-api-key"]`,'
        " or `[]` when no single input is at fault.",
        examples=[["body", "file"]],
    )
    msg: str = Field(description="Human-readable explanation.", examples=["file is empty"])
    # Only FastAPI's request validation errors carry these; ours never echo input back.
    input: Any = Field(
        default=None,
        description="The rejected value. Request validation errors only.",
    )
    ctx: dict[str, Any] | None = Field(
        default=None,
        description="Extra details, such as the expected pattern. Request validation errors only.",
    )


class ErrorResponse(BaseModel):
    """The body of every error response."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "detail": [
                        {"type": "file_empty", "loc": ["body", "file"], "msg": "file is empty"}
                    ]
                }
            ]
        }
    )

    detail: list[ErrorItem] = Field(description="One or more errors.")


def _utc(value: datetime | None) -> datetime | None:
    """Timestamps come back in the session's time zone; the API always speaks UTC (`Z`)."""
    return value.astimezone(UTC) if value is not None else None


# Models with nullable fields carry examples per field only: FastAPI drops null values
# from object-level examples (`exclude_none` in `get_openapi`), so a whole-object example
# would lose them. Swagger builds the sample from the field examples, nulls included.


class Document(BaseModel):
    """A stored document, the same in the listing and on its own. `status` compares it with
    the current settings."""

    doc_id: str = Field(
        description="Stable id of the document, derived from the tenant and the source key.",
        examples=["upload-1890b5dc5335"],
    )
    tenant: str = Field(description="Tenant the document belongs to.", examples=["acme"])
    title: str | None = Field(
        description="Display title: given at upload, else the first `# ` heading, else the"
        " file name.",
        examples=["PRO-014 Control de sellado"],
    )
    source_key: str = Field(
        description="Name that identifies the document within the tenant. Uploading with the"
        " same `tenant` and `source_key` replaces it.",
        examples=["pro-014-control-sellado.md"],
    )
    status: Literal["indexed", "outdated"] = Field(
        description="`indexed`: processed with the current chunking and embedding settings."
        " `outdated`: the current settings would index it differently; reprocess or"
        " upload it again.",
        examples=["indexed"],
    )
    outdated_reason: Literal["chunker_changed", "embedder_changed", "unknown"] | None = Field(
        description="Why it is `outdated` (null when `indexed`): the chunking settings changed,"
        " the embedding model changed, or `unknown` (indexed before the settings were"
        " recorded). The chunker wins when both changed.",
        examples=[None],
    )
    chunk_count: int = Field(description="Number of stored chunks.", examples=[12])
    size_bytes: int | None = Field(
        description="Size of the stored Markdown in bytes (UTF-8, after normalization).",
        examples=[8421],
    )
    content_hash: str = Field(
        description="SHA-256 (hex) of the stored Markdown; equal hashes mean equal content.",
        examples=["9f2c1a7e5b0d4c3a8e6f1b2d7c9a0e4f3b5d8c1a2e7f6b9d0c4a3e8f5b1d2c7a"],
    )
    chunk_signature: str = Field(
        description="Hash of the content and `chunker_config`.",
        examples=["4e1b9c0d7a2f5e8b3c6d9a0f1e4b7c2d5a8f3e6b9c0d1a4f7e2b5c8d3a6f9e0b"],
    )
    embed_signature: str = Field(
        description="Hash of `chunk_signature` and `embedder_config`. An upload whose signature"
        " equals it is `up_to_date`.",
        examples=["17047d562b7e9a3c0f5d8b1e4a7c2f6d9b0e3a8c5f1d4b7e2a9c6f0d3b8e5a1c"],
    )
    chunker_config: str | None = Field(
        description="Chunking settings the document was processed with (null if indexed"
        " before they were recorded).",
        examples=[
            "md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1"
        ],
    )
    embedder_config: str | None = Field(
        description="Embedding model and dimensions the document was processed with (null if"
        " indexed before they were recorded).",
        examples=["voyage-4/document/1024"],
    )
    created_at: datetime = Field(
        description="First upload (UTC).", examples=["2026-10-15T09:30:00Z"]
    )
    updated_at: datetime = Field(
        description="Last change: upload or rename (UTC).", examples=["2026-10-15T09:30:00Z"]
    )
    chunked_at: datetime | None = Field(
        description="When the current chunks were made (UTC).",
        examples=["2026-10-15T09:30:01Z"],
    )
    embedded_at: datetime | None = Field(
        description="When the current chunks were embedded (UTC).",
        examples=["2026-10-15T09:30:04Z"],
    )

    @classmethod
    def from_row(cls, row: DocumentRow, settings: Settings) -> "Document":
        status, reason = document_status(row.chunker_config, row.embedder_config, settings)
        return cls(
            doc_id=row.doc_id,
            tenant=row.tenant,
            title=row.title,
            source_key=row.source_key,
            status=status,
            outdated_reason=reason,
            chunk_count=row.chunk_count,
            size_bytes=row.size_bytes,
            content_hash=row.content_hash,
            chunk_signature=row.chunk_signature,
            embed_signature=row.embed_signature,
            chunker_config=row.chunker_config,
            embedder_config=row.embedder_config,
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            chunked_at=_utc(row.chunked_at),
            embedded_at=_utc(row.embedded_at),
        )


class Page[T](BaseModel):
    """One page of a listing. Subclass it per item type, so OpenAPI gets a clean name."""

    items: list[T] = Field(description="The items of this page, possibly empty.")
    total: int = Field(
        description="Number of items matching the filters, across all pages.", examples=[42]
    )
    limit: int = Field(description="Page size requested.", examples=[25])
    offset: int = Field(description="Number of matching items skipped.", examples=[0])


class DocumentPage(Page[Document]):
    """A page of documents."""


class Chunk(BaseModel):
    """One stored chunk of a document."""

    chunk_index: int = Field(
        description="Position of the chunk in the document, from 0.", examples=[2]
    )
    heading: str | None = Field(
        description="Path of the Markdown headings the chunk sits under, joined with ` > `;"
        " null before the first heading.",
        examples=["PRO-014 Control de sellado > 3. Pasos"],
    )
    chunk_text: str = Field(
        description="The chunk's text. The text that was embedded is `heading`, a blank line"
        " and this text (only this text when `heading` is null).",
        examples=[
            "Comprobar la presión de la junta antes de cada turno y anotar el valor en el registro."
        ],
    )
    char_count: int = Field(
        description="Length of `chunk_text` in characters (not bytes).", examples=[86]
    )
    embedding: list[float] | None = Field(
        description="The stored vector, one float per dimension of the embedding model. Null"
        " unless `include_embedding=true`.",
        examples=[None],
    )

    @classmethod
    def from_row(cls, row: ChunkRow) -> "Chunk":
        return cls(
            chunk_index=row.chunk_index,
            heading=row.heading,
            chunk_text=row.chunk_text,
            char_count=row.char_count,
            embedding=row.embedding,
        )


class ChunkPage(Page[Chunk]):
    """A page of a document's chunks."""

    # Redeclared only for the example: the chunks' default page size is 50.
    limit: int = Field(description="Page size requested.", examples=[50])


class DocumentUpdate(BaseModel):
    """Changes to a document that need no reprocessing. Only the title, for now."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ] = Field(
        description="New display title. Surrounding whitespace is removed; 1 to 200"
        " characters remain.",
        examples=["PRO-014 Control de sellado (rev. 3)"],
    )
