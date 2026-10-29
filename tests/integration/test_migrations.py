import psycopg
import pytest
from alembic import command

from tests.integration.support import alembic_config

pytestmark = pytest.mark.integration

ZERO_VECTOR = "[" + ",".join(["0"] * 1024) + "]"


def _tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = 'public'"
    ).fetchall()
    return {name for (name,) in rows}


def test_upgrade_from_scratch_creates_schema(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        assert {"documents", "chunks", "alembic_version"} <= _tables(conn)
        assert conn.execute("select 1 from pg_extension where extname = 'vector'").fetchone()
        (column_type,) = conn.execute(
            "select format_type(atttypid, atttypmod) from pg_attribute"
            " where attrelid = 'chunks'::regclass and attname = 'embedding'"
        ).fetchone()
        assert column_type == "vector(1024)"
        assert conn.execute(
            "select data_type, is_nullable from information_schema.columns"
            " where table_name = 'documents' and column_name = 'markdown'"
        ).fetchone() == ("text", "NO")
        (index_def,) = conn.execute(
            "select indexdef from pg_indexes where indexname = 'chunks_embedding_hnsw_idx'"
        ).fetchone()
        assert "USING hnsw (embedding vector_cosine_ops)" in index_def


def test_downgrade_removes_tables_and_upgrade_works_again(scratch_database_url: str) -> None:
    config = alembic_config(scratch_database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    with psycopg.connect(scratch_database_url) as conn:
        assert not {"documents", "chunks"} & _tables(conn)

    command.upgrade(config, "head")
    with psycopg.connect(scratch_database_url) as conn:
        assert {"documents", "chunks"} <= _tables(conn)


def _insert_document(conn: psycopg.Connection, doc_id: str, source_key: str) -> str:
    (document_id,) = conn.execute(
        """
        insert into documents (doc_id, tenant, source_key, markdown,
                               content_hash, chunk_signature, embed_signature)
        values (%s, 'acme', %s, 'p', 'h', 'c', 'e') returning id
        """,
        (doc_id, source_key),
    ).fetchone()
    return document_id


def _insert_chunk(conn: psycopg.Connection, document_id: str, index: int) -> None:
    conn.execute(
        "insert into chunks (document_id, chunk_index, chunk_text, embedding)"
        " values (%s, %s, 'texto', %s::vector)",
        (document_id, index, ZERO_VECTOR),
    )


def test_deleting_a_document_cascades_to_its_chunks(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        document_id = _insert_document(conn, "upload-000000000001", "a.md")
        _insert_chunk(conn, document_id, 0)
        _insert_chunk(conn, document_id, 1)
        conn.execute("delete from documents where id = %s", (document_id,))

        assert conn.execute("select count(*) from chunks").fetchone() == (0,)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        ("doc", "documents_doc_id_key"),
        ("source", "documents_tenant_source_type_source_key_key"),
        ("chunk", "chunks_document_id_chunk_index_key"),
    ],
)
def test_unique_constraints_hold(
    scratch_database_url: str, statement: str, constraint: str
) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        document_id = _insert_document(conn, "upload-000000000001", "a.md")
        _insert_chunk(conn, document_id, 0)
        with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
            if statement == "doc":
                _insert_document(conn, "upload-000000000001", "b.md")
            elif statement == "source":
                _insert_document(conn, "upload-000000000002", "a.md")
            else:
                _insert_chunk(conn, document_id, 0)

    assert excinfo.value.diag.constraint_name == constraint


def test_embedding_dimension_is_enforced(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        document_id = _insert_document(conn, "upload-000000000001", "a.md")
        with pytest.raises(psycopg.errors.DataException):
            conn.execute(
                "insert into chunks (document_id, chunk_index, chunk_text, embedding)"
                " values (%s, 0, 'texto', '[1,2,3]'::vector)",
                (document_id,),
            )


NEW_DOCUMENT_COLUMNS = {"chunk_count", "size_bytes", "chunker_config", "embedder_config"}
LIST_INDEX = "documents_tenant_updated_at_id_idx"


def _document_columns(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "select column_name from information_schema.columns where table_name = 'documents'"
    ).fetchall()
    return {name for (name,) in rows}


def _has_index(conn: psycopg.Connection, name: str) -> bool:
    return (
        conn.execute("select 1 from pg_indexes where indexname = %s", (name,)).fetchone()
        is not None
    )


def test_0002_backfills_existing_documents(scratch_database_url: str) -> None:
    config = alembic_config(scratch_database_url)
    command.upgrade(config, "0001")
    markdown = "# Válvula de purga\n\nRevisión diaria del caudalímetro."
    with psycopg.connect(scratch_database_url) as conn:
        with_chunks = _insert_document(conn, "upload-000000000001", "a.md")
        _insert_chunk(conn, with_chunks, 0)
        _insert_chunk(conn, with_chunks, 1)
        _insert_document(conn, "upload-000000000002", "b.md")
        conn.execute(
            "update documents set markdown = %s where doc_id = 'upload-000000000002'",
            (markdown,),
        )

    command.upgrade(config, "head")

    with psycopg.connect(scratch_database_url) as conn:
        rows = conn.execute(
            "select doc_id, chunk_count, size_bytes, chunker_config, embedder_config, markdown"
            " from documents order by doc_id"
        ).fetchall()
    assert rows == [
        ("upload-000000000001", 2, 1, None, None, "p"),
        ("upload-000000000002", 0, len(markdown.encode()), None, None, markdown),
    ]
    assert len(markdown.encode()) > len(markdown)  # bytes, not characters


def test_0002_adds_columns_and_list_index(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        assert _document_columns(conn) >= NEW_DOCUMENT_COLUMNS
        (index_def,) = conn.execute(
            "select indexdef from pg_indexes where indexname = %s", (LIST_INDEX,)
        ).fetchone()
        assert "(tenant, updated_at DESC, id)" in index_def
        _insert_document(conn, "upload-000000000001", "a.md")
        assert conn.execute("select chunk_count, size_bytes from documents").fetchone() == (
            0,
            None,
        )


def test_0002_downgrade_keeps_documents(scratch_database_url: str) -> None:
    config = alembic_config(scratch_database_url)
    command.upgrade(config, "head")
    with psycopg.connect(scratch_database_url) as conn:
        _insert_document(conn, "upload-000000000001", "a.md")

    command.downgrade(config, "0001")

    with psycopg.connect(scratch_database_url) as conn:
        assert not NEW_DOCUMENT_COLUMNS & _document_columns(conn)
        assert not _has_index(conn, LIST_INDEX)
        assert conn.execute("select doc_id from documents").fetchall() == [("upload-000000000001",)]

    command.upgrade(config, "head")
    with psycopg.connect(scratch_database_url) as conn:
        assert _document_columns(conn) >= NEW_DOCUMENT_COLUMNS
        assert _has_index(conn, LIST_INDEX)
