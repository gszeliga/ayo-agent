"""The reprocess pipeline on a real database, with the fake embedder.

The races are made deterministic by an embedder that changes the database while it is
being called: that is the window in which a concurrent request can interfere.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import get_document, rename_document
from ayo_copilot.ingestion import service
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from ayo_copilot.ingestion.service import (
    DocumentChangedError,
    DocumentNotFoundError,
    IngestResult,
    chunk_document,
    compute_signatures,
    document_status,
    embedding_text,
)
from tests.integration.test_ingestion_service import (
    CONTENT,
    FailingEmbedder,
    ingest,
    make_settings,
    snapshot,
    stored_chunks,
)

pytestmark = pytest.mark.integration

SMALLER_CHUNKS = {"chunk_size": 300, "chunk_overlap": 30, "min_chunk_size": 50}


class MeddlingEmbedder(FakeEmbedder):
    """Runs `meddle` (a concurrent change) when called, then embeds as usual."""

    def __init__(self, meddle: Callable[[], None]) -> None:
        super().__init__(dimensions=1024)
        self.meddle = meddle

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.meddle()
        return super().embed_documents(texts)


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimensions=1024)


def reprocess(
    pool: ConnectionPool,
    embedder,
    doc_id: str,
    *,
    settings: Settings | None = None,
    force: bool = False,
) -> IngestResult:
    return service.reprocess_document(
        settings=settings or make_settings(),
        pool=pool,
        embedder=embedder,
        doc_id=doc_id,
        force=force,
    )


def row(pool: ConnectionPool, doc_id: str):
    with pool.connection() as conn:
        return get_document(conn, doc_id)


def test_an_up_to_date_document_is_left_alone(db_pool: ConnectionPool, embedder) -> None:
    doc_id = ingest(db_pool, embedder).doc_id
    before = snapshot(db_pool)
    embedder.calls.clear()

    result = reprocess(db_pool, embedder, doc_id)

    assert result == IngestResult(doc_id=doc_id, status="up_to_date")
    assert embedder.calls == []
    assert snapshot(db_pool) == before


def test_force_reprocesses_an_up_to_date_document(db_pool: ConnectionPool, embedder) -> None:
    doc_id = ingest(db_pool, embedder).doc_id
    before = row(db_pool, doc_id)
    embedder.calls.clear()

    result = reprocess(db_pool, embedder, doc_id, force=True)

    after = row(db_pool, doc_id)
    assert (result.status, result.chunk_count) == ("indexed", before.chunk_count)
    assert len(embedder.calls) == 1
    assert after.embedded_at > before.embedded_at
    assert after.updated_at == before.updated_at


def test_new_chunk_settings_reindex_from_the_stored_markdown(
    db_pool: ConnectionPool, embedder
) -> None:
    doc_id = ingest(db_pool, embedder).doc_id
    with db_pool.connection() as conn:
        rename_document(conn, doc_id, "Sellado (renombrado)")
    before = row(db_pool, doc_id)
    settings = make_settings(**SMALLER_CHUNKS)
    assert document_status(before.chunker_config, before.embedder_config, settings) == (
        "outdated",
        "chunker_changed",
    )
    embedder.calls.clear()

    result = reprocess(db_pool, embedder, doc_id, settings=settings)

    after = row(db_pool, doc_id)
    markdown = CONTENT.decode()
    expected_chunks = chunk_document(markdown, settings)
    sigs = compute_signatures(markdown, settings)
    assert result == IngestResult(
        doc_id=doc_id,
        status="indexed",
        chunk_count=len(expected_chunks),
        embedding_model="voyage-4",
        embed_signature=sigs.embed_signature,
    )
    assert len(expected_chunks) > before.chunk_count
    assert embedder.calls == [[embedding_text(chunk) for chunk in expected_chunks]]
    assert [text for _, _, text, _ in stored_chunks(db_pool)] == [c.text for c in expected_chunks]
    assert (after.chunk_count, after.chunk_signature, after.embed_signature) == (
        len(expected_chunks),
        sigs.chunk_signature,
        sigs.embed_signature,
    )
    assert (after.chunker_config, after.embedder_config) == (
        sigs.chunker_config,
        sigs.embedder_config,
    )
    assert document_status(after.chunker_config, after.embedder_config, settings) == (
        "indexed",
        None,
    )
    assert after.chunked_at > before.chunked_at
    kept = ("title", "content_hash", "size_bytes", "created_at", "updated_at")
    assert [getattr(after, k) for k in kept] == [getattr(before, k) for k in kept]
    assert after.title == "Sellado (renombrado)"


def test_missing_configs_are_recorded_without_the_provider(
    db_pool: ConnectionPool, embedder
) -> None:
    doc_id = ingest(db_pool, embedder).doc_id
    with db_pool.connection() as conn:
        conn.execute("update documents set chunker_config = null, embedder_config = null")
    before = row(db_pool, doc_id)
    chunks_before = snapshot(db_pool)[1]
    embedder.calls.clear()

    result = reprocess(db_pool, embedder, doc_id)

    after = row(db_pool, doc_id)
    sigs = compute_signatures(CONTENT.decode(), make_settings())
    assert result.status == "up_to_date"
    assert embedder.calls == []
    assert (after.chunker_config, after.embedder_config) == (
        sigs.chunker_config,
        sigs.embedder_config,
    )
    assert document_status(after.chunker_config, after.embedder_config, make_settings())[0] == (
        "indexed"
    )
    assert replace(after, chunker_config=None, embedder_config=None) == before
    assert snapshot(db_pool)[1] == chunks_before


def test_provider_failure_writes_nothing(db_pool: ConnectionPool, embedder) -> None:
    doc_id = ingest(db_pool, embedder).doc_id
    before = snapshot(db_pool)

    with pytest.raises(EmbeddingError):
        reprocess(db_pool, FailingEmbedder(), doc_id, settings=make_settings(**SMALLER_CHUNKS))

    assert snapshot(db_pool) == before


def test_unknown_document_is_not_found(db_pool: ConnectionPool, embedder) -> None:
    with pytest.raises(DocumentNotFoundError):
        reprocess(db_pool, embedder, "upload-000000000000")
    assert embedder.calls == []


def test_a_newer_upload_meanwhile_wins(db_pool: ConnectionPool, embedder) -> None:
    doc_id = ingest(db_pool, embedder).doc_id
    newer = "# PRO-014 Control de sellado\n\nVersión nueva del procedimiento.\n".encode()
    racer = MeddlingEmbedder(lambda: ingest(db_pool, FakeEmbedder(dimensions=1024), newer))

    with pytest.raises(DocumentChangedError):
        reprocess(db_pool, racer, doc_id, force=True)

    after = row(db_pool, doc_id)
    assert after.content_hash == compute_signatures(newer.decode(), make_settings()).content_hash
    assert [text for _, _, text, _ in stored_chunks(db_pool)] == [
        "Versión nueva del procedimiento."
    ]


def test_a_delete_meanwhile_is_not_found(db_pool: ConnectionPool, embedder) -> None:
    doc_id = ingest(db_pool, embedder).doc_id

    def delete() -> None:
        with db_pool.connection() as conn:
            conn.execute("delete from documents where doc_id = %s", (doc_id,))

    with pytest.raises(DocumentNotFoundError):
        reprocess(db_pool, MeddlingEmbedder(delete), doc_id, force=True)

    assert snapshot(db_pool) == ([], [])


def test_a_rename_meanwhile_is_kept(db_pool: ConnectionPool, embedder) -> None:
    doc_id = ingest(db_pool, embedder).doc_id

    def rename() -> None:
        with db_pool.connection() as conn:
            rename_document(conn, doc_id, "Renombrado durante el reproceso")

    result = reprocess(
        db_pool, MeddlingEmbedder(rename), doc_id, settings=make_settings(**SMALLER_CHUNKS)
    )

    assert result.status == "indexed"
    assert row(db_pool, doc_id).title == "Renombrado durante el reproceso"
