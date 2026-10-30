import threading

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.db.repository import (
    ChunkRecord,
    DocumentRecord,
    get_chunk_count,
    list_chunks,
    replace_chunks,
    similar_chunks,
    upsert_document,
)
from ayo_copilot.ingestion.embedding import FakeEmbedder
from ayo_copilot.ingestion.signatures import make_doc_id

pytestmark = pytest.mark.integration

embedder = FakeEmbedder(dimensions=1024)


def make_document(
    tenant: str = "acme", source_key: str = "pro-014.md", **overrides
) -> DocumentRecord:
    values: dict[str, object] = {
        "doc_id": make_doc_id(tenant, source_key),
        "tenant": tenant,
        "source_key": source_key,
        "title": "PRO-014 Control de sellado",
        "markdown": "# PRO-014 Control de sellado\n\nTexto original.\n",
        "content_hash": "content-1",
        "chunk_signature": "chunk-1",
        "embed_signature": "embed-1",
        "chunk_count": 0,
        "chunker_config": "chunker-1",
        "embedder_config": "embedder-1",
    }
    values.update(overrides)
    return DocumentRecord(**values)


def make_chunks(*texts: str, heading: str = "PRO-014 > 3. Pasos") -> list[ChunkRecord]:
    vectors = embedder.embed_documents(list(texts))
    return [
        ChunkRecord(index=i, heading=heading, text=text, embedding=vector, metadata={"n": i})
        for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    ]


def store(pool: ConnectionPool, document: DocumentRecord, chunks: list[ChunkRecord]):
    with pool.connection() as conn, conn.transaction():
        document_id = upsert_document(conn, document)
        replace_chunks(conn, document_id, chunks)
    return document_id


def chunk_texts(pool: ConnectionPool) -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute("select chunk_text from chunks order by chunk_index").fetchall()
    return [text for (text,) in rows]


def document_row(pool: ConnectionPool) -> tuple:
    with pool.connection() as conn:
        return conn.execute(
            "select id, title, content_hash, embed_signature, created_at, updated_at, markdown"
            " from documents"
        ).fetchone()


def test_upsert_inserts_a_new_document(db_pool: ConnectionPool) -> None:
    document_id = store(db_pool, make_document(), [])

    with db_pool.connection() as conn:
        row = conn.execute(
            "select doc_id, tenant, source_type, source_key, chunked_at is not null,"
            " embedded_at is not null from documents where id = %s",
            (document_id,),
        ).fetchone()
    assert row == (make_doc_id("acme", "pro-014.md"), "acme", "upload", "pro-014.md", True, True)


def test_upsert_updates_the_same_row(db_pool: ConnectionPool) -> None:
    first_id = store(db_pool, make_document(), [])
    _, _, _, _, created_at, first_updated_at, _ = document_row(db_pool)
    revised = "# Nuevo título\n\nTexto revisado, versión 2.\n"

    second_id = store(
        db_pool,
        make_document(
            title="Nuevo título",
            content_hash="content-2",
            embed_signature="embed-2",
            markdown=revised,
        ),
        [],
    )

    assert second_id == first_id
    row_id, title, content_hash, embed_signature, created, updated, markdown = document_row(db_pool)
    assert (row_id, title, content_hash, embed_signature, markdown) == (
        first_id,
        "Nuevo título",
        "content-2",
        "embed-2",
        revised,
    )
    assert created == created_at
    assert updated > first_updated_at


def admin_columns(pool: ConnectionPool) -> tuple:
    with pool.connection() as conn:
        return conn.execute(
            "select chunk_count, size_bytes, chunker_config, embedder_config from documents"
        ).fetchone()


def test_upsert_writes_the_admin_columns(db_pool: ConnectionPool) -> None:
    markdown = "# Válvula\n\nPresión máxima: 6 bar.\n"
    store(db_pool, make_document(markdown=markdown, chunk_count=1), make_chunks("uno"))

    assert admin_columns(db_pool) == (1, len(markdown.encode()), "chunker-1", "embedder-1")

    revised = "# Válvula\n\nPresión máxima: 8 bar. Revisión anual.\n"
    store(
        db_pool,
        make_document(
            markdown=revised, chunk_count=2, chunker_config="chunker-2", embedder_config=None
        ),
        make_chunks("uno", "dos"),
    )

    assert admin_columns(db_pool) == (2, len(revised.encode()), "chunker-2", None)


def test_replace_chunks_removes_the_old_ones(db_pool: ConnectionPool) -> None:
    store(db_pool, make_document(), make_chunks("uno", "dos", "tres"))
    store(db_pool, make_document(), make_chunks("Temperatura máxima: 180 °C"))

    assert chunk_texts(db_pool) == ["Temperatura máxima: 180 °C"]


def test_chunks_keep_heading_metadata_and_embedding(db_pool: ConnectionPool) -> None:
    (chunk,) = make_chunks("Revisar la mordaza", heading="PRO-014 > 2. Preparación")
    store(db_pool, make_document(), [chunk])

    with db_pool.connection() as conn:
        heading, metadata, embedding = conn.execute(
            "select heading, metadata, embedding from chunks"
        ).fetchone()
    assert heading == "PRO-014 > 2. Preparación"
    assert metadata == {"n": 0}
    assert embedding.to_list() == pytest.approx(chunk.embedding, abs=1e-6)


def test_a_failure_midway_keeps_the_previous_document_and_chunks(db_pool: ConnectionPool) -> None:
    store(db_pool, make_document(), make_chunks("uno", "dos"))
    before = document_row(db_pool)
    good, bad = make_chunks("nuevo", "roto")
    bad = ChunkRecord(index=bad.index, heading=None, text=bad.text, embedding=[0.1, 0.2])

    with pytest.raises(psycopg.errors.DataException):
        store(db_pool, make_document(embed_signature="embed-2", markdown="# Nuevo\n"), [good, bad])

    assert chunk_texts(db_pool) == ["uno", "dos"]
    assert document_row(db_pool) == before


def test_similar_chunks_returns_the_matching_chunk_first(db_pool: ConnectionPool) -> None:
    texts = [
        "Verificar la temperatura de la mordaza antes de sellar.",
        "Registrar el lote en la hoja de control.",
        "¿Qué hacer si el sellado falla? Avisar al responsable de línea.",
    ]
    store(db_pool, make_document(), make_chunks(*texts))
    (query,) = embedder.embed_documents([texts[1]])

    with db_pool.connection() as conn:
        results = similar_chunks(conn, tenant="acme", embedding=query, limit=3)

    assert results[0].chunk_text == texts[1]
    assert results[0].distance == pytest.approx(0.0, abs=1e-6)
    assert results[0].doc_id == make_doc_id("acme", "pro-014.md")
    assert [r.distance for r in results] == sorted(r.distance for r in results)


def test_similar_chunks_never_returns_another_tenants_chunks(db_pool: ConnectionPool) -> None:
    store(db_pool, make_document(tenant="acme"), make_chunks("Texto de acme"))
    store(db_pool, make_document(tenant="globex"), make_chunks("Texto de globex"))
    (query,) = embedder.embed_documents(["Texto de globex"])

    with db_pool.connection() as conn:
        results = similar_chunks(conn, tenant="acme", embedding=query, limit=10)

    assert [r.chunk_text for r in results] == ["Texto de acme"]


def test_concurrent_replacements_of_one_document_do_not_interleave(
    db_pool: ConnectionPool,
) -> None:
    store(db_pool, make_document(), make_chunks("original"))
    second_done = threading.Event()
    errors: list[BaseException] = []

    def second_upload() -> None:
        try:
            store(db_pool, make_document(embed_signature="embed-3"), make_chunks("b1", "b2"))
        except BaseException as exc:
            errors.append(exc)
        finally:
            second_done.set()

    with db_pool.connection() as conn, conn.transaction():
        document_id = upsert_document(conn, make_document(embed_signature="embed-2"))
        replace_chunks(conn, document_id, make_chunks("a1", "a2", "a3"))
        thread = threading.Thread(target=second_upload)
        thread.start()
        # The second upload must wait for this transaction's row lock.
        assert not second_done.wait(timeout=1.0)
    thread.join(timeout=10)

    assert not errors
    assert chunk_texts(db_pool) == ["b1", "b2"]
    assert document_row(db_pool)[3] == "embed-3"


def test_list_chunks_pages_in_chunk_index_order(db_pool: ConnectionPool) -> None:
    # Inserted out of order, so the order comes from the query.
    chunks = make_chunks("Paso uno.", "Paso dos.", "Paso tres.", "Paso cuatro.")
    document_id = store(db_pool, make_document(), [chunks[2], chunks[0], chunks[3], chunks[1]])

    with db_pool.connection() as conn:
        full = list_chunks(conn, document_id, limit=10, offset=0)
        middle = list_chunks(conn, document_id, limit=2, offset=1)
        past_end = list_chunks(conn, document_id, limit=2, offset=4)

    assert [c.chunk_index for c in full] == [0, 1, 2, 3]
    assert [c.chunk_text for c in middle] == ["Paso dos.", "Paso tres."]
    assert past_end == []
    first = full[0]
    assert (first.heading, first.char_count, first.embedding) == ("PRO-014 > 3. Pasos", 9, None)


def test_list_chunks_counts_characters_not_bytes(db_pool: ConnectionPool) -> None:
    document_id = store(db_pool, make_document(), make_chunks("Presión ñ"))

    with db_pool.connection() as conn:
        (chunk,) = list_chunks(conn, document_id, limit=10, offset=0)

    assert chunk.char_count == len("Presión ñ") == 9


def test_list_chunks_reads_vectors_only_when_asked(db_pool: ConnectionPool) -> None:
    chunks = make_chunks("Paso uno.")
    document_id = store(db_pool, make_document(), chunks)

    with db_pool.connection() as conn:
        (chunk,) = list_chunks(conn, document_id, limit=10, offset=0, include_embedding=True)

    assert isinstance(chunk.embedding, list) and len(chunk.embedding) == 1024
    # Stored as float4: equal to the provider's vector up to single precision.
    assert chunk.embedding == pytest.approx(chunks[0].embedding, rel=1e-6, abs=1e-7)


def test_list_chunks_never_returns_another_documents_chunks(db_pool: ConnectionPool) -> None:
    document_id = store(db_pool, make_document(), make_chunks("Propio."))
    store(db_pool, make_document(source_key="otro.md"), make_chunks("Ajeno uno.", "Ajeno dos."))

    with db_pool.connection() as conn:
        chunks = list_chunks(conn, document_id, limit=10, offset=0)

    assert [c.chunk_text for c in chunks] == ["Propio."]


def test_get_chunk_count_gives_the_row_id_and_the_stored_count(db_pool: ConnectionPool) -> None:
    document = make_document(chunk_count=2)
    document_id = store(db_pool, document, make_chunks("a", "b"))

    with db_pool.connection() as conn:
        assert get_chunk_count(conn, document.doc_id) == (document_id, 2)
        assert get_chunk_count(conn, "upload-000000000000") is None
