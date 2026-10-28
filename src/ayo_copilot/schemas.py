"""Request and response bodies of the API. Every field is described for the OpenAPI docs."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ayo_copilot.ingestion.service import IngestResult


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="Always `ok` when the process is serving.")


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
