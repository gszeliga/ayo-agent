"""Request and response bodies of the API. Every field is described for the OpenAPI docs."""

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

from ayo_copilot.config import MAX_SEARCH_TOP_K, Settings
from ayo_copilot.conversation.case import Phase
from ayo_copilot.conversation.store import SessionView
from ayo_copilot.db.repository import ChunkRow, DeletedRow, DocumentRow, StatusCounts, TenantRow
from ayo_copilot.ingestion import signatures
from ayo_copilot.ingestion.service import IngestResult, current_configs, document_status
from ayo_copilot.ingestion.signatures import DOC_ID_PATTERN
from ayo_copilot.ingestion.storage import TENANT_PATTERN
from ayo_copilot.search import SearchOutcome, SearchResult

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

# The `status` filter of the documents list: `db.repository.DOCUMENT_STATUSES`.
DocumentStatus = Literal["indexed", "outdated"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(
        description="Always `ok` when the process is serving.", examples=["ok"]
    )


EMBED_SIGNATURE_EXAMPLE = "17047d562b7e9a3c0f5d8b1e4a7c2f6d9b0e3a8c5f1d4b7e2a9c6f0d3b8e5a1c"


class IngestResponse(BaseModel):
    """The outcome of an upload or a reprocess. Sent without the optional fields when
    `up_to_date`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "doc_id": "upload-1890b5dc5335",
                    "status": "indexed",
                    "chunk_count": 12,
                    "embedding_model": "voyage-4",
                    "embed_signature": EMBED_SIGNATURE_EXAMPLE,
                }
            ]
        }
    )

    doc_id: str = Field(
        description="Stable id of the document, derived from the tenant and the source key.",
        examples=["upload-1890b5dc5335"],
    )
    status: Literal["indexed", "up_to_date"] = Field(
        description="`indexed`: chunked, embedded and stored (HTTP 201 on upload, 200 on"
        " reprocess). `up_to_date`: the stored version has the same content and settings,"
        " nothing was done (HTTP 200).",
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
        description="Signature that decides whether a later upload is `up_to_date`: the"
        " document's `embed_signature`. Only when `indexed`.",
        examples=[EMBED_SIGNATURE_EXAMPLE],
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
    status: DocumentStatus = Field(
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
        examples=[EMBED_SIGNATURE_EXAMPLE],
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


MAX_BULK_DELETE = 100


class DocumentDeleteRequest(BaseModel):
    """The documents to delete at once."""

    model_config = ConfigDict(extra="forbid")

    doc_ids: list[Annotated[str, StringConstraints(pattern=DOC_ID_PATTERN)]] = Field(
        min_length=1,
        max_length=MAX_BULK_DELETE,
        json_schema_extra={"uniqueItems": True},
        description=f"Ids of the documents to delete: 1 to {MAX_BULK_DELETE}, no repeats.",
        examples=[["upload-1890b5dc5335", "upload-4be0c2a91d7f"]],
    )

    @field_validator("doc_ids")
    @classmethod
    def _no_repeats(cls, doc_ids: list[str]) -> list[str]:
        if len(set(doc_ids)) != len(doc_ids):
            raise PydanticCustomError("duplicate_doc_ids", "doc_ids must not repeat an id")
        return doc_ids


class DeletedDocument(BaseModel):
    """A document that was deleted, with its chunks."""

    doc_id: str = Field(description="Id of the deleted document.", examples=["upload-1890b5dc5335"])
    tenant: str = Field(description="Tenant it belonged to.", examples=["acme"])
    chunk_count: int = Field(description="Chunks deleted with it.", examples=[12])

    @classmethod
    def from_row(cls, row: DeletedRow) -> "DeletedDocument":
        return cls(doc_id=row.doc_id, tenant=row.tenant, chunk_count=row.chunk_count)


class DocumentDeleteResult(BaseModel):
    """What a bulk delete did. Both lists keep the order of the request."""

    deleted: list[DeletedDocument] = Field(
        description="The documents deleted, with their chunks.",
        examples=[[{"doc_id": "upload-1890b5dc5335", "tenant": "acme", "chunk_count": 12}]],
    )
    not_found: list[str] = Field(
        description="Requested ids with no document (never stored, or already deleted).",
        examples=[["upload-4be0c2a91d7f"]],
    )


class TenantSummary(BaseModel):
    """A tenant with stored documents."""

    tenant: str = Field(description="Tenant id, as given on upload.", examples=["acme"])
    document_count: int = Field(
        description="Number of the tenant's stored documents, whatever their status.",
        examples=[4],
    )
    chunk_count: int = Field(
        description="Total chunks of those documents (the sum of their `chunk_count`).",
        examples=[57],
    )

    @classmethod
    def from_row(cls, row: TenantRow) -> "TenantSummary":
        return cls(
            tenant=row.tenant, document_count=row.document_count, chunk_count=row.chunk_count
        )


CHUNKER_CONFIG_EXAMPLE = (
    "md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1"
)


class ChunkingSettings(BaseModel):
    """How new uploads and reprocesses are chunked."""

    chunker_version: str = Field(
        description="Version of the chunking algorithm and of the embedded text format.",
        examples=["md-header+recursive@v3"],
    )
    chunk_size: int = Field(
        description="Target chunk size in characters (`CHUNK_SIZE`).", examples=[800]
    )
    chunk_overlap: int = Field(
        description="Characters shared by consecutive chunks of a split section (`CHUNK_OVERLAP`).",
        examples=[80],
    )
    min_chunk_size: int = Field(
        description="Chunks shorter than this are merged into a neighbour (`MIN_CHUNK_SIZE`).",
        examples=[100],
    )
    chunker_config: str = Field(
        description="All of the above as one string: a document whose `chunker_config`"
        " differs is outdated (`chunker_changed`).",
        examples=[CHUNKER_CONFIG_EXAMPLE],
    )


class EmbeddingSettings(BaseModel):
    """How chunks are embedded. No keys or URLs."""

    provider: Literal["voyage", "fake"] = Field(
        description="Embedding provider (`EMBEDDING_PROVIDER`); `fake` is for tests and"
        " local runs.",
        examples=["voyage"],
    )
    model: str = Field(description="Embedding model (`EMBEDDING_MODEL`).", examples=["voyage-4"])
    dimensions: int = Field(
        description="Vector size (`EMBEDDING_DIMENSIONS`); the database column must match.",
        examples=[1024],
    )
    batch_size: int = Field(
        description="Texts per provider request (`EMBEDDING_BATCH_SIZE`).", examples=[128]
    )
    embedder_config: str = Field(
        description="Model and dimensions as one string: a document whose `embedder_config`"
        " differs is outdated (`embedder_changed`).",
        examples=["voyage-4/document/1024"],
    )


class UploadSettings(BaseModel):
    """Limits on uploads."""

    max_upload_bytes: int = Field(
        description="Largest accepted file in bytes (`MAX_UPLOAD_BYTES`); larger ones get `413`.",
        examples=[5242880],
    )


class OutdatedCounts(BaseModel):
    """Outdated documents by reason, as `outdated_reason` reports them. A document whose
    chunker and embedder configs both differ counts as `chunker_changed` only."""

    unknown: int = Field(
        description="Indexed before configs were stored: their settings are not known.",
        examples=[0],
    )
    chunker_changed: int = Field(description="Chunked with other chunking settings.", examples=[2])
    embedder_changed: int = Field(
        description="Same chunking, embedded with another model or vector size.", examples=[1]
    )


class DocumentStatusCounts(BaseModel):
    """How the stored documents compare with the current settings, across all tenants."""

    total: int = Field(description="Stored documents.", examples=[12])
    indexed: int = Field(
        description="Documents the current settings would index the same way.", examples=[9]
    )
    outdated: OutdatedCounts = Field(
        description="The other documents, by reason; reprocessing brings them up to date."
    )


class IndexingSettings(BaseModel):
    """The settings new uploads and reprocesses use, and the documents' status against
    them."""

    chunking: ChunkingSettings = Field(description="Chunking settings.")
    embedding: EmbeddingSettings = Field(description="Embedding settings.")
    uploads: UploadSettings = Field(description="Upload limits.")
    documents: DocumentStatusCounts = Field(description="Document counts by status.")

    @classmethod
    def build(cls, settings: Settings, counts: StatusCounts) -> "IndexingSettings":
        chunker_config, embedder_config = current_configs(settings)
        return cls(
            chunking=ChunkingSettings(
                chunker_version=signatures.CHUNKER_VERSION,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                min_chunk_size=settings.min_chunk_size,
                chunker_config=chunker_config,
            ),
            embedding=EmbeddingSettings(
                provider=settings.embedding_provider,
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                batch_size=settings.embedding_batch_size,
                embedder_config=embedder_config,
            ),
            uploads=UploadSettings(max_upload_bytes=settings.max_upload_bytes),
            documents=DocumentStatusCounts(
                total=counts.total,
                indexed=counts.indexed,
                outdated=OutdatedCounts(
                    unknown=counts.unknown,
                    chunker_changed=counts.chunker_changed,
                    embedder_changed=counts.embedder_changed,
                ),
            ),
        )


ServiceState = Literal["up", "down"]


class DatabaseHealth(BaseModel):
    """One query through the connection pool, run on every request. Where the database
    runs is given as a category only: never its host or URL."""

    status: ServiceState = Field(description="`up` if the query answered in time.", examples=["up"])
    latency_ms: int = Field(
        description="How long the check took, waiting for a connection included.", examples=[4]
    )
    error: str | None = Field(
        description="`timeout` (no answer, or no free connection, within 2 s) or"
        " `connection failed`; null when up.",
        examples=["timeout"],
    )
    location: Literal["local", "neon", "remote"] = Field(
        description="Where it runs, from `DATABASE_URL`: `local` (localhost or a Unix"
        " socket), `neon` (a `*.neon.tech` host, pooled or direct) or `remote` (any other"
        " host). Known even when it is down.",
        examples=["neon"],
    )
    postgres_version: str | None = Field(
        description="PostgreSQL server version, its number only; null when down.",
        examples=["18.1"],
    )
    pgvector_version: str | None = Field(
        description="Version of the `vector` extension; null when down or not installed.",
        examples=["0.8.1"],
    )


class EmbeddingHealth(BaseModel):
    """The embedding provider: a check embedding one short word (cached for 60 s), and the
    outcome of the last real embedding calls since the service started."""

    status: ServiceState = Field(
        description="`up` if the check embedded its word within 5 s, without retries.",
        examples=["up"],
    )
    provider: Literal["voyage", "fake"] = Field(
        description="Embedding provider (`EMBEDDING_PROVIDER`); `fake` is always up.",
        examples=["voyage"],
    )
    checked_at: datetime = Field(
        description="When the check ran (UTC); older than this request when `cached`.",
        examples=["2026-11-05T10:14:03Z"],
    )
    latency_ms: int = Field(description="How long the check took.", examples=[180])
    error: str | None = Field(
        description="Why the check failed; null when up.",
        examples=["Embedding provider unreachable (ReadTimeout)"],
    )
    cached: bool = Field(
        description="Whether this is the result of an earlier check (up to 60 s old)."
        " `refresh=true` always checks again.",
        examples=[True],
    )
    last_success_at: datetime | None = Field(
        description="Last successful embedding call by an upload, a reprocess or a search"
        " (UTC); null if none since the service started.",
        examples=["2026-11-05T09:58:41Z"],
    )
    last_error_at: datetime | None = Field(
        description="Last failed embedding call by an upload, a reprocess or a search"
        " (UTC); null if none since the service started.",
        examples=["2026-11-05T10:12:10Z"],
    )
    last_error: str | None = Field(
        description="Why that call failed.", examples=["Embedding provider returned HTTP 503"]
    )


class ServiceHealth(BaseModel):
    """Whether the services the API depends on work."""

    status: Literal["ok", "degraded"] = Field(
        description="`ok` when the database and the embedding provider are both up.",
        examples=["ok"],
    )
    database: DatabaseHealth = Field(description="The database.")
    embeddings: EmbeddingHealth = Field(description="The embedding provider.")


MAX_QUERY_CHARS = 2000
MAX_SEARCH_TENANTS = 50
MAX_SEARCH_DOC_IDS = 50


def _no_repeats(values: list[str] | None, field: str) -> list[str] | None:
    if values is not None and len(set(values)) != len(values):
        raise PydanticCustomError(f"duplicate_{field}", f"{field} must not repeat a value")
    return values


class SearchRequest(BaseModel):
    """A question to find the nearest chunks for, and where to look."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS)
    ] = Field(
        description="The question, in the plant team's words. Surrounding whitespace is"
        f" removed; 1 to {MAX_QUERY_CHARS} characters remain. Never logged.",
        examples=["¿Qué herramienta uso si tengo muchos tipos de defecto?"],
    )
    tenants: list[Annotated[str, StringConstraints(pattern=TENANT_PATTERN)]] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_SEARCH_TENANTS,
        json_schema_extra={"uniqueItems": True},
        description="Tenants to search, 1 to"
        f" {MAX_SEARCH_TENANTS}, no repeats; null searches every tenant. A tenant without"
        " documents is not an error, it just adds no results. The production agent will"
        " always search one customer's tenant plus the shared `ayo` tenant, never across"
        " customers; searching every tenant is for administrators.",
        examples=[["cliente-acme", "ayo"]],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=MAX_SEARCH_TOP_K,
        description=f"How many chunks to return at most, 1 to {MAX_SEARCH_TOP_K}.",
        examples=[5],
    )
    min_similarity: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Drop results whose `similarity` is below this, 0 to 1; null keeps them"
        " all. Not calibrated yet: the evaluation harness reports the similarities of"
        " answerable and unanswerable questions to choose it.",
        examples=[0.5],
    )
    doc_ids: list[Annotated[str, StringConstraints(pattern=DOC_ID_PATTERN)]] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_SEARCH_DOC_IDS,
        json_schema_extra={"uniqueItems": True},
        description=f"Search only these documents, 1 to {MAX_SEARCH_DOC_IDS} ids, no repeats;"
        " null searches every document. Useful to debug one document. Unknown ids add no"
        " results.",
        examples=[["upload-1890b5dc5335"]],
    )
    include_outdated: bool = Field(
        default=False,
        description="Also search documents embedded with another embedding model (or an"
        " unknown one), flagged with `embedder_outdated`. Their vectors live in another"
        " space, so their similarities are not comparable; by default they are skipped and"
        " counted in `skipped`. A chunking change alone never skips a document.",
        examples=[False],
    )
    debug: bool = Field(
        default=False,
        description="Add `debug` to the answer: the text embedded, the configs and timings.",
        examples=[False],
    )

    @field_validator("tenants")
    @classmethod
    def _unique_tenants(cls, tenants: list[str] | None) -> list[str] | None:
        return _no_repeats(tenants, "tenants")

    @field_validator("doc_ids")
    @classmethod
    def _unique_doc_ids(cls, doc_ids: list[str] | None) -> list[str] | None:
        return _no_repeats(doc_ids, "doc_ids")


class SearchHitResult(BaseModel):
    """One chunk found, with what a result list shows of its document."""

    rank: int = Field(description="Position in the results, from 1.", examples=[1])
    similarity: float = Field(
        description="Cosine similarity between the query and the chunk, rounded to 4"
        " decimals: 1 for the same direction, 0 for unrelated, negative for opposite."
        " Results are ordered by it, highest first; ties by `chunk_id`.",
        examples=[0.8734],
    )
    chunk_id: UUID = Field(
        description="Stable id of the chunk until its document is reprocessed or replaced.",
        examples=["0b9f6c1e-3d2a-4f5b-8c7d-9e0a1b2c3d4e"],
    )
    chunk_index: int = Field(
        description="Position of the chunk in its document, from 0 (as in the chunks listing).",
        examples=[3],
    )
    heading: str | None = Field(
        description="Path of the Markdown headings the chunk sits under, joined with ` > `;"
        " null before the first heading.",
        examples=["Método Pareto > Cuándo aplicarlo"],
    )
    chunk_text: str = Field(
        description="The chunk's text (without the heading path that was embedded with it).",
        examples=[
            "Usa el diagrama de Pareto cuando tengas muchos tipos de defecto y necesites"
            " decidir cuáles atacar primero: el 20% de las causas suele explicar el 80%."
        ],
    )
    char_count: int = Field(
        description="Length of `chunk_text` in characters (not bytes).", examples=[148]
    )
    doc_id: str = Field(
        description="The document the chunk belongs to (link to its detail).",
        examples=["upload-3f9a1c2b7d4e"],
    )
    document_title: str | None = Field(
        description="The document's display title.", examples=["Método Pareto"]
    )
    source_key: str = Field(
        description="Name that identifies the document within its tenant.",
        examples=["pareto.md"],
    )
    tenant: str = Field(description="Tenant the document belongs to.", examples=["ayo"])
    embedder_outdated: bool = Field(
        description="The document was embedded with another (or an unknown) embedding model:"
        " its similarity is not comparable. Only true with `include_outdated`; reprocess the"
        " document to fix it.",
        examples=[False],
    )

    @classmethod
    def from_result(cls, result: SearchResult) -> "SearchHitResult":
        hit = result.hit
        return cls(
            rank=result.rank,
            similarity=result.similarity,
            chunk_id=hit.chunk_id,
            chunk_index=hit.chunk_index,
            heading=hit.heading,
            chunk_text=hit.chunk_text,
            char_count=hit.char_count,
            doc_id=hit.doc_id,
            document_title=hit.title,
            source_key=hit.source_key,
            tenant=hit.tenant,
            embedder_outdated=hit.embedder_outdated,
        )


class SearchSkipped(BaseModel):
    """Documents matching the filters that were not searched."""

    embedder_mismatch: int = Field(
        description="Documents embedded with another embedding model, or an unknown one,"
        " and so skipped (0 with `include_outdated`). Reprocess them to make them"
        " searchable again.",
        examples=[2],
    )


class SearchTimings(BaseModel):
    """Where the time went, in milliseconds rounded to 0.1."""

    embed: float = Field(description="Embedding the query (the provider call).", examples=[41.2])
    search: float = Field(description="The database search.", examples=[6.3])
    total: float = Field(description="Both, as measured around them.", examples=[47.5])


class SearchDebug(BaseModel):
    """How the search ran, for diagnosis."""

    embedded_query: str = Field(
        description="The text sent to the embedding provider: the trimmed query. The"
        " provider adds its own retrieval prompt for `input_type`.",
        examples=["¿Qué herramienta uso si tengo muchos tipos de defecto?"],
    )
    input_type: Literal["query"] = Field(
        description="How the query was embedded (documents are embedded as `document`).",
        examples=["query"],
    )
    embedder_config: str = Field(
        description="Embedding model and dimensions searched with; documents with another"
        " value are skipped unless `include_outdated`.",
        examples=["voyage-4/document/1024"],
    )
    chunker_config: str = Field(
        description="Current chunking settings (documents chunked otherwise are still searched).",
        examples=[CHUNKER_CONFIG_EXAMPLE],
    )
    timings_ms: SearchTimings = Field(description="Durations of the stages.")


def _ms(value: float) -> float:
    return round(value, 1)


class SearchResponse(BaseModel):
    """The nearest chunks, what was skipped and, on request, how the search ran."""

    query: str = Field(
        description="The query as searched (trimmed).",
        examples=["¿Qué herramienta uso si tengo muchos tipos de defecto?"],
    )
    results: list[SearchHitResult] = Field(
        description="The nearest chunks, best first; empty when nothing matches the filters"
        " or passes `min_similarity`."
    )
    skipped: SearchSkipped = Field(description="Documents left out of the search.")
    debug: SearchDebug | None = Field(
        description="Present (not null) only with `debug=true`.",
        examples=[
            {
                "embedded_query": "¿Qué herramienta uso si tengo muchos tipos de defecto?",
                "input_type": "query",
                "embedder_config": "voyage-4/document/1024",
                "chunker_config": CHUNKER_CONFIG_EXAMPLE,
                "timings_ms": {"embed": 41.2, "search": 6.3, "total": 47.5},
            }
        ],
    )

    @classmethod
    def from_outcome(cls, outcome: SearchOutcome, *, debug: bool) -> "SearchResponse":
        return cls(
            query=outcome.embedded_query,
            results=[SearchHitResult.from_result(result) for result in outcome.results],
            skipped=SearchSkipped(embedder_mismatch=outcome.embedder_mismatch),
            debug=SearchDebug(
                embedded_query=outcome.embedded_query,
                input_type="query",
                embedder_config=outcome.embedder_config,
                chunker_config=outcome.chunker_config,
                timings_ms=SearchTimings(
                    embed=_ms(outcome.embed_ms),
                    search=_ms(outcome.search_ms),
                    total=_ms(outcome.total_ms),
                ),
            )
            if debug
            else None,
        )


# --- The copilot (conversations) -----------------------------------------------------

# The longest `user_id` a channel may send; stored as the case's `created_by`.
MAX_USER_ID_CHARS = 200
SESSION_ID_EXAMPLE = "3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14"

_PHASE_DESCRIPTION = (
    "`understand` (the four facts), `challenge` (evidence), `analyse` (the cause),"
    " `action` (actions with owner and date), `followup` (tracking them) or `closed`."
)


class CopilotMessageRequest(BaseModel):
    """One message from the plant team to the copilot."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "session_id": SESSION_ID_EXAMPLE,
                    "tenant": "cliente-acme",
                    "text": "Tenemos un 4 % de merma en la llenadora de la línea 2.",
                    "user_id": "operario-17",
                }
            ]
        },
    )

    session_id: UUID = Field(
        description="The conversation, generated by the client (a UUID). The first message"
        " of a session opens a case; the next ones continue it.",
        examples=[SESSION_ID_EXAMPLE],
    )
    tenant: Annotated[str, StringConstraints(pattern=TENANT_PATTERN)] = Field(
        description="The customer. A session belongs to the tenant of its first message;"
        " another tenant gets `422 tenant_mismatch`.",
        examples=["cliente-acme"],
    )
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="The message. Surrounding whitespace is removed; 1 to"
        " `MAX_USER_MESSAGE_CHARS` (default 4000) characters remain. Never logged.",
        examples=["Tenemos un 4 % de merma en la llenadora de la línea 2."],
    )
    user_id: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_USER_ID_CHARS),
        ]
        | None
    ) = Field(
        default=None,
        description=f"Who writes, 1 to {MAX_USER_ID_CHARS} characters; optional. Recorded as"
        " the case's creator on the first message.",
        examples=["operario-17"],
    )


class ToolUse(BaseModel):
    """One tool call the copilot made in the turn: what it tried to record, not the values."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "record_field", "ok": True}]}
    )

    name: str = Field(
        description="The tool: `record_field`, `log_event`, `add_action`, `update_action` or"
        " `propose_transition` (any other name was refused).",
        examples=["record_field"],
    )
    ok: bool = Field(
        description="Whether it was accepted. A refused call (invalid values, criteria not"
        " met) changed nothing; the copilot was told why.",
        examples=[True],
    )


class CopilotMessageResponse(BaseModel):
    """The copilot's reply and where the case stands after the turn."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "session_id": SESSION_ID_EXAMPLE,
                    "reply": "Entendido. ¿Qué datos tenéis de la llenadora desde el lunes?",
                    "phase": "challenge",
                    "previous_phase": "understand",
                    "phase_changed": True,
                    "turn": 3,
                    "tools_used": [
                        {"name": "record_field", "ok": True},
                        {"name": "propose_transition", "ok": True},
                    ],
                }
            ]
        }
    )

    session_id: UUID = Field(description="The session, as sent.", examples=[SESSION_ID_EXAMPLE])
    reply: str = Field(
        description="The copilot's answer, in Spanish. When a phase changed, it already"
        " opens the new phase.",
        examples=["Entendido. ¿Qué datos tenéis de la llenadora desde el lunes?"],
    )
    phase: Phase = Field(
        description=f"The phase after the turn: {_PHASE_DESCRIPTION}", examples=["challenge"]
    )
    previous_phase: Phase = Field(description="The phase before the turn.", examples=["understand"])
    phase_changed: bool = Field(
        description="Whether the turn moved the case to another phase.", examples=[True]
    )
    turn: int = Field(ge=1, description="The turn's number in the case, from 1.", examples=[3])
    tools_used: list[ToolUse] = Field(
        description="The tool calls of the turn, in order; empty when the copilot only wrote."
    )


class CopilotSessionFields(BaseModel):
    """The four facts of the problem; null until recorded."""

    what: str | None = Field(description="What happens.", examples=["Merma del 4 % en el envasado"])
    where: str | None = Field(description="Where it happens.", examples=["Línea 2, llenadora"])
    since: str | None = Field(description="Since when.", examples=["Desde el lunes 9"])
    standard: str | None = Field(
        description="What should happen instead (the standard).",
        examples=["Merma máxima del 1,5 %"],
    )


class CopilotSessionEvent(BaseModel):
    """An annotation the copilot recorded: evidence, a hypothesis, a discarded hypothesis or
    the validated cause."""

    id: int = Field(description="The annotation's id, in recording order.", examples=[12])
    event_type: Literal["evidence", "hypothesis", "hypothesis_discarded", "validated_cause"] = (
        Field(description="What kind of annotation it is.", examples=["evidence"])
    )
    content: str = Field(
        description="The annotation, as recorded.",
        examples=["El sensor de nivel marca 3 mm de más desde el cambio de formato"],
    )
    state_at_time: Phase = Field(
        description="The phase it was recorded in.", examples=["challenge"]
    )
    created_at: datetime = Field(
        description="When it was recorded (UTC).", examples=["2026-11-12T09:31:04Z"]
    )


class CopilotSessionAction(BaseModel):
    """An agreed action."""

    id: int = Field(description="The action's id.", examples=[3])
    description: str = Field(
        description="What to do.", examples=["Recalibrar el sensor de nivel de la llenadora"]
    )
    owner: str = Field(description="Who does it.", examples=["Ana (mantenimiento)"])
    due_date: date_type = Field(description="By when.", examples=["2026-11-20"])
    status: Literal["pending", "done"] = Field(
        description="`pending` or `done`.", examples=["pending"]
    )
    overdue: bool = Field(
        description="Pending and past its due date, in `APP_TIMEZONE` (computed, not stored).",
        examples=[False],
    )


class CopilotSessionMessage(BaseModel):
    """One message of the conversation."""

    role: Literal["user", "assistant"] = Field(
        description="`user` (the plant team) or `assistant` (the copilot).", examples=["user"]
    )
    content: str = Field(
        description="The message.",
        examples=["Tenemos un 4 % de merma en la llenadora de la línea 2."],
    )
    state_at_time: Phase = Field(
        description="The phase when it was sent: a user message carries the phase its turn"
        " started in, a reply the phase it ended in.",
        examples=["understand"],
    )
    created_at: datetime = Field(
        description="When it was stored (UTC).", examples=["2026-11-12T09:30:58Z"]
    )


class CopilotSession(BaseModel):
    """A session's case, for inspection while testing. No prompts, traces or retrieved
    text."""

    session_id: UUID = Field(description="The session.", examples=[SESSION_ID_EXAMPLE])
    tenant: str = Field(description="The case's tenant.", examples=["cliente-acme"])
    phase: Phase = Field(
        description=f"The current phase: {_PHASE_DESCRIPTION}", examples=["analyse"]
    )
    version: int = Field(ge=0, description="Bumped by every committed turn.", examples=[7])
    turns: int = Field(ge=0, description="Committed turns.", examples=[4])
    fields: CopilotSessionFields = Field(description="The four facts.")
    events: list[CopilotSessionEvent] = Field(description="The annotations, oldest first.")
    actions: list[CopilotSessionAction] = Field(description="The actions, oldest first.")
    messages: list[CopilotSessionMessage] = Field(description="The conversation, oldest first.")

    @classmethod
    def from_view(cls, session_id: UUID, view: SessionView) -> "CopilotSession":
        return cls(
            session_id=session_id,
            tenant=view.tenant,
            phase=view.phase,
            version=view.version,
            turns=view.turns,
            fields=CopilotSessionFields(**view.fields),
            events=[
                CopilotSessionEvent(
                    id=event.id,
                    event_type=event.event_type,
                    content=event.content,
                    state_at_time=event.state_at_time,
                    created_at=_utc(event.created_at),
                )
                for event in view.events
            ],
            actions=[
                CopilotSessionAction(
                    id=item.action.id,
                    description=item.action.description,
                    owner=item.action.owner,
                    due_date=item.action.due_date,
                    status=item.action.status,
                    overdue=item.overdue,
                )
                for item in view.actions
            ],
            messages=[
                CopilotSessionMessage(
                    role=message.role,
                    content=message.content,
                    state_at_time=message.state_at_time,
                    created_at=_utc(message.created_at),
                )
                for message in view.messages
            ],
        )
