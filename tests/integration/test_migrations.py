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


CONVERSATION_TABLES = {
    "problems",
    "problem_events",
    "actions",
    "conversation_links",
    "turn_traces",
}
CHILD_TABLES = ("problem_events", "actions", "conversation_links", "turn_traces")


def _insert_problem(conn: psycopg.Connection, tenant: str = "acme") -> str:
    (problem_id,) = conn.execute(
        "insert into problems (tenant) values (%s) returning id", (tenant,)
    ).fetchone()
    return problem_id


def _insert_children(conn: psycopg.Connection, problem_id: str) -> None:
    conn.execute(
        "insert into problem_events (problem_id, role, content, state_at_time)"
        " values (%s, 'user', 'La línea 3 para cada hora', 'understand')",
        (problem_id,),
    )
    conn.execute(
        "insert into actions (problem_id, description, owner, due_date)"
        " values (%s, 'Revisar el sensor', 'Marta', '2026-11-20')",
        (problem_id,),
    )
    conn.execute(
        "insert into conversation_links"
        " (problem_id, channel_type, external_channel_id, external_thread_id)"
        " values (%s, 'web', 'web', %s)",
        (problem_id, str(problem_id)),
    )
    conn.execute(
        "insert into turn_traces (problem_id, turn_no, phase_before, phase_after,"
        " prompts_version, llm_calls, duration_ms)"
        " values (%s, 1, 'understand', 'understand', 'draft-1', 1, 10)",
        (problem_id,),
    )


def test_0003_creates_conversation_tables_with_defaults(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        assert _tables(conn) >= CONVERSATION_TABLES
        problem_id = _insert_problem(conn)
        _insert_children(conn, problem_id)
        assert conn.execute(
            "select state, version, closed_at from problems where id = %s", (problem_id,)
        ).fetchone() == ("understand", 0, None)
        assert conn.execute("select event_type from problem_events").fetchone() == ("message",)
        assert conn.execute("select status from actions").fetchone() == ("pending",)
        assert conn.execute(
            "select tool_calls, retrieved, capped, retrieval_error from turn_traces"
        ).fetchone() == ([], [], False, None)
        for index in (
            "problems_tenant_updated_at_idx",
            "problem_events_problem_id_id_idx",
            "problem_events_problem_id_event_type_idx",
            "actions_problem_id_idx",
        ):
            assert _has_index(conn, index), index


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "insert into problems (tenant, state) values ('acme', 'follow_up')",
            "problems_state_check",
        ),
        (
            "insert into problem_events (problem_id, role, content, state_at_time)"
            " values (%(p)s, 'system', 'x', 'understand')",
            "problem_events_role_check",
        ),
        (
            "insert into problem_events (problem_id, role, content, event_type, state_at_time)"
            " values (%(p)s, 'assistant', 'x', 'root_cause', 'analyse')",
            "problem_events_event_type_check",
        ),
        (
            "insert into actions (problem_id, description, owner, due_date, status)"
            " values (%(p)s, 'x', 'Marta', '2026-11-20', 'overdue')",
            "actions_status_check",
        ),
    ],
    ids=["state", "role", "event_type", "action_status"],
)
def test_0003_check_constraints_reject_unknown_values(
    scratch_database_url: str, statement: str, constraint: str
) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        problem_id = _insert_problem(conn)
        with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
            conn.execute(statement, {"p": problem_id})

    assert excinfo.value.diag.constraint_name == constraint


UNKNOWN_PROBLEM = "00000000-0000-0000-0000-000000000000"
ORPHAN_INSERTS = {
    "problem_events": "insert into problem_events (problem_id, role, content, state_at_time)"
    " values (%s, 'user', 'x', 'understand')",
    "actions": "insert into actions (problem_id, description, owner, due_date)"
    " values (%s, 'x', 'Marta', '2026-11-20')",
    "conversation_links": "insert into conversation_links"
    " (problem_id, channel_type, external_channel_id, external_thread_id)"
    " values (%s, 'web', 'web', 'orphan')",
    "turn_traces": "insert into turn_traces (problem_id, turn_no, phase_before, phase_after,"
    " prompts_version, llm_calls, duration_ms) values (%s, 1, 'understand', 'understand',"
    " 'draft-1', 1, 10)",
}


@pytest.mark.parametrize("table", CHILD_TABLES)
def test_0003_children_need_an_existing_problem(scratch_database_url: str, table: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with (
        psycopg.connect(scratch_database_url) as conn,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        conn.execute(ORPHAN_INSERTS[table], (UNKNOWN_PROBLEM,))


def test_0003_link_is_unique_per_channel_thread(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        first, second = _insert_problem(conn), _insert_problem(conn)
        link = (
            "insert into conversation_links"
            " (problem_id, channel_type, external_channel_id, external_thread_id)"
            " values (%s, %s, 'web', 'session-1')"
        )
        conn.execute(link, (first, "web"))
        conn.execute(link, (second, "slack"))  # another channel type: allowed
        with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
            conn.execute(link, (second, "web"))

    assert excinfo.value.diag.constraint_name == "conversation_links_channel_thread_key"


def test_0003_trace_turn_numbers_are_unique_per_problem(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        problem_id = _insert_problem(conn)
        _insert_children(conn, problem_id)
        with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
            conn.execute(
                "insert into turn_traces (problem_id, turn_no, phase_before, phase_after,"
                " prompts_version, llm_calls, duration_ms)"
                " values (%s, 1, 'understand', 'challenge', 'draft-1', 2, 10)",
                (problem_id,),
            )

    assert excinfo.value.diag.constraint_name == "turn_traces_problem_id_turn_no_key"


def test_0003_deleting_a_problem_cascades(scratch_database_url: str) -> None:
    command.upgrade(alembic_config(scratch_database_url), "head")

    with psycopg.connect(scratch_database_url) as conn:
        doomed, kept = _insert_problem(conn), _insert_problem(conn)
        _insert_children(conn, doomed)
        _insert_children(conn, kept)
        conn.execute("delete from problems where id = %s", (doomed,))

        for table in CHILD_TABLES:
            rows = conn.execute(f"select problem_id from {table}").fetchall()
            assert rows == [(kept,)], table


def test_0003_downgrade_removes_conversation_tables_and_keeps_documents(
    scratch_database_url: str,
) -> None:
    config = alembic_config(scratch_database_url)
    command.upgrade(config, "head")
    with psycopg.connect(scratch_database_url) as conn:
        _insert_document(conn, "upload-000000000001", "a.md")
        _insert_children(conn, _insert_problem(conn))

    command.downgrade(config, "0002")

    with psycopg.connect(scratch_database_url) as conn:
        assert not CONVERSATION_TABLES & _tables(conn)
        assert conn.execute("select doc_id from documents").fetchall() == [("upload-000000000001",)]

    command.upgrade(config, "head")
    with psycopg.connect(scratch_database_url) as conn:
        assert _tables(conn) >= CONVERSATION_TABLES
