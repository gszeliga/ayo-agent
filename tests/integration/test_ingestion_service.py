from collections.abc import Sequence
from pathlib import Path

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import similar_chunks
from ayo_copilot.ingestion import service
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from ayo_copilot.ingestion.service import IngestResult, chunk_document, embedding_text
from ayo_copilot.ingestion.signatures import chunker_descriptor, make_doc_id
from ayo_copilot.ingestion.storage import InvalidInputError

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "pro-014-control-sellado.md"
CONTENT = FIXTURE.read_bytes()


class FailingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        raise EmbeddingError("provider returned HTTP 503")


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"admin_api_key": "k", "embedding_provider": "fake"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimensions=1024)


def ingest(
    pool: ConnectionPool,
    embedder,
    content: bytes = CONTENT,
    *,
    settings: Settings | None = None,
    tenant: str = "acme",
    filename: str = "pro-014-control-sellado.md",
    **kwargs,
) -> IngestResult:
    return service.ingest_document(
        settings=settings or make_settings(),
        pool=pool,
        embedder=embedder,
        tenant=tenant,
        filename=filename,
        content=content,
        **kwargs,
    )


def snapshot(pool: ConnectionPool) -> tuple[list, list]:
    """Every document and chunk row, to compare the database before and after."""
    with pool.connection() as conn:
        documents = conn.execute("select * from documents order by doc_id").fetchall()
        chunks = conn.execute(
            "select document_id, chunk_index, heading, chunk_text, metadata from chunks"
            " order by document_id, chunk_index"
        ).fetchall()
    return documents, chunks


def configured_chunker(settings: Settings) -> str:
    return chunker_descriptor(
        size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        min_size=settings.min_chunk_size,
    )


def admin_columns(pool: ConnectionPool) -> tuple:
    with pool.connection() as conn:
        return conn.execute(
            "select chunk_count, (select count(*) from chunks), size_bytes, chunker_config,"
            " embedder_config from documents"
        ).fetchone()


def stored_chunks(pool: ConnectionPool) -> list[tuple]:
    with pool.connection() as conn:
        return conn.execute(
            "select chunk_index, heading, chunk_text, metadata from chunks order by chunk_index"
        ).fetchall()


def test_first_upload_indexes_the_document(db_pool: ConnectionPool, embedder) -> None:
    result = ingest(db_pool, embedder)

    doc_id = make_doc_id("acme", "pro-014-control-sellado.md")
    expected_chunks = chunk_document(CONTENT.decode(), make_settings())
    assert result.doc_id == doc_id
    assert result.status == "indexed"
    assert result.chunk_count == len(expected_chunks) > 1
    assert result.embedding_model == "voyage-4"
    assert len(result.embed_signature) == 12
    assert embedder.calls == [[embedding_text(chunk) for chunk in expected_chunks]]

    rows = stored_chunks(db_pool)
    assert [row[0] for row in rows] == list(range(len(expected_chunks)))
    assert rows[0][1].startswith("PRO-014 Control de sellado")
    assert all(row[3] == {"doc_id": doc_id, "tenant": "acme"} for row in rows)
    with db_pool.connection() as conn:
        title, markdown = conn.execute("select title, markdown from documents").fetchone()
    assert title == "PRO-014 Control de sellado"
    assert markdown == CONTENT.decode()


def test_upload_stores_counts_size_and_configs(db_pool: ConnectionPool, embedder) -> None:
    result = ingest(db_pool, embedder)

    chunk_count, stored_chunk_rows, size_bytes, chunker_config, embedder_config = admin_columns(
        db_pool
    )
    assert chunk_count == stored_chunk_rows == result.chunk_count
    assert size_bytes == len(CONTENT) > len(CONTENT.decode())  # bytes, not characters
    assert chunker_config == configured_chunker(make_settings())
    assert embedder_config == "voyage-4/document/1024"


def test_reindexing_updates_counts_size_and_configs(db_pool: ConnectionPool, embedder) -> None:
    ingest(db_pool, embedder)
    revised = b"# PRO-014 Control de sellado (rev. 2)\n\nNuevo procedimiento simplificado.\n"
    ingest(db_pool, embedder, revised)

    assert admin_columns(db_pool)[:3] == (1, 1, len(revised))

    settings = make_settings(chunk_size=300)
    ingest(db_pool, embedder, revised, settings=settings)

    assert (
        admin_columns(db_pool)[3]
        == configured_chunker(settings)
        != configured_chunker(make_settings())
    )


def test_identical_upload_is_up_to_date_without_calling_the_embedder(
    db_pool: ConnectionPool, embedder
) -> None:
    ingest(db_pool, embedder)
    before = snapshot(db_pool)

    result = ingest(db_pool, embedder)

    assert result == IngestResult(doc_id=result.doc_id, status="up_to_date")
    assert len(embedder.calls) == 1
    assert snapshot(db_pool) == before


def test_crlf_line_endings_do_not_count_as_a_change(db_pool: ConnectionPool, embedder) -> None:
    ingest(db_pool, embedder)

    result = ingest(db_pool, embedder, CONTENT.replace(b"\n", b"\r\n"))

    assert result.status == "up_to_date"


def test_force_reprocesses_identical_content(db_pool: ConnectionPool, embedder) -> None:
    ingest(db_pool, embedder)

    result = ingest(db_pool, embedder, force=True)

    assert result.status == "indexed"
    assert len(embedder.calls) == 2


def test_modified_content_replaces_the_old_chunks(db_pool: ConnectionPool, embedder) -> None:
    ingest(db_pool, embedder)
    revised = b"# PRO-014 Control de sellado (rev. 2)\n\nNuevo procedimiento simplificado.\n"

    result = ingest(db_pool, embedder, revised)

    assert result.status == "indexed"
    assert [row[2] for row in stored_chunks(db_pool)] == ["Nuevo procedimiento simplificado."]
    with db_pool.connection() as conn:
        assert conn.execute("select markdown from documents").fetchone() == (revised.decode(),)


@pytest.mark.parametrize(
    "changed", [{"chunk_size": 300}, {"embedding_model": "voyage-4-lite"}, {"min_chunk_size": 50}]
)
def test_a_configuration_change_reprocesses(
    db_pool: ConnectionPool, embedder, changed: dict
) -> None:
    ingest(db_pool, embedder)

    result = ingest(db_pool, embedder, settings=make_settings(**changed))

    assert result.status == "indexed"
    assert len(embedder.calls) == 2


def test_provider_failure_on_a_new_document_writes_nothing(db_pool: ConnectionPool) -> None:
    failing = FailingEmbedder()

    with pytest.raises(EmbeddingError):
        ingest(db_pool, failing)

    assert failing.calls == 1
    assert snapshot(db_pool) == ([], [])


def test_provider_failure_on_an_update_keeps_the_previous_version(
    db_pool: ConnectionPool, embedder
) -> None:
    ingest(db_pool, embedder)
    before = snapshot(db_pool)

    with pytest.raises(EmbeddingError):
        ingest(db_pool, FailingEmbedder(), b"# Cambiado\n\nOtro texto distinto.\n")

    assert snapshot(db_pool) == before


def test_a_failure_inside_the_transaction_keeps_the_previous_version(
    db_pool: ConnectionPool, embedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest(db_pool, embedder)
    before = snapshot(db_pool)

    def broken_replace(conn, document_id, records) -> None:
        conn.execute("delete from chunks where document_id = %s", (document_id,))
        raise RuntimeError("connection lost midway")

    monkeypatch.setattr(service, "replace_chunks", broken_replace)
    with pytest.raises(RuntimeError, match="midway"):
        ingest(db_pool, embedder, b"# Cambiado\n\nOtro texto distinto.\n")

    assert snapshot(db_pool) == before

    # The stored signature is still the old one, so the next upload does the work.
    monkeypatch.undo()
    assert ingest(db_pool, embedder, b"# Cambiado\n\nOtro texto distinto.\n").status == "indexed"


def test_same_file_name_in_two_tenants_gives_two_documents(
    db_pool: ConnectionPool, embedder
) -> None:
    first = ingest(db_pool, embedder, tenant="acme")
    second = ingest(db_pool, embedder, tenant="globex")

    assert first.doc_id != second.doc_id
    assert second.status == "indexed"
    with db_pool.connection() as conn:
        rows = conn.execute("select tenant from documents order by tenant").fetchall()
    assert rows == [("acme",), ("globex",)]


def test_source_key_defaults_to_the_bare_file_name(db_pool: ConnectionPool, embedder) -> None:
    result = ingest(db_pool, embedder, filename="C:\\Documentos\\pro-014-control-sellado.md")

    assert result.doc_id == make_doc_id("acme", "pro-014-control-sellado.md")


def test_title_and_source_key_can_be_given(db_pool: ConnectionPool, embedder) -> None:
    result = ingest(db_pool, embedder, title="Sellado", source_key="sellado.md")

    assert result.doc_id == make_doc_id("acme", "sellado.md")
    with db_pool.connection() as conn:
        assert conn.execute("select title, source_key from documents").fetchone() == (
            "Sellado",
            "sellado.md",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tenant": "../etc"}, "tenant"),
        ({"content": b"\xff\xfe"}, "UTF-8"),
        ({"content": b"  \n"}, "empty"),
        ({"content": "# Solo título\n\n---\n".encode()}, "no indexable content"),
    ],
)
def test_invalid_input_touches_neither_the_provider_nor_the_database(
    db_pool: ConnectionPool, embedder, kwargs: dict, message: str
) -> None:
    with pytest.raises(InvalidInputError, match=message):
        ingest(db_pool, embedder, **kwargs)

    assert embedder.calls == []
    assert snapshot(db_pool) == ([], [])


def test_an_uploaded_section_can_be_found_by_similarity(db_pool: ConnectionPool, embedder) -> None:
    ingest(db_pool, embedder)
    chunks = chunk_document(CONTENT.decode(), make_settings())
    target = next(chunk for chunk in chunks if "Presión" in chunk.text)
    (query,) = embedder.embed_documents([embedding_text(target)])

    with db_pool.connection() as conn:
        (best, *_) = similar_chunks(conn, tenant="acme", embedding=query, limit=3)

    assert best.chunk_index == target.index
    assert best.chunk_text == target.text
