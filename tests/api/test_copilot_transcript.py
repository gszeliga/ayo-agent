"""Transcripts from the real database: traces read back as written, and `ayo-transcript`
on a scripted conversation held over HTTP (no model, no network)."""

import io
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import ConversationSettings, DatabaseSettings, Settings
from ayo_copilot.conversation.store import read_traces
from ayo_copilot.conversation.transcript_cli import main
from ayo_copilot.dependencies import get_llm_provider
from ayo_copilot.llm.fake import FakeLLMProvider, text_response, tool_call, tool_calls_response
from ayo_copilot.llm.types import Usage

pytestmark = pytest.mark.integration

API_KEY = "test-admin-key"
TENANT = "cliente-acme"
NOW = datetime(2026, 11, 16, 9, 30, tzinfo=UTC)


@pytest.fixture
def llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def client(
    db_pool: ConnectionPool, migrated_database_url: str, llm: FakeLLMProvider
) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        allow_remote_database=True,
        admin_api_key=API_KEY,
        embedding_provider="fake",
    )
    app = create_app(settings, docs_enabled=True)
    app.dependency_overrides[get_llm_provider] = lambda: llm
    with TestClient(app) as client:
        yield client


def send(client: TestClient, session_id: str, text: str) -> None:
    response = client.post(
        "/copilot/messages",
        json={"session_id": session_id, "tenant": TENANT, "text": text},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text


def two_turns(client: TestClient, llm: FakeLLMProvider) -> str:
    session_id = str(uuid4())
    llm.add(text_response("¿En qué línea?", usage=Usage(10, 2, 12, cost=0.001), model="m/x"))
    send(client, session_id, "Tenemos merma")
    llm.add(
        tool_calls_response(
            tool_call("record_field", {"field": "where", "value": "Línea 2"}, call_id="c1"),
            tool_call("propose_transition", {"target_state": "challenge", "reasoning": "x"}),
        ),
        text_response("Anotado. ¿Desde cuándo?"),
    )
    send(client, session_id, "En la línea 2")
    return session_id


def settings_for(url: str) -> tuple[DatabaseSettings, ConversationSettings]:
    return (
        DatabaseSettings(_env_file=None, database_url=url, allow_remote_database=True),
        ConversationSettings(_env_file=None),
    )


def test_traces_read_back_as_written(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    two_turns(client, llm)
    with db_pool.connection() as conn:
        ((problem_id,),) = conn.execute("select id from problems").fetchall()

    first, second = read_traces(db_pool, problem_id)

    assert (first.turn_no, first.phase_before, first.phase_after) == (1, "understand", "understand")
    assert first.trace.model == "m/x"
    assert (first.trace.total_tokens, first.trace.cost) == (12, 0.001)
    assert (second.turn_no, second.phase_after) == (2, "understand")
    assert [(t.name, t.ok, t.error_code) for t in second.trace.tool_calls] == [
        ("record_field", True, None),
        ("propose_transition", False, "criteria_not_met"),
    ]
    assert second.trace.llm_calls == 2 and second.trace.cost is None
    assert first.created_at is not None


def test_cli_writes_the_transcript_of_a_session(
    client: TestClient,
    llm: FakeLLMProvider,
    migrated_database_url: str,
    tmp_path: Path,
) -> None:
    session_id = two_turns(client, llm)
    out, err = io.StringIO(), io.StringIO()

    code = main(
        [session_id, "--out", str(tmp_path)],
        load_settings=lambda: settings_for(migrated_database_url),
        now=lambda: NOW,
        stdout=out,
        stderr=err,
    )

    assert code == 0, err.getvalue()
    (path,) = tmp_path.iterdir()
    assert out.getvalue().strip() == str(path)
    assert path.name == f"20261116T093000Z-{session_id[:8]}.md"
    text = path.read_text()
    assert text.index("## Turn 1 · understand") < text.index("## Turn 2 · understand")
    assert "> Tenemos merma" in text and "> Anotado. ¿Desde cuándo?" in text
    assert "propose_transition refused (criteria_not_met)" in text
    assert "| where | Línea 2 |" in text


def test_cli_refuses_an_unknown_session(migrated_database_url: str, tmp_path: Path) -> None:
    err = io.StringIO()

    code = main(
        [str(uuid4()), "--out", str(tmp_path)],
        load_settings=lambda: settings_for(migrated_database_url),
        stdout=io.StringIO(),
        stderr=err,
    )

    assert code == 1
    assert "no session" in err.getvalue()
    assert list(tmp_path.iterdir()) == []


def test_cli_keeps_the_remote_database_guard(tmp_path: Path) -> None:
    err = io.StringIO()

    def remote() -> tuple[DatabaseSettings, ConversationSettings]:
        url = "postgresql://ayo:s3cret@db.example.com:5432/ayo"
        database = DatabaseSettings(_env_file=None, database_url=url)
        return database, ConversationSettings(_env_file=None)

    code = main([str(uuid4()), "--out", str(tmp_path)], load_settings=remote, stderr=err)

    assert code == 2
    assert "ALLOW_REMOTE_DATABASE" in err.getvalue()
    assert "s3cret" not in err.getvalue()
