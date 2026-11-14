"""The copilot endpoints through HTTP, with a scripted model and the real database: cases
and links, the response, validation, tenant mismatch, the session view and the mapping
of every failure to a safe status."""

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.conversation.engine import TurnEngine
from ayo_copilot.dependencies import get_embedder, get_llm_provider
from ayo_copilot.ingestion.embedding import EmbeddingError
from ayo_copilot.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMInsufficientCreditsError,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
)
from ayo_copilot.llm.fake import FakeLLMProvider, text_response, tool_call, tool_calls_response
from ayo_copilot.llm.types import LLMResponse
from ayo_copilot.routers.copilot import get_turn_engine
from tests.integration.support import CASE_FACTS, advance_case

pytestmark = pytest.mark.integration

API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
TENANT = "cliente-acme"
MAX_TEXT = 200
# The provider's own words: never in a response.
PROVIDER_DETAIL = "upstream said: account 42 over quota"


class RaisingLLM:
    def __init__(self, error: Exception, before: Sequence[LLMResponse] = ()) -> None:
        self.fake = FakeLLMProvider(before)
        self.error = error

    def complete(self, **kwargs: Any) -> LLMResponse:
        if self.fake.remaining:
            return self.fake.complete(**kwargs)
        raise self.error


class FailingEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("provider returned HTTP 503")

    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("provider returned HTTP 503")


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
        max_user_message_chars=MAX_TEXT,
    )
    app = create_app(settings, docs_enabled=True)
    app.dependency_overrides[get_llm_provider] = lambda: llm
    with TestClient(app) as client:
        yield client


def send(client: TestClient, body: dict[str, Any], headers: dict[str, str] = HEADERS):
    return client.post("/copilot/messages", json=body, headers=headers)


def message(session_id: UUID | str, text: str = "Tenemos merma en la línea 2", **extra: Any):
    return {"session_id": str(session_id), "tenant": TENANT, "text": text, **extra}


def fetch(pool: ConnectionPool, query: str, *params: object) -> list[tuple]:
    with pool.connection() as conn:
        return conn.execute(query, params).fetchall()


def problem_of(pool: ConnectionPool, session_id: UUID) -> UUID:
    rows = fetch(
        pool,
        "select problem_id from conversation_links where external_thread_id = %s",
        str(session_id),
    )
    assert len(rows) == 1
    return rows[0][0]


# --- sending messages ---------------------------------------------------------------------


def test_first_message_opens_a_case_and_the_next_continues_it(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("¿En qué línea?"), text_response("¿Desde cuándo?"))

    first = send(client, message(session_id, user_id="operario-17"))
    second = send(client, message(session_id, "En la línea 2"))

    assert first.status_code == 200, first.text
    assert first.json() == {
        "session_id": str(session_id),
        "reply": "¿En qué línea?",
        "phase": "understand",
        "previous_phase": "understand",
        "phase_changed": False,
        "turn": 1,
        "tools_used": [],
    }
    assert second.json()["turn"] == 2
    assert fetch(db_pool, "select tenant, created_by, version from problems") == [
        (TENANT, "operario-17", 2)
    ]
    links = fetch(
        db_pool,
        "select channel_type, external_channel_id, external_thread_id from conversation_links",
    )
    assert links == [("web", "web", str(session_id))]


def test_phase_change_and_tools_are_reported(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    llm.add(
        tool_calls_response(
            *[
                tool_call("record_field", {"field": k, "value": v}, call_id=f"c_{k}")
                for k, v in CASE_FACTS.items()
            ],
            tool_call("propose_transition", {"target_state": "challenge", "reasoning": "ok"}),
            tool_call("borrar_todo", {}, call_id="c_unknown"),
        ),
        text_response("¿Qué datos tenéis?"),
    )

    body = send(client, message(uuid4(), "Los cuatro hechos")).json()

    assert (body["phase"], body["previous_phase"], body["phase_changed"]) == (
        "challenge",
        "understand",
        True,
    )
    assert body["tools_used"] == [
        *[{"name": "record_field", "ok": True}] * 4,
        {"name": "propose_transition", "ok": True},
        {"name": "borrar_todo", "ok": False},
    ]


def test_text_is_trimmed_before_the_turn(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    llm.add(text_response("Vale"))

    send(client, message(uuid4(), "  \n Hay merma \t "))

    assert llm.calls[0].messages[-1].content == "Hay merma"
    assert fetch(db_pool, "select content from problem_events where role = 'user'") == [
        ("Hay merma",)
    ]


@pytest.mark.parametrize(
    ("body", "type", "loc"),
    [
        ({"text": "   "}, "string_too_short", ["body", "text"]),
        ({"text": "a" * (MAX_TEXT + 1)}, "string_too_long", ["body", "text"]),
        ({"tenant": "Cliente ACME"}, "string_pattern_mismatch", ["body", "tenant"]),
        ({"session_id": "session-1"}, "uuid_parsing", ["body", "session_id"]),
        ({"user_id": " "}, "string_too_short", ["body", "user_id"]),
        ({"channel": "slack"}, "extra_forbidden", ["body", "channel"]),
    ],
    ids=["blank", "too long", "tenant", "session id", "user id", "extra"],
)
def test_invalid_bodies_are_rejected_and_store_nothing(
    client: TestClient,
    db_pool: ConnectionPool,
    llm: FakeLLMProvider,
    body: dict[str, Any],
    type: str,
    loc: list[str],
) -> None:
    response = send(client, {**message(uuid4()), **body})

    assert response.status_code == 422, response.text
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == (type, loc)
    assert llm.calls == []
    assert fetch(db_pool, "select count(*) from problems") == [(0,)]


def test_text_at_the_limit_is_accepted(client: TestClient, llm: FakeLLMProvider) -> None:
    llm.add(text_response("Vale"))
    assert send(client, message(uuid4(), "a" * MAX_TEXT)).status_code == 200


def test_another_tenant_gets_422_and_changes_nothing(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"))
    send(client, message(session_id))

    response = send(client, {**message(session_id), "tenant": "cliente-otro"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "tenant_mismatch",
                "loc": ["body", "tenant"],
                "msg": "the session belongs to another tenant",
            }
        ]
    }
    assert len(llm.calls) == 1
    assert fetch(db_pool, "select tenant, version from problems") == [(TENANT, 1)]


def test_closed_case_gets_409(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"))
    send(client, message(session_id))
    with db_pool.connection() as conn:
        conn.execute("update problems set state = 'closed', closed_at = now()")

    response = send(client, message(session_id))

    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "case_closed"
    assert len(llm.calls) == 1


def test_concurrent_turn_gets_409_and_no_partial_writes(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"))
    send(client, message(session_id))
    problem_id = problem_of(db_pool, session_id)
    settings = client.app_state["settings"]
    prompts = client.app_state["prompts"]

    class OtherTurnFirst:
        """Commits another turn of the same case before answering."""

        def __init__(self) -> None:
            self.fake = FakeLLMProvider(
                [
                    tool_calls_response(
                        tool_call("record_field", {"field": "what", "value": "Merma"})
                    ),
                    text_response("Anotado"),
                ]
            )
            self.done = False

        def complete(self, **kwargs: Any) -> LLMResponse:
            if not self.done:
                self.done = True
                other = FakeLLMProvider([text_response("Respuesta del otro")])
                TurnEngine(db_pool, other, FailingEmbedder(), settings, prompts).handle_turn(
                    problem_id, "Mensaje del otro"
                )
            return self.fake.complete(**kwargs)

    client.app.dependency_overrides[get_llm_provider] = OtherTurnFirst

    response = send(client, message(session_id, "Mi mensaje"))

    assert response.status_code == 409, response.text
    assert response.json()["detail"][0] == {
        "type": "case_changed",
        "loc": [],
        "msg": "the case changed while processing, try again",
    }
    assert fetch(db_pool, "select what, version from problems") == [(None, 2)]
    contents = [row[0] for row in fetch(db_pool, "select content from problem_events")]
    assert "Mi mensaje" not in contents


@pytest.mark.parametrize(
    ("error", "status", "type"),
    [
        (LLMUnavailableError(PROVIDER_DETAIL, status=503), 502, "llm_unavailable"),
        (LLMRateLimitError(PROVIDER_DETAIL, status=429), 502, "llm_rate_limited"),
        (LLMInsufficientCreditsError(PROVIDER_DETAIL, status=402), 502, "llm_credits"),
        (LLMAuthError(PROVIDER_DETAIL, status=401), 502, "llm_auth"),
        (LLMBadRequestError(PROVIDER_DETAIL, status=400), 502, "llm_error"),
        (LLMResponseError(PROVIDER_DETAIL), 502, "llm_error"),
        (LLMError(PROVIDER_DETAIL), 502, "llm_error"),
        (LLMConfigError(PROVIDER_DETAIL), 503, "llm_not_configured"),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_model_failures_map_to_safe_errors_and_store_no_turn(
    client: TestClient,
    db_pool: ConnectionPool,
    caplog: pytest.LogCaptureFixture,
    error: LLMError,
    status: int,
    type: str,
) -> None:
    # The failure comes after a tool call already changed the snapshot.
    before = [tool_calls_response(tool_call("record_field", {"field": "what", "value": "Merma"}))]
    client.app.dependency_overrides[get_llm_provider] = lambda: RaisingLLM(error, before)

    response = send(client, message(uuid4(), "Hay merma"))

    assert response.status_code == status
    (item,) = response.json()["detail"]
    assert (item["type"], item["loc"]) == (type, [])
    assert PROVIDER_DETAIL not in response.text
    assert not any(PROVIDER_DETAIL in record.getMessage() for record in caplog.records)
    assert fetch(db_pool, "select what, version from problems") == [(None, 0)]
    assert fetch(db_pool, "select count(*) from problem_events") == [(0,)]
    assert fetch(db_pool, "select count(*) from turn_traces") == [(0,)]


def test_unconfigured_model_is_503_without_an_override(
    db_pool: ConnectionPool, migrated_database_url: str
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        allow_remote_database=True,
        admin_api_key=API_KEY,
        embedding_provider="fake",
        openrouter_api_key=None,
    )
    with TestClient(create_app(settings, docs_enabled=True)) as client:
        response = send(client, message(uuid4()))

    assert response.status_code == 503
    assert response.json()["detail"][0]["type"] == "llm_not_configured"


def test_knowledge_base_failure_does_not_fail_the_turn(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"), text_response("No puedo consultar la base ahora."))
    send(client, message(session_id))
    advance_case(db_pool, problem_of(db_pool, session_id), "analyse")
    client.app.dependency_overrides[get_embedder] = FailingEmbedder

    response = send(client, message(session_id, "¿Cuál puede ser la causa?"))

    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "analyse"


# --- the session view -------------------------------------------------------------------


def use_today(client: TestClient, today: datetime) -> None:
    def engine() -> TurnEngine:
        state = client.app_state
        return TurnEngine(
            state["pool"],
            FakeLLMProvider(),
            state["embedder"],
            state["settings"],
            state["prompts"],
            now=lambda: today,
        )

    client.app.dependency_overrides[get_turn_engine] = engine


def get_session(client: TestClient, session_id: UUID | str, headers: dict[str, str] = HEADERS):
    return client.get(f"/copilot/sessions/{session_id}", headers=headers)


def test_session_view_shows_the_case(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("¿En qué línea?"))
    send(client, message(session_id))
    problem_id = problem_of(db_pool, session_id)
    advance_case(db_pool, problem_id, "action")
    with db_pool.connection() as conn:
        conn.execute(
            "insert into actions (problem_id, description, owner, due_date, status) values"
            " (%(p)s, 'Recalibrar el sensor', 'Ana', '2026-11-10', 'pending'),"
            " (%(p)s, 'Revisar el registro', 'Luis', '2026-11-10', 'done'),"
            " (%(p)s, 'Formar al turno de noche', 'Marta', '2026-11-20', 'pending')",
            {"p": problem_id},
        )
    use_today(client, datetime(2026, 11, 11, 23, 30, tzinfo=UTC))

    response = get_session(client, session_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == str(session_id)
    assert (body["tenant"], body["phase"], body["version"], body["turns"]) == (
        TENANT,
        "action",
        2,
        2,
    )
    assert body["fields"] == CASE_FACTS
    assert [e["event_type"] for e in body["events"]] == ["evidence", "validated_cause"]
    assert [e["state_at_time"] for e in body["events"]] == ["challenge", "analyse"]
    assert all(e["created_at"].endswith("Z") for e in body["events"])
    assert [(a["owner"], a["status"], a["overdue"]) for a in body["actions"]] == [
        ("Ana", "pending", True),
        ("Luis", "done", False),
        ("Marta", "pending", False),
    ]
    assert [(m["role"], m["state_at_time"]) for m in body["messages"]] == [
        ("user", "understand"),
        ("assistant", "understand"),
        ("user", "understand"),
        ("assistant", "action"),
    ]
    assert set(body) == {
        "session_id",
        "tenant",
        "phase",
        "version",
        "turns",
        "fields",
        "events",
        "actions",
        "messages",
    }


def test_overdue_uses_the_app_time_zone(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"))
    send(client, message(session_id))
    with db_pool.connection() as conn:
        conn.execute(
            "insert into actions (problem_id, description, owner, due_date) values"
            " (%s, 'Recalibrar', 'Ana', '2026-11-11')",
            (problem_of(db_pool, session_id),),
        )

    def overdue() -> bool:
        return get_session(client, session_id).json()["actions"][0]["overdue"]

    use_today(client, datetime(2026, 11, 11, 22, 30, tzinfo=UTC))  # 23:30 in Madrid
    assert overdue() is False
    use_today(client, datetime(2026, 11, 11, 23, 30, tzinfo=UTC))  # 00:30 on the 12th
    assert overdue() is True


def test_new_session_view_has_empty_facts(client: TestClient, llm: FakeLLMProvider) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"))
    send(client, message(session_id))

    body = get_session(client, session_id).json()

    assert body["fields"] == {"what": None, "where": None, "since": None, "standard": None}
    assert (body["events"], body["actions"], len(body["messages"])) == ([], [], 2)


def test_unknown_session_is_404(client: TestClient) -> None:
    response = get_session(client, uuid4())

    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "session_not_found"


def test_malformed_session_id_is_422(client: TestClient) -> None:
    response = get_session(client, "session-1")

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "uuid_parsing"


def test_session_id_case_does_not_matter(client: TestClient, llm: FakeLLMProvider) -> None:
    session_id = uuid4()
    llm.add(text_response("Hola"), text_response("Seguimos"))
    send(client, message(str(session_id).upper()))

    assert send(client, message(session_id)).json()["turn"] == 2
    assert get_session(client, str(session_id).upper()).status_code == 200
