from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.db.repository import (
    SORT_KEYS,
    DocumentRecord,
    DocumentRow,
    get_document,
    get_markdown,
    list_documents,
    rename_document,
    upsert_document,
)
from ayo_copilot.ingestion.signatures import make_doc_id

pytestmark = pytest.mark.integration

BASE_TIME = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def add_document(
    pool: ConnectionPool,
    source_key: str,
    *,
    tenant: str = "acme",
    title: str | None = None,
    chunk_count: int = 1,
    minutes: int = 0,
) -> str:
    """Insert a document whose created_at and updated_at are BASE_TIME + `minutes`."""
    doc_id = make_doc_id(tenant, source_key)
    record = DocumentRecord(
        doc_id=doc_id,
        tenant=tenant,
        source_key=source_key,
        title=title if title is not None else source_key,
        markdown=f"# {source_key}\n\nTexto del procedimiento.\n",
        content_hash=f"hash-{source_key}",
        chunk_signature="chunk-1",
        embed_signature="embed-1",
        chunk_count=chunk_count,
        chunker_config="chunker-1",
        embedder_config="embedder-1",
    )
    stamp = BASE_TIME + timedelta(minutes=minutes)
    with pool.connection() as conn, conn.transaction():
        upsert_document(conn, record)
        conn.execute(
            "update documents set created_at = %s, updated_at = %s where doc_id = %s",
            (stamp, stamp, doc_id),
        )
    return doc_id


def page(pool: ConnectionPool, limit: int = 100, offset: int = 0, **filters) -> tuple[list, int]:
    with pool.connection() as conn:
        rows, total = list_documents(conn, limit=limit, offset=offset, **filters)
    return [row.source_key for row in rows], total


def test_lists_newest_update_first_by_default(db_pool: ConnectionPool) -> None:
    add_document(db_pool, "a.md", minutes=1)
    add_document(db_pool, "b.md", minutes=3)
    add_document(db_pool, "c.md", minutes=2)

    assert page(db_pool) == (["b.md", "c.md", "a.md"], 3)


def test_filters_by_tenant(db_pool: ConnectionPool) -> None:
    add_document(db_pool, "a.md", tenant="acme")
    add_document(db_pool, "b.md", tenant="beta")

    assert page(db_pool, tenant="beta") == (["b.md"], 1)
    assert page(db_pool, tenant="nadie") == ([], 0)


def test_q_matches_title_or_source_key_ignoring_case(db_pool: ConnectionPool) -> None:
    add_document(db_pool, "pro-014.md", title="Control de SELLADO", minutes=2)
    add_document(db_pool, "sellado-linea-2.md", title="Línea 2", minutes=1)
    add_document(db_pool, "pro-020.md", title="Limpieza de tolvas")

    assert page(db_pool, q="sellado") == (["pro-014.md", "sellado-linea-2.md"], 2)


@pytest.mark.parametrize(
    ("q", "expected"),
    [("50%", ["50%-carga.md"]), ("pro_", ["pro_014.md"]), ("a\\b", ["a\\b.md"])],
)
def test_q_treats_like_wildcards_literally(
    db_pool: ConnectionPool, q: str, expected: list[str]
) -> None:
    for source_key in ("50%-carga.md", "500-carga.md", "pro_014.md", "pro-014.md", "a\\b.md"):
        add_document(db_pool, source_key, title="Procedimiento")

    assert page(db_pool, q=q) == (expected, 1)


def test_filters_combine_and_total_counts_all_matches(db_pool: ConnectionPool) -> None:
    for i in range(3):
        add_document(db_pool, f"sellado-{i}.md", minutes=i)
    add_document(db_pool, "sellado-beta.md", tenant="beta")
    add_document(db_pool, "tolvas.md")

    assert page(db_pool, limit=1, tenant="acme", q="sellado") == (["sellado-2.md"], 3)


@pytest.mark.parametrize("key", SORT_KEYS)
def test_sorts_by_every_key_in_both_directions(db_pool: ConnectionPool, key: str) -> None:
    # Each document is first, middle or last on every key at once.
    add_document(db_pool, "uno.md", title="Alfa", chunk_count=1, minutes=1)
    add_document(db_pool, "dos.md", title="Beta", chunk_count=2, minutes=2)
    add_document(db_pool, "tres.md", title="Gamma", chunk_count=3, minutes=3)

    assert page(db_pool, sort=key)[0] == ["uno.md", "dos.md", "tres.md"]
    assert page(db_pool, sort=f"-{key}")[0] == ["tres.md", "dos.md", "uno.md"]


@pytest.mark.parametrize("sort", ["-updated_at", "title", "-chunk_count"])
def test_ties_page_through_every_row_exactly_once(db_pool: ConnectionPool, sort: str) -> None:
    for i in range(5):
        add_document(db_pool, f"doc-{i}.md", title="Mismo título", chunk_count=4)

    full, total = page(db_pool, sort=sort)
    one_by_one = [page(db_pool, limit=1, offset=i, sort=sort)[0][0] for i in range(total)]

    assert total == 5
    assert one_by_one == full
    assert sorted(full) == [f"doc-{i}.md" for i in range(5)]


def test_offset_past_the_end_returns_no_items_but_the_real_total(db_pool: ConnectionPool) -> None:
    add_document(db_pool, "a.md", minutes=1)
    add_document(db_pool, "b.md", minutes=2)

    assert page(db_pool, limit=10, offset=5) == ([], 2)
    assert page(db_pool, limit=1, offset=1)[0] == ["a.md"]


def test_unknown_sort_is_rejected(db_pool: ConnectionPool) -> None:
    with pytest.raises(ValueError, match="unknown sort key"):
        page(db_pool, sort="markdown")


def test_get_document_returns_every_column_but_the_markdown(db_pool: ConnectionPool) -> None:
    doc_id = add_document(db_pool, "pro-014.md", title="Control de sellado", chunk_count=7)

    with db_pool.connection() as conn:
        row = get_document(conn, doc_id)
        markdown = conn.execute("select markdown from documents").fetchone()[0]

    assert isinstance(row, DocumentRow)
    assert (row.doc_id, row.tenant, row.source_type, row.source_key, row.title) == (
        doc_id,
        "acme",
        "upload",
        "pro-014.md",
        "Control de sellado",
    )
    assert (row.content_hash, row.chunk_signature, row.embed_signature) == (
        "hash-pro-014.md",
        "chunk-1",
        "embed-1",
    )
    assert (row.chunk_count, row.size_bytes) == (7, len(markdown.encode()))
    assert (row.chunker_config, row.embedder_config) == ("chunker-1", "embedder-1")
    assert row.created_at == row.updated_at == BASE_TIME
    assert row.chunked_at is not None and row.embedded_at is not None
    assert not hasattr(row, "markdown")


def test_get_document_returns_none_for_an_unknown_doc_id(db_pool: ConnectionPool) -> None:
    with db_pool.connection() as conn:
        assert get_document(conn, "upload-000000000000") is None


def test_get_markdown_returns_the_stored_text(db_pool: ConnectionPool) -> None:
    doc_id = add_document(db_pool, "pro-014.md")
    add_document(db_pool, "otro.md")

    with db_pool.connection() as conn:
        assert get_markdown(conn, doc_id) == "# pro-014.md\n\nTexto del procedimiento.\n"
        assert get_markdown(conn, "upload-000000000000") is None


def test_rename_changes_only_the_title_and_updated_at(db_pool: ConnectionPool) -> None:
    doc_id = add_document(db_pool, "pro-014.md", title="Control de sellado", chunk_count=7)
    with db_pool.connection() as conn:
        before = get_document(conn, doc_id)
        markdown_before = get_markdown(conn, doc_id)

    with db_pool.connection() as conn:
        renamed = rename_document(conn, doc_id, "Control de sellado (rev. 3)")
        stored = get_document(conn, doc_id)
        markdown_after = get_markdown(conn, doc_id)

    assert renamed == stored
    assert renamed.title == "Control de sellado (rev. 3)"
    assert renamed.updated_at > BASE_TIME
    assert replace(renamed, title=before.title, updated_at=before.updated_at) == before
    assert markdown_after == markdown_before


def test_rename_to_the_same_title_changes_nothing(db_pool: ConnectionPool) -> None:
    doc_id = add_document(db_pool, "pro-014.md", title="Control de sellado")
    with db_pool.connection() as conn:
        before = get_document(conn, doc_id)

    with db_pool.connection() as conn:
        renamed = rename_document(conn, doc_id, "Control de sellado")

    assert renamed == before
    assert renamed.updated_at == BASE_TIME


def test_rename_returns_none_for_an_unknown_doc_id(db_pool: ConnectionPool) -> None:
    add_document(db_pool, "pro-014.md")

    with db_pool.connection() as conn:
        assert rename_document(conn, "upload-000000000000", "Nuevo") is None
