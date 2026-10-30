"""The ingestion pipeline: validate, check signatures, chunk, embed, store.

The stages are separate functions so a future worker can reuse them. Document content
is customer data: it is never logged, only `doc_id`, tenant, counts and durations.
"""

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, NoReturn

from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import (
    ChunkRecord,
    DocumentRecord,
    get_document,
    get_embed_signature,
    get_markdown,
    record_configs,
    replace_chunks,
    update_indexed_document,
    upsert_document,
)
from ayo_copilot.ingestion import signatures
from ayo_copilot.ingestion.chunking import Chunk, chunk_markdown, normalize_markdown
from ayo_copilot.ingestion.embedding import Embedder
from ayo_copilot.ingestion.storage import (
    InvalidInputError,
    normalize_source_key,
    validate_tenant,
)

logger = logging.getLogger(__name__)

_H1 = re.compile(r"#[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*")
_FENCE = re.compile(r"(`{3,}|~{3,})")


DocumentStatus = Literal["indexed", "outdated"]
OutdatedReason = Literal["chunker_changed", "embedder_changed", "unknown"]


@dataclass(frozen=True)
class ProcessingSignatures:
    """What identifies an indexed version: the content and the settings it was processed with.

    The configs are the descriptors the signatures are built from, stored so the admin API
    can tell which documents the current settings would index differently.
    """

    content_hash: str
    chunker_config: str
    embedder_config: str
    chunk_signature: str
    embed_signature: str


class DocumentNotFoundError(Exception):
    """No document has this `doc_id`, or it was deleted while being reprocessed."""


class DocumentChangedError(Exception):
    """A newer upload replaced the document's content while it was being reprocessed."""


@dataclass(frozen=True)
class IngestResult:
    doc_id: str
    status: Literal["indexed", "up_to_date"]
    # Set only when the document was (re)indexed.
    chunk_count: int | None = None
    embedding_model: str | None = None
    embed_signature: str | None = None


def decode_markdown(content: bytes) -> str:
    """UTF-8 bytes to normalized Markdown; rejects invalid UTF-8 and blank files."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidInputError(
            "file is not valid UTF-8", field="file", code="file_encoding"
        ) from None
    markdown = normalize_markdown(text)
    if not markdown.strip():
        raise InvalidInputError("file is empty", field="file", code="file_empty")
    return markdown


def first_h1(markdown: str) -> str | None:
    """The text of the first `# ` heading outside code blocks."""
    fence: str | None = None
    for line in markdown.split("\n"):
        stripped = line.strip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            continue
        if opening := _FENCE.match(stripped):
            fence = opening.group(1)
            continue
        if match := _H1.fullmatch(stripped):
            return match.group(1)
    return None


def resolve_title(title: str | None, markdown: str, source_key: str) -> str:
    """The given title, else the first H1, else the file name."""
    if title and title.strip():
        return title.strip()
    return first_h1(markdown) or source_key


def current_configs(settings: Settings) -> tuple[str, str]:
    """The chunker and embedder descriptors the current settings index with."""
    chunker_config = signatures.chunker_descriptor(
        size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        min_size=settings.min_chunk_size,
    )
    embedder_config = signatures.embedder_descriptor(
        model=settings.embedding_model, dimensions=settings.embedding_dimensions
    )
    return chunker_config, embedder_config


def compute_signatures(markdown: str, settings: Settings) -> ProcessingSignatures:
    content_hash = signatures.content_hash(markdown)
    chunker_config, embedder_config = current_configs(settings)
    chunk_signature = signatures.chunk_signature(content_hash, chunker_config)
    return ProcessingSignatures(
        content_hash=content_hash,
        chunker_config=chunker_config,
        embedder_config=embedder_config,
        chunk_signature=chunk_signature,
        embed_signature=signatures.embed_signature(chunk_signature, embedder_config),
    )


def document_status(
    chunker_config: str | None, embedder_config: str | None, settings: Settings
) -> tuple[DocumentStatus, OutdatedReason | None]:
    """Whether the current settings would index the document differently, and why.

    Missing configs (rows indexed before they were stored) count as `unknown`; when both
    differ, the chunker wins, since re-chunking implies re-embedding anyway.
    """
    current_chunker, current_embedder = current_configs(settings)
    if chunker_config is None or embedder_config is None:
        return "outdated", "unknown"
    if chunker_config != current_chunker:
        return "outdated", "chunker_changed"
    if embedder_config != current_embedder:
        return "outdated", "embedder_changed"
    return "indexed", None


def chunk_document(markdown: str, settings: Settings) -> list[Chunk]:
    chunks = chunk_markdown(
        markdown,
        size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        min_size=settings.min_chunk_size,
    )
    if not chunks:
        raise InvalidInputError(
            "file has no indexable content", field="file", code="file_no_content"
        )
    return chunks


def embedding_text(chunk: Chunk) -> str:
    """The heading path gives the vector context; `chunk_text` is stored without it."""
    if not chunk.heading_path:
        return chunk.text
    return f"{chunk.heading_path}\n\n{chunk.text}"


def embed_chunks(embedder: Embedder, chunks: Sequence[Chunk]) -> list[list[float]]:
    return embedder.embed_documents([embedding_text(chunk) for chunk in chunks])


def index_markdown(
    markdown: str, settings: Settings, embedder: Embedder
) -> tuple[list[Chunk], list[list[float]]]:
    """Chunk and embed, without touching the database: the provider call that can fail or
    take seconds stays outside any transaction."""
    chunks = chunk_document(markdown, settings)
    return chunks, embed_chunks(embedder, chunks)


def _chunk_records(
    document: DocumentRecord, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
) -> list[ChunkRecord]:
    return [
        ChunkRecord(
            index=chunk.index,
            heading=chunk.heading_path or None,
            text=chunk.text,
            embedding=vector,
            metadata={"doc_id": document.doc_id, "tenant": document.tenant},
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def store_document(
    pool: ConnectionPool,
    document: DocumentRecord,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
) -> None:
    """Insert or overwrite the document, its Markdown and its chunks in one transaction."""
    records = _chunk_records(document, chunks, vectors)
    with pool.connection() as conn, conn.transaction():
        document_id = upsert_document(conn, document)
        replace_chunks(conn, document_id, records)


def store_reprocessed_document(
    pool: ConnectionPool,
    document: DocumentRecord,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
) -> bool:
    """Replace the chunks of a stored document whose content is still
    `document.content_hash`, in one transaction. False, with nothing written, if the
    document is gone or its content changed: a newer upload's chunks must survive."""
    records = _chunk_records(document, chunks, vectors)
    with pool.connection() as conn, conn.transaction():
        document_id = update_indexed_document(conn, document)
        if document_id is None:
            return False
        replace_chunks(conn, document_id, records)
    return True


def reprocess_document(
    *,
    settings: Settings,
    pool: ConnectionPool,
    embedder: Embedder,
    doc_id: str,
    force: bool = False,
) -> IngestResult:
    """Re-chunk and re-embed a stored document, from its stored Markdown, with the current
    settings. Its title, Markdown and `updated_at` are kept.

    Skipped (`up_to_date`, no provider call) when its embed signature already matches,
    unless `force`; a document indexed before its configs were stored only gets them
    recorded then. Raises DocumentNotFoundError, DocumentChangedError and EmbeddingError;
    in each case nothing is written. As on upload, the provider is called outside any
    transaction.
    """
    started = time.monotonic()
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        row = get_document(conn, doc_id)
        markdown = get_markdown(conn, doc_id)
    if row is None or markdown is None:
        raise DocumentNotFoundError(doc_id)

    sigs = compute_signatures(markdown, settings)
    if not force and row.embed_signature == sigs.embed_signature:
        if row.chunker_config is None or row.embedder_config is None:
            with pool.connection() as conn, conn.transaction():
                recorded = record_configs(
                    conn, doc_id, sigs.embed_signature, sigs.chunker_config, sigs.embedder_config
                )
            if not recorded:
                _raise_conflict(pool, doc_id)
        _log_result(doc_id, row.tenant, "up_to_date", 0, started, action="reprocess")
        return IngestResult(doc_id=doc_id, status="up_to_date")

    chunks, vectors = index_markdown(markdown, settings, embedder)
    document = DocumentRecord(
        doc_id=doc_id,
        tenant=row.tenant,
        source_type=row.source_type,
        source_key=row.source_key,
        title=row.title,
        markdown=markdown,
        content_hash=sigs.content_hash,
        chunk_signature=sigs.chunk_signature,
        embed_signature=sigs.embed_signature,
        chunk_count=len(chunks),
        chunker_config=sigs.chunker_config,
        embedder_config=sigs.embedder_config,
    )
    if not store_reprocessed_document(pool, document, chunks, vectors):
        _raise_conflict(pool, doc_id)

    _log_result(doc_id, row.tenant, "indexed", len(chunks), started, action="reprocess")
    return IngestResult(
        doc_id=doc_id,
        status="indexed",
        chunk_count=len(chunks),
        embedding_model=settings.embedding_model,
        embed_signature=sigs.embed_signature,
    )


def _raise_conflict(pool: ConnectionPool, doc_id: str) -> NoReturn:
    """A guarded write matched no row: the document is gone, or its content changed."""
    with pool.connection() as conn:
        exists = get_document(conn, doc_id) is not None
    if exists:
        raise DocumentChangedError(doc_id)
    raise DocumentNotFoundError(doc_id)


def ingest_document(
    *,
    settings: Settings,
    pool: ConnectionPool,
    embedder: Embedder,
    tenant: str,
    filename: str,
    content: bytes,
    title: str | None = None,
    source_key: str | None = None,
    force: bool = False,
) -> IngestResult:
    """Index one uploaded Markdown file, or report that it is already up to date.

    Raises InvalidInputError for bad input and EmbeddingError when the provider fails.
    The provider is called outside any transaction, and nothing is written before it
    succeeds, so a failure leaves the database untouched.
    """
    started = time.monotonic()
    tenant = validate_tenant(tenant)
    source_key = normalize_source_key(source_key or filename)
    markdown = decode_markdown(content)
    doc_id = signatures.make_doc_id(tenant, source_key)

    sigs = compute_signatures(markdown, settings)

    if not force:
        with pool.connection() as conn:
            stored = get_embed_signature(conn, doc_id)
        if stored == sigs.embed_signature:
            _log_result(doc_id, tenant, "up_to_date", 0, started)
            return IngestResult(doc_id=doc_id, status="up_to_date")

    chunks, vectors = index_markdown(markdown, settings, embedder)
    document = DocumentRecord(
        doc_id=doc_id,
        tenant=tenant,
        source_key=source_key,
        title=resolve_title(title, markdown, source_key),
        markdown=markdown,
        content_hash=sigs.content_hash,
        chunk_signature=sigs.chunk_signature,
        embed_signature=sigs.embed_signature,
        chunk_count=len(chunks),
        chunker_config=sigs.chunker_config,
        embedder_config=sigs.embedder_config,
    )
    store_document(pool, document, chunks, vectors)

    _log_result(doc_id, tenant, "indexed", len(chunks), started)
    return IngestResult(
        doc_id=doc_id,
        status="indexed",
        chunk_count=len(chunks),
        embedding_model=settings.embedding_model,
        embed_signature=sigs.embed_signature,
    )


def _log_result(
    doc_id: str,
    tenant: str,
    status: str,
    chunk_count: int,
    started: float,
    *,
    action: str = "upload",
) -> None:
    logger.info(
        "document %s tenant=%s %s status=%s chunks=%d in %.0f ms",
        doc_id,
        tenant,
        action,
        status,
        chunk_count,
        (time.monotonic() - started) * 1000,
    )
