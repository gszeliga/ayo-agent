"""Request and response bodies of the API."""

from typing import Literal

from pydantic import BaseModel

from ayo_copilot.ingestion.service import IngestResult


class IngestResponse(BaseModel):
    doc_id: str
    status: Literal["indexed", "up_to_date"]
    # Set only when the document was (re)indexed.
    chunk_count: int | None = None
    embedding_model: str | None = None
    embed_signature: str | None = None

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
    """Compatible with the items of FastAPI's `HTTPValidationError` (`input` omitted)."""

    type: str
    loc: list[str | int]
    msg: str


class ErrorResponse(BaseModel):
    detail: list[ErrorItem]
