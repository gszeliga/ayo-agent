"""The cases endpoints through HTTP and the real database: the listing's filters, order,
pagination and row fields, and one case's detail. Cases are written with SQL, so times and
counts are exact."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.cases import MissingTurnMessage, read_case_turns, read_summary_input
from ayo_copilot.config import Settings
from ayo_copilot.conversation.prompt_files import load_prompts
from ayo_copilot.dependencies import get_llm_provider, get_today
from ayo_copilot.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMInsufficientCreditsError,
    LLMRateLimitError,
    LLMUnavailableError,
)
from ayo_copilot.llm.fake import (
    FakeLLMProvider,
    text_response,
    tool_call,
    tool_calls_response,
)
from ayo_copilot.llm.types import LLMResponse, Usage

pytestmark = pytest.mark.integration

API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
TODAY = date(2026, 11, 16)


@pytest.fixture
def client(db_pool: ConnectionPool, migrated_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        allow_remote_database=True,
        admin_api_key=API_KEY,
        embedding_provider="fake",
        # No model key: only overridden fake providers answer; a summary without one is 503.
        openrouter_api_key=None,
    )
    app = create_app(settings, docs_enabled=True)
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as client:
        yield client


def add_case(
    pool: ConnectionPool,
    *,
    tenant: str = "cliente-acme",
    state: str = "understand",
    what: str | None = None,
    updated: str = "2026-11-10 10:00+00",
    turns: int = 0,
    actions: tuple[tuple[str, str], ...] = (),
    link: tuple[str, str] | None = ("web", "web"),
) -> tuple[UUID, str]:
    """A case with `turns` traces, `actions` as (status, due date) and one link; returns
    the case id and the link's thread id."""
    thread = str(uuid4())
    with pool.connection() as conn:
        row = conn.execute(
            "insert into problems (tenant, state, what, created_at, updated_at, closed_at)"
            " values (%s, %s, %s, %s::timestamptz - interval '1 day', %s,"
            " case when %s = 'closed' then %s::timestamptz end) returning id",
            (tenant, state, what, updated, updated, state, updated),
        ).fetchone()
        assert row is not None
        problem_id = row[0]
        for turn_no in range(1, turns + 1):
            conn.execute(
                "insert into turn_traces (problem_id, turn_no, phase_before, phase_after,"
                " prompts_version, llm_calls, duration_ms)"
                " values (%s, %s, 'understand', 'understand', 'draft-1', 1, 10)",
                (problem_id, turn_no),
            )
        for status, due in actions:
            conn.execute(
                "insert into actions (problem_id, description, owner, due_date, status)"
                " values (%s, 'Recalibrar el sensor', 'Ana', %s, %s)",
                (problem_id, due, status),
            )
        if link is not None:
            conn.execute(
                "insert into conversation_links"
                " (problem_id, channel_type, external_channel_id, external_thread_id)"
                " values (%s, %s, %s, %s)",
                (problem_id, link[0], link[1], thread),
            )
    return problem_id, thread


def list_cases(client: TestClient, headers: dict[str, str] = HEADERS, **params: Any):
    return client.get("/admin/cases", params=params, headers=headers)


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["case_id"] for item in response.json()["items"]]


def test_empty_listing(client: TestClient) -> None:
    response = list_cases(client)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


def test_row_fields(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, thread = add_case(
        db_pool,
        state="action",
        what="Merma del 4 %\nen el envasado",
        updated="2026-11-13 16:02:11+00",
        turns=3,
        actions=(("pending", "2026-11-15"), ("pending", "2026-11-16"), ("done", "2026-11-01")),
    )

    [item] = list_cases(client).json()["items"]

    assert item == {
        "case_id": str(problem_id),
        "tenant": "cliente-acme",
        "title": "Merma del 4 % en el envasado",
        "phase": "action",
        "turns": 3,
        "pending_actions": 2,
        # Due today is not overdue yet; done never is.
        "overdue_actions": 1,
        "created_at": "2026-11-12T16:02:11Z",
        "updated_at": "2026-11-13T16:02:11Z",
        "closed_at": None,
        "web_session_id": thread,
    }


def test_title_is_cut_and_null_until_recorded(client: TestClient, db_pool: ConnectionPool) -> None:
    add_case(db_pool, what="a" * 81, updated="2026-11-10 10:00+00")
    add_case(db_pool, what="b" * 80, updated="2026-11-11 10:00+00")
    add_case(db_pool, what="   ", updated="2026-11-12 10:00+00")
    add_case(db_pool, what=None, updated="2026-11-13 10:00+00")

    titles = [item["title"] for item in list_cases(client).json()["items"]]

    assert titles == [None, None, "b" * 80, "a" * 79 + "…"]


def test_case_from_another_channel_has_no_web_session(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    add_case(db_pool, link=("slack", "T01-C02"))
    add_case(db_pool, link=None, updated="2026-11-11 10:00+00")

    items = list_cases(client).json()["items"]

    assert [item["web_session_id"] for item in items] == [None, None]


def test_closed_case_has_its_closing_time(client: TestClient, db_pool: ConnectionPool) -> None:
    add_case(db_pool, state="closed", updated="2026-11-14 08:00+00")

    [item] = list_cases(client).json()["items"]

    assert (item["phase"], item["closed_at"]) == ("closed", "2026-11-14T08:00:00Z")


def test_newest_update_first_and_stable_on_ties(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    old, _ = add_case(db_pool, updated="2026-11-10 10:00+00")
    new, _ = add_case(db_pool, updated="2026-11-12 10:00+00")
    tie_a, _ = add_case(db_pool, updated="2026-11-11 10:00+00")
    tie_b, _ = add_case(db_pool, updated="2026-11-11 10:00+00")
    ties = sorted([str(tie_a), str(tie_b)])

    assert ids(list_cases(client)) == [str(new), *ties, str(old)]


def test_pagination(client: TestClient, db_pool: ConnectionPool) -> None:
    created = [add_case(db_pool, updated=f"2026-11-{day} 10:00+00")[0] for day in (10, 11, 12)]

    page = list_cases(client, limit=2, offset=1).json()

    assert [item["case_id"] for item in page["items"]] == [str(created[1]), str(created[0])]
    assert (page["total"], page["limit"], page["offset"]) == (3, 2, 1)
    assert list_cases(client, offset=5).json()["items"] == []


def test_filters(client: TestClient, db_pool: ConnectionPool) -> None:
    acme_open, _ = add_case(db_pool, state="analyse", what="Merma en la llenadora")
    acme_closed, _ = add_case(
        db_pool, state="closed", what="Atasco en la etiquetadora", updated="2026-11-11 10:00+00"
    )
    beta, _ = add_case(
        db_pool, tenant="beta", state="analyse", what="MERMA de film", updated="2026-11-12 10:00+00"
    )

    assert ids(list_cases(client, tenant="beta")) == [str(beta)]
    assert ids(list_cases(client, phase="analyse")) == [str(beta), str(acme_open)]
    assert ids(list_cases(client, closed=True)) == [str(acme_closed)]
    assert ids(list_cases(client, closed=False)) == [str(beta), str(acme_open)]
    assert ids(list_cases(client, q="merma")) == [str(beta), str(acme_open)]
    assert ids(list_cases(client, q="merma", tenant="cliente-acme")) == [str(acme_open)]
    assert ids(list_cases(client, phase="closed", closed=False)) == []
    assert list_cases(client, q="merma").json()["total"] == 2
    # An empty search is no filter.
    assert len(ids(list_cases(client, q=""))) == 3


def test_search_matches_wildcards_literally(client: TestClient, db_pool: ConnectionPool) -> None:
    percent, _ = add_case(db_pool, what="Merma del 4 % en el envasado")
    add_case(db_pool, what="Merma del 4 en el envasado", updated="2026-11-11 10:00+00")
    underscore, _ = add_case(db_pool, what="Paro_largo", updated="2026-11-12 10:00+00")
    add_case(db_pool, what="Paro largo", updated="2026-11-13 10:00+00")

    assert ids(list_cases(client, q="4 %")) == [str(percent)]
    assert ids(list_cases(client, q="o_l")) == [str(underscore)]


def test_case_opened_through_the_copilot_is_listed(client: TestClient) -> None:
    llm = FakeLLMProvider([text_response("¿En qué línea?")])
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    session_id = str(uuid4())
    sent = client.post(
        "/copilot/messages",
        json={"session_id": session_id, "tenant": "cliente-acme", "text": "Hay merma"},
        headers=HEADERS,
    ).json()

    [item] = list_cases(client).json()["items"]

    assert (item["case_id"], item["web_session_id"], item["turns"]) == (
        sent["case_id"],
        session_id,
        1,
    )
    assert item["title"] is None


@pytest.mark.parametrize(
    ("params", "loc", "type"),
    [
        ({"phase": "done"}, "phase", "literal_error"),
        ({"closed": "maybe"}, "closed", "bool_parsing"),
        ({"limit": 0}, "limit", "greater_than_equal"),
        ({"limit": 101}, "limit", "less_than_equal"),
        ({"offset": -1}, "offset", "greater_than_equal"),
        ({"q": "a" * 201}, "q", "string_too_long"),
        ({"tenant": "Acme Corp"}, "tenant", "string_pattern_mismatch"),
    ],
)
def test_invalid_parameters_are_422(
    client: TestClient, params: dict[str, Any], loc: str, type: str
) -> None:
    response = list_cases(client, **params)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert (error["loc"], error["type"]) == (["query", loc], type)


def test_search_text_is_not_logged(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    add_case(db_pool, what="Merma confidencial")

    with caplog.at_level("DEBUG"):
        list_cases(client, q="confidencial")

    # The app's own loggers; uvicorn's access log drops query strings
    # (tests/unit/test_access_log.py). The test client logs full URLs, so it is excluded.
    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    assert not any("confidencial" in message for message in app_messages)


# --- get_case ------------------------------------------------------------------------------


def get_case(client: TestClient, case_id: object, headers: dict[str, str] = HEADERS):
    return client.get(f"/admin/cases/{case_id}", headers=headers)


def add_detail(pool: ConnectionPool, problem_id: UUID) -> None:
    """Facts, a version, two messages, three annotations and two actions on a case."""
    with pool.connection() as conn:
        conn.execute(
            "update problems set what = %s, where_ = %s, since = %s, standard = null,"
            " version = 5 where id = %s",
            ("Merma del 4 %\nen el envasado", "Línea 2", "Desde el lunes", problem_id),
        )
        for role, event_type, content, phase, at in [
            ("user", "message", "Hay merma", "understand", "2026-11-13 09:00+00"),
            (
                "assistant",
                "evidence",
                "El sensor marca 3 mm de más",
                "challenge",
                "2026-11-13 09:01+00",
            ),
            ("assistant", "message", "¿Desde cuándo?", "challenge", "2026-11-13 09:02+00"),
            ("assistant", "hypothesis", "Sensor descalibrado", "challenge", "2026-11-13 09:03+00"),
            (
                "assistant",
                "hypothesis_discarded",
                "Cambio de lote",
                "analyse",
                "2026-11-13 09:04+00",
            ),
        ]:
            conn.execute(
                "insert into problem_events"
                " (problem_id, role, event_type, content, state_at_time, created_at)"
                " values (%s, %s, %s, %s, %s, %s)",
                (problem_id, role, event_type, content, phase, at),
            )


def test_case_detail_fields(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, thread = add_case(
        db_pool,
        state="action",
        updated="2026-11-13 16:02:11+00",
        turns=2,
        actions=(("pending", "2026-11-15"), ("pending", "2026-11-16"), ("done", "2026-11-01")),
    )
    add_detail(db_pool, problem_id)

    response = get_case(client, problem_id)

    assert response.status_code == 200, response.text
    body = response.json()
    events = body.pop("events")
    actions = body.pop("actions")
    assert body.pop("summary") is None
    assert body == {
        "case_id": str(problem_id),
        "tenant": "cliente-acme",
        "title": "Merma del 4 % en el envasado",
        "phase": "action",
        "version": 5,
        "turns": 2,
        "created_at": "2026-11-12T16:02:11Z",
        "updated_at": "2026-11-13T16:02:11Z",
        "closed_at": None,
        "web_session_id": thread,
        "fields": {
            "what": "Merma del 4 %\nen el envasado",
            "where": "Línea 2",
            "since": "Desde el lunes",
            "standard": None,
        },
    }
    # Annotations only, oldest first; messages are not part of the case detail.
    assert [
        (e["event_type"], e["content"], e["state_at_time"], e["created_at"]) for e in events
    ] == [
        ("evidence", "El sensor marca 3 mm de más", "challenge", "2026-11-13T09:01:00Z"),
        ("hypothesis", "Sensor descalibrado", "challenge", "2026-11-13T09:03:00Z"),
        ("hypothesis_discarded", "Cambio de lote", "analyse", "2026-11-13T09:04:00Z"),
    ]
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)
    # Due today is not overdue yet; done never is.
    assert [(a["status"], a["due_date"], a["overdue"]) for a in actions] == [
        ("pending", "2026-11-15", True),
        ("pending", "2026-11-16", False),
        ("done", "2026-11-01", False),
    ]
    assert set(actions[0]) == {"id", "description", "owner", "due_date", "status", "overdue"}
    assert (actions[0]["description"], actions[0]["owner"]) == ("Recalibrar el sensor", "Ana")


def test_case_detail_has_no_messages_or_traces(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool, turns=1)
    add_detail(db_pool, problem_id)

    body = get_case(client, problem_id).json()

    assert not {"messages", "traces"} & set(body)
    assert "Hay merma" not in str(body)


def test_closed_case_from_another_channel(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(
        db_pool, state="closed", updated="2026-11-14 08:00+00", link=("slack", "C123")
    )

    body = get_case(client, problem_id).json()

    assert (body["phase"], body["closed_at"], body["web_session_id"]) == (
        "closed",
        "2026-11-14T08:00:00Z",
        None,
    )


def test_case_left_by_a_failed_first_message(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)

    body = get_case(client, problem_id).json()

    assert (body["turns"], body["version"], body["title"], body["events"], body["actions"]) == (
        0,
        0,
        None,
        [],
        [],
    )
    assert body["fields"] == {"what": None, "where": None, "since": None, "standard": None}


def test_case_detail_matches_the_session_view(client: TestClient) -> None:
    llm = FakeLLMProvider(
        [
            tool_calls_response(tool_call("record_field", {"field": "what", "value": "Merma"})),
            text_response("¿En qué línea?"),
        ]
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    session_id = str(uuid4())
    sent = client.post(
        "/copilot/messages",
        json={"session_id": session_id, "tenant": "cliente-acme", "text": "Hay merma"},
        headers=HEADERS,
    ).json()
    session = client.get(f"/copilot/sessions/{session_id}", headers=HEADERS).json()

    body = get_case(client, sent["case_id"]).json()

    assert (body["web_session_id"], body["title"], body["turns"]) == (session_id, "Merma", 1)
    for key in ("case_id", "tenant", "phase", "version", "fields", "events", "actions"):
        assert body[key] == session[key], key


def test_unknown_case_is_404(client: TestClient, db_pool: ConnectionPool) -> None:
    add_case(db_pool)

    response = get_case(client, uuid4())

    assert response.status_code == 404
    assert response.json() == {
        "detail": [{"type": "case_not_found", "loc": ["path", "case_id"], "msg": "case not found"}]
    }


def test_malformed_case_id_is_422(client: TestClient) -> None:
    response = get_case(client, "case-1")

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert (error["loc"], error["type"]) == (["path", "case_id"], "uuid_parsing")


def test_case_detail_needs_the_key(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)

    assert get_case(client, problem_id, headers={}).status_code == 401


def test_case_content_is_not_logged(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    problem_id, _ = add_case(db_pool)
    add_detail(db_pool, problem_id)

    with caplog.at_level("DEBUG"):
        assert get_case(client, problem_id).status_code == 200

    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    for secret in ("Merma", "Línea 2", "Sensor descalibrado", "Recalibrar", "Ana"):
        assert not any(secret in message for message in app_messages), secret


# --- list_case_turns -----------------------------------------------------------------------


def list_turns(client: TestClient, case_id: object, headers=HEADERS, **params: Any):
    return client.get(f"/admin/cases/{case_id}/turns", params=params, headers=headers)


def upload(client: TestClient, tenant: str, name: str, title: str = "Calibración") -> str:
    """A document through the admin API (fake embedder); returns its doc_id."""
    response = client.post(
        "/admin/documents",
        files={
            "file": (name, f"# {title}\n\nAjustar el sensor de nivel.\n".encode(), "text/markdown")
        },
        data={"tenant": tenant},
        headers=HEADERS,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["doc_id"]


def add_turn(
    pool: ConnectionPool,
    problem_id: UUID,
    turn_no: int,
    *,
    phases: tuple[str, str] = ("understand", "understand"),
    tool_calls: list[dict[str, Any]] | None = None,
    retrieved: list[dict[str, Any]] | None = None,
    annotation: bool = False,
    **trace: Any,
) -> None:
    """A committed turn as `commit_turn` writes it: the user message, an optional
    annotation, the reply and the trace."""
    before, after = phases
    with pool.connection() as conn:
        rows = [("user", "message", f"Mensaje {turn_no}", before)]
        if annotation:
            rows.append(("assistant", "evidence", f"Evidencia {turn_no}", after))
        rows.append(("assistant", "message", f"Respuesta {turn_no}", after))
        for role, event_type, content, phase in rows:
            conn.execute(
                "insert into problem_events (problem_id, role, event_type, content,"
                " state_at_time, created_at)"
                " values (%s, %s, %s, %s, %s,"
                " timestamptz '2026-11-13 09:00+00' + %s * interval '1 minute')",
                (problem_id, role, event_type, content, phase, turn_no),
            )
        values = {
            "model": "openai/gpt-4.1-mini",
            "prompts_version": "draft-1",
            "llm_calls": 1,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cost": None,
            "retrieval_error": None,
            "capped": False,
            "duration_ms": 100 + turn_no,
            **trace,
        }
        conn.execute(
            "insert into turn_traces (problem_id, turn_no, phase_before, phase_after, model,"
            " prompts_version, llm_calls, prompt_tokens, completion_tokens, total_tokens, cost,"
            " tool_calls, retrieved, retrieval_error, capped, duration_ms, created_at)"
            " values (%(problem_id)s, %(turn_no)s, %(before)s, %(after)s, %(model)s,"
            " %(prompts_version)s, %(llm_calls)s, %(prompt_tokens)s, %(completion_tokens)s,"
            " %(total_tokens)s, %(cost)s, %(tool_calls)s, %(retrieved)s, %(retrieval_error)s,"
            " %(capped)s, %(duration_ms)s,"
            " timestamptz '2026-11-13 09:00:30+00' + %(turn_no)s * interval '1 minute')",
            {
                **values,
                "problem_id": problem_id,
                "turn_no": turn_no,
                "before": before,
                "after": after,
                "tool_calls": Jsonb(tool_calls or []),
                "retrieved": Jsonb(retrieved or []),
            },
        )


def turns(response) -> list[int]:
    assert response.status_code == 200, response.text
    return [item["turn"] for item in response.json()["items"]]


def test_turn_fields(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool, state="analyse")
    add_turn(
        db_pool,
        problem_id,
        1,
        phases=("challenge", "analyse"),
        tool_calls=[
            {"name": "log_event", "ok": True, "error_code": None},
            {
                "name": "propose_transition",
                "ok": False,
                "error_code": "criteria_not_met",
                "target": "analyse",
                "missing": ["evidence"],
            },
            {
                "name": "propose_transition",
                "ok": True,
                "error_code": None,
                "target": "analyse",
                "missing": [],
            },
        ],
        llm_calls=3,
        prompt_tokens=3120,
        completion_tokens=210,
        total_tokens=3330,
        cost=Decimal("0.0021"),
        capped=True,
        retrieval_error="embedding_failed",
    )

    response = list_turns(client, problem_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (1, 20, 0)
    [item] = body["items"]
    assert item == {
        "turn": 1,
        "phase_before": "challenge",
        "phase_after": "analyse",
        "created_at": "2026-11-13T09:01:30Z",
        "user_message": {
            "content": "Mensaje 1",
            "state_at_time": "challenge",
            "created_at": "2026-11-13T09:01:00Z",
        },
        "reply": {
            "content": "Respuesta 1",
            "state_at_time": "analyse",
            "created_at": "2026-11-13T09:01:00Z",
        },
        "trace": {
            "model": "openai/gpt-4.1-mini",
            "prompts_version": "draft-1",
            "llm_calls": 3,
            "prompt_tokens": 3120,
            "completion_tokens": 210,
            "total_tokens": 3330,
            "cost": 0.0021,
            "duration_ms": 101,
            "capped": True,
            "retrieval_error": "embedding_failed",
            "tool_calls": [
                {
                    "name": "log_event",
                    "ok": True,
                    "error_code": None,
                    "target": None,
                    "missing": [],
                },
                {
                    "name": "propose_transition",
                    "ok": False,
                    "error_code": "criteria_not_met",
                    "target": "analyse",
                    "missing": ["evidence"],
                },
                {
                    "name": "propose_transition",
                    "ok": True,
                    "error_code": None,
                    "target": "analyse",
                    "missing": [],
                },
            ],
            "retrieved": [],
        },
    }


def test_old_trace_rows_have_no_target(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(
        db_pool,
        problem_id,
        1,
        tool_calls=[{"name": "propose_transition", "ok": False, "error_code": "criteria_not_met"}],
    )

    [call] = list_turns(client, problem_id).json()["items"][0]["trace"]["tool_calls"]

    assert (call["target"], call["missing"]) == (None, [])


def test_messages_are_paired_by_turn(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    for turn_no in range(1, 5):
        # Annotations sit between the messages and are not counted.
        add_turn(db_pool, problem_id, turn_no, annotation=turn_no % 2 == 1)

    items = list_turns(client, problem_id).json()["items"]

    assert [(i["turn"], i["user_message"]["content"], i["reply"]["content"]) for i in items] == [
        (n, f"Mensaje {n}", f"Respuesta {n}") for n in range(1, 5)
    ]
    assert "Evidencia" not in str(items)


def test_pages_walk_back_from_the_latest(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    for turn_no in range(1, 6):
        add_turn(db_pool, problem_id, turn_no)
    total = get_case(client, problem_id).json()["turns"]

    # As the UI does it: the latest page first, then older ones.
    pages = [
        turns(list_turns(client, problem_id, limit=2, offset=offset))
        for offset in (max(0, total - 2), total - 4, 0)
    ]

    assert total == 5
    assert pages == [[4, 5], [2, 3], [1, 2]]
    assert list_turns(client, problem_id, limit=2, offset=3).json()["total"] == 5
    assert turns(list_turns(client, problem_id, offset=5)) == []
    assert turns(list_turns(client, problem_id, offset=50)) == []
    assert turns(list_turns(client, problem_id)) == [1, 2, 3, 4, 5]


def test_a_new_turn_does_not_move_earlier_pages(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    problem_id, _ = add_case(db_pool)
    for turn_no in range(1, 4):
        add_turn(db_pool, problem_id, turn_no)
    before = list_turns(client, problem_id, limit=2, offset=0).json()["items"]

    add_turn(db_pool, problem_id, 4)

    assert list_turns(client, problem_id, limit=2, offset=0).json()["items"] == before
    assert turns(list_turns(client, problem_id, offset=3)) == [4]


def test_case_without_turns_has_an_empty_page(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)

    response = list_turns(client, problem_id)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_retrieved_documents(client: TestClient, db_pool: ConnectionPool) -> None:
    kept = upload(client, "cliente-acme", "pro-001.md", title="Calibración de la llenadora")
    gone = upload(client, "cliente-acme", "pro-002.md")
    untitled = upload(client, "cliente-acme", "pro-003.md")
    foreign = upload(client, "otro-cliente", "pro-004.md", title="Ajeno")
    assert client.delete(f"/admin/documents/{gone}", headers=HEADERS).status_code == 204
    with db_pool.connection() as conn:
        conn.execute("update documents set title = null where doc_id = %s", (untitled,))
    problem_id, _ = add_case(db_pool)
    chunk = "5b0d7c2e-9a41-4f3e-8c6d-2e1f0a9b7c34"
    add_turn(
        db_pool,
        problem_id,
        1,
        retrieved=[
            {"chunk_id": chunk, "similarity": 0.82, "doc_id": kept},
            {"chunk_id": chunk, "similarity": 0.71, "doc_id": gone},
            {"chunk_id": chunk, "similarity": 0.65, "doc_id": untitled},
            # Another tenant's document never shows its title in this case.
            {"chunk_id": chunk, "similarity": 0.6, "doc_id": foreign},
        ],
    )

    retrieved = list_turns(client, problem_id).json()["items"][0]["trace"]["retrieved"]

    assert retrieved == [
        {
            "chunk_id": chunk,
            "doc_id": kept,
            "document_title": "Calibración de la llenadora",
            "document_deleted": False,
            "chunk_index": None,
            "similarity": 0.82,
        },
        {
            "chunk_id": chunk,
            "doc_id": gone,
            "document_title": None,
            "document_deleted": True,
            "chunk_index": None,
            "similarity": 0.71,
        },
        {
            "chunk_id": chunk,
            "doc_id": untitled,
            "document_title": None,
            "document_deleted": False,
            "chunk_index": None,
            "similarity": 0.65,
        },
        {
            "chunk_id": chunk,
            "doc_id": foreign,
            "document_title": None,
            "document_deleted": True,
            "chunk_index": None,
            "similarity": 0.6,
        },
    ]


def stored_chunks(pool: ConnectionPool, doc_id: str) -> list[tuple[str, int]]:
    """A document's chunks as stored now: (chunk_id, chunk_index), in order."""
    with pool.connection() as conn:
        rows = conn.execute(
            "select c.id::text, c.chunk_index from chunks c"
            " join documents d on d.id = c.document_id where d.doc_id = %s"
            " order by c.chunk_index",
            (doc_id,),
        ).fetchall()
    return [(row[0], row[1]) for row in rows]


LONG_PROCEDURE = (
    "# Calibración de la llenadora\n\n"
    "## Preparación\n\n"
    + "Comprobar que la llenadora está parada y bloqueada antes de abrir la tapa. " * 9
    + "\n\n## Ajuste del sensor\n\n"
    + "Ajustar el sensor de nivel hasta que la lectura coincida con el patrón. " * 9
    + "\n"
)


def upload_long(client: TestClient, tenant: str, name: str) -> str:
    response = client.post(
        "/admin/documents",
        files={"file": (name, LONG_PROCEDURE.encode(), "text/markdown")},
        data={"tenant": tenant},
        headers=HEADERS,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["doc_id"]


def retrieved_of(client: TestClient, problem_id: UUID) -> list[dict[str, Any]]:
    return list_turns(client, problem_id).json()["items"][0]["trace"]["retrieved"]


def test_retrieved_chunks_carry_their_index(client: TestClient, db_pool: ConnectionPool) -> None:
    doc = upload_long(client, "cliente-acme", "pro-010.md")
    chunks = stored_chunks(db_pool, doc)
    assert len(chunks) >= 2
    problem_id, _ = add_case(db_pool)
    # Listed out of order and with a repeat, as a trace may hold them.
    picked = [chunks[-1], chunks[0], chunks[-1]]
    add_turn(
        db_pool,
        problem_id,
        1,
        retrieved=[
            {"chunk_id": chunk_id, "similarity": 0.8 - i / 10, "doc_id": doc}
            for i, (chunk_id, _) in enumerate(picked)
        ],
    )

    retrieved = retrieved_of(client, problem_id)

    assert [(r["chunk_id"], r["chunk_index"]) for r in retrieved] == picked
    assert all(r["document_deleted"] is False for r in retrieved)


def test_chunk_index_is_null_once_the_document_is_reprocessed(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    doc = upload_long(client, "cliente-acme", "pro-011.md")
    chunk_id, _ = stored_chunks(db_pool, doc)[1]
    problem_id, _ = add_case(db_pool)
    add_turn(
        db_pool,
        problem_id,
        1,
        retrieved=[{"chunk_id": chunk_id, "similarity": 0.8, "doc_id": doc}],
    )
    response = client.post(f"/admin/documents/{doc}/reprocess?force=true", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert chunk_id not in [c for c, _ in stored_chunks(db_pool, doc)]

    [chunk] = retrieved_of(client, problem_id)

    assert chunk["chunk_index"] is None
    assert chunk["document_deleted"] is False
    assert chunk["document_title"] == "Calibración de la llenadora"


def test_chunk_index_is_null_for_a_deleted_document(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    doc = upload_long(client, "cliente-acme", "pro-012.md")
    chunk_id, _ = stored_chunks(db_pool, doc)[0]
    problem_id, _ = add_case(db_pool)
    add_turn(
        db_pool,
        problem_id,
        1,
        retrieved=[{"chunk_id": chunk_id, "similarity": 0.8, "doc_id": doc}],
    )
    assert client.delete(f"/admin/documents/{doc}", headers=HEADERS).status_code == 204

    [chunk] = retrieved_of(client, problem_id)

    assert chunk["chunk_index"] is None
    assert chunk["document_deleted"] is True


def test_chunk_index_only_where_the_trace_says(client: TestClient, db_pool: ConnectionPool) -> None:
    doc = upload_long(client, "cliente-acme", "pro-013.md")
    other = upload(client, "cliente-acme", "pro-014.md")
    foreign = upload_long(client, "otro-cliente", "pro-015.md")
    chunk_id, _ = stored_chunks(db_pool, doc)[1]
    foreign_chunk, _ = stored_chunks(db_pool, foreign)[0]
    problem_id, _ = add_case(db_pool)
    add_turn(
        db_pool,
        problem_id,
        1,
        retrieved=[
            # A stored chunk recorded under another document's doc_id.
            {"chunk_id": chunk_id, "similarity": 0.8, "doc_id": other},
            # Another tenant's chunk, never resolved in this case.
            {"chunk_id": foreign_chunk, "similarity": 0.7, "doc_id": foreign},
        ],
    )

    retrieved = retrieved_of(client, problem_id)

    assert [r["chunk_index"] for r in retrieved] == [None, None]
    assert [r["document_deleted"] for r in retrieved] == [False, True]


def test_turns_of_a_copilot_conversation(client: TestClient) -> None:
    llm = FakeLLMProvider(
        [
            tool_calls_response(tool_call("record_field", {"field": "what", "value": "Merma"})),
            text_response("¿En qué línea?"),
            text_response("¿Desde cuándo?"),
        ]
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    session_id = str(uuid4())
    for text in ("Hay merma", "En la línea 2"):
        sent = client.post(
            "/copilot/messages",
            json={"session_id": session_id, "tenant": "cliente-acme", "text": text},
            headers=HEADERS,
        ).json()

    items = list_turns(client, sent["case_id"]).json()["items"]

    assert [(i["turn"], i["user_message"]["content"], i["reply"]["content"]) for i in items] == [
        (1, "Hay merma", "¿En qué línea?"),
        (2, "En la línea 2", "¿Desde cuándo?"),
    ]
    assert [c["name"] for c in items[0]["trace"]["tool_calls"]] == ["record_field"]
    assert items[1]["trace"]["tool_calls"] == []


def test_turns_of_an_unknown_case_are_404(client: TestClient) -> None:
    response = list_turns(client, uuid4())

    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "case_not_found"


@pytest.mark.parametrize(
    ("case_id", "params", "loc", "type"),
    [
        ("case-1", {}, ["path", "case_id"], "uuid_parsing"),
        (None, {"limit": 0}, ["query", "limit"], "greater_than_equal"),
        (None, {"limit": 51}, ["query", "limit"], "less_than_equal"),
        (None, {"offset": -1}, ["query", "offset"], "greater_than_equal"),
    ],
)
def test_invalid_turn_parameters_are_422(
    client: TestClient, case_id: str | None, params: dict[str, Any], loc: list[str], type: str
) -> None:
    response = list_turns(client, case_id or uuid4(), **params)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert (error["loc"], error["type"]) == (loc, type)


def test_turns_need_the_key(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)

    assert list_turns(client, problem_id, headers={}).status_code == 401


def test_turn_content_is_not_logged(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)

    with caplog.at_level("DEBUG"):
        assert list_turns(client, problem_id).status_code == 200

    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    assert not any("Mensaje" in m or "Respuesta" in m for m in app_messages)


def test_a_turn_without_its_messages_is_an_error(db_pool: ConnectionPool) -> None:
    # `commit_turn` always writes both messages with the trace; a gap is a bug, not a page.
    problem_id, _ = add_case(db_pool, turns=1)

    with pytest.raises(MissingTurnMessage):
        read_case_turns(db_pool, problem_id, limit=20, offset=0)


# --- delete_case ---------------------------------------------------------------------------


def delete_case(client: TestClient, case_id: object, headers: dict[str, str] = HEADERS):
    return client.delete(f"/admin/cases/{case_id}", headers=headers)


def row_counts(pool: ConnectionPool, problem_id: UUID) -> dict[str, int]:
    counts = {}
    with pool.connection() as conn:
        for table, column in [
            ("problems", "id"),
            ("problem_events", "problem_id"),
            ("actions", "problem_id"),
            ("conversation_links", "problem_id"),
            ("turn_traces", "problem_id"),
            ("case_summaries", "problem_id"),
        ]:
            row = conn.execute(
                f"select count(*) from {table} where {column} = %s", (problem_id,)
            ).fetchone()
            assert row is not None
            counts[table] = row[0]
    return counts


def test_delete_removes_the_case_and_what_it_owns(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    problem_id, _ = add_case(db_pool, actions=(("pending", "2026-11-20"),))
    add_turn(db_pool, problem_id, 1, annotation=True)
    add_turn(db_pool, problem_id, 2)
    add_summary(db_pool, problem_id)
    other, _ = add_case(db_pool, actions=(("done", "2026-11-01"),))
    add_turn(db_pool, other, 1)
    assert row_counts(db_pool, problem_id) == {
        "problems": 1,
        "problem_events": 5,
        "actions": 1,
        "conversation_links": 1,
        "turn_traces": 2,
        "case_summaries": 1,
    }
    other_before = row_counts(db_pool, other)

    response = delete_case(client, problem_id)

    assert response.status_code == 204
    assert response.content == b""
    assert set(row_counts(db_pool, problem_id).values()) == {0}
    assert row_counts(db_pool, other) == other_before
    assert get_case(client, problem_id).status_code == 404
    assert list_turns(client, problem_id).status_code == 404
    assert ids(list_cases(client)) == [str(other)]


def test_delete_twice_is_404(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    assert delete_case(client, problem_id).status_code == 204

    response = delete_case(client, problem_id)

    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "case_not_found"


def test_delete_a_closed_case(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool, state="closed", link=("slack", "C123"))

    assert delete_case(client, problem_id).status_code == 204
    assert get_case(client, problem_id).status_code == 404


def test_delete_needs_a_valid_id_and_the_key(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)

    malformed = delete_case(client, "case-1")
    no_key = delete_case(client, problem_id, headers={})

    assert malformed.status_code == 422
    assert malformed.json()["detail"][0]["type"] == "uuid_parsing"
    assert no_key.status_code == 401
    assert row_counts(db_pool, problem_id)["problems"] == 1


def test_delete_is_logged_without_content(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    problem_id, _ = add_case(db_pool, what="Merma confidencial", turns=0)
    add_turn(db_pool, problem_id, 1)
    add_turn(db_pool, problem_id, 2)

    with caplog.at_level("DEBUG"):
        assert delete_case(client, problem_id).status_code == 204

    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    assert f"case deleted case_id={problem_id} tenant=cliente-acme turns=2" in app_messages
    assert not any("confidencial" in m or "Mensaje" in m for m in app_messages)


def test_the_deleted_session_opens_a_new_case(client: TestClient) -> None:
    llm = FakeLLMProvider([text_response("¿En qué línea?"), text_response("¿Qué pasa?")])
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    message = {"session_id": str(uuid4()), "tenant": "cliente-acme", "text": "Hay merma"}
    first = client.post("/copilot/messages", json=message, headers=HEADERS).json()
    assert delete_case(client, first["case_id"]).status_code == 204

    second = client.post("/copilot/messages", json=message, headers=HEADERS)

    assert second.status_code == 200, second.text
    assert second.json()["case_id"] != first["case_id"]
    assert second.json()["turn"] == 1


class DeletingLLM:
    """Deletes every case while the model 'thinks', as an admin would mid-turn."""

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def complete(self, **kwargs: Any) -> LLMResponse:
        with self.pool.connection() as conn:
            conn.execute("delete from problems")
        return text_response("¿En qué línea?")


def test_a_turn_running_on_a_deleted_case_stores_nothing(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    llm = DeletingLLM(db_pool)
    client.app.dependency_overrides[get_llm_provider] = lambda: llm

    response = client.post(
        "/copilot/messages",
        json={"session_id": str(uuid4()), "tenant": "cliente-acme", "text": "Hay merma"},
        headers=HEADERS,
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"][0]["type"] == "case_changed"
    with db_pool.connection() as conn:
        for table in ("problems", "problem_events", "actions", "conversation_links", "turn_traces"):
            row = conn.execute(f"select count(*) from {table}").fetchone()
            assert row == (0,), table


# --- summary in get_case ---------------------------------------------------------------------


def add_summary(pool: ConnectionPool, problem_id: UUID, source_version: int = 0) -> None:
    with pool.connection() as conn:
        conn.execute(
            "insert into case_summaries (problem_id, content, source_version, model,"
            " prompts_version, total_tokens, cost, created_at)"
            " values (%s, 'La línea 2 pierde un 4 %%.', %s, 'openai/gpt-4.1-mini',"
            " 'summary-1', 812, 0.0004, '2026-11-13 16:05:40+00')",
            (problem_id, source_version),
        )


def test_summary_is_null_until_generated(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)

    assert get_case(client, problem_id).json()["summary"] is None


def test_summary_of_the_current_version(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    add_detail(db_pool, problem_id)  # version 5
    add_summary(db_pool, problem_id, source_version=5)

    summary = get_case(client, problem_id).json()["summary"]

    # Tokens, cost and the prompts version are stored, not exposed.
    assert summary == {
        "content": "La línea 2 pierde un 4 %.",
        "model": "openai/gpt-4.1-mini",
        "generated_at": "2026-11-13T16:05:40Z",
        "source_version": 5,
        "stale": False,
    }


def test_summary_is_stale_after_another_turn(client: TestClient, db_pool: ConnectionPool) -> None:
    llm = FakeLLMProvider([text_response("¿En qué línea?"), text_response("¿Desde cuándo?")])
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    message = {"session_id": str(uuid4()), "tenant": "cliente-acme", "text": "Hay merma"}
    sent = client.post("/copilot/messages", json=message, headers=HEADERS).json()
    case_id = UUID(sent["case_id"])
    add_summary(db_pool, case_id, source_version=get_case(client, case_id).json()["version"])
    assert get_case(client, case_id).json()["summary"]["stale"] is False

    client.post("/copilot/messages", json={**message, "text": "En la línea 2"}, headers=HEADERS)

    body = get_case(client, case_id).json()
    assert body["summary"]["stale"] is True
    assert body["summary"]["source_version"] == body["version"] - 1


def test_summary_content_is_not_logged(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    problem_id, _ = add_case(db_pool)
    add_summary(db_pool, problem_id)

    with caplog.at_level("DEBUG"):
        assert get_case(client, problem_id).status_code == 200

    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    assert not any("pierde" in message for message in app_messages)


# --- generate_case_summary -------------------------------------------------------------------

SUMMARY_TEXT = "### Problema\nLa línea 2 pierde un 4 % en el envasado."


def summarise(client: TestClient, case_id: object, headers: dict[str, str] = HEADERS):
    return client.post(f"/admin/cases/{case_id}/summary", headers=headers)


def use_llm(client: TestClient, llm: object) -> None:
    client.app.dependency_overrides[get_llm_provider] = lambda: llm


def summary_response(text: str = SUMMARY_TEXT) -> LLMResponse:
    return text_response(text, model="m-used", usage=Usage(total_tokens=812, cost=0.000412))


def stored_summaries(pool: ConnectionPool) -> list[tuple]:
    with pool.connection() as conn:
        return conn.execute(
            "select problem_id, content, source_version, model, prompts_version, total_tokens,"
            " cost from case_summaries order by problem_id"
        ).fetchall()


def case_state(pool: ConnectionPool, problem_id: UUID) -> tuple:
    with pool.connection() as conn:
        row = conn.execute(
            "select version, updated_at from problems where id = %s", (problem_id,)
        ).fetchone()
    assert row is not None
    return row


def test_summary_is_generated_stored_and_shown(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool, state="action")
    add_detail(db_pool, problem_id)  # facts, annotations, version 5
    add_turn(db_pool, problem_id, 1)
    before = case_state(db_pool, problem_id)
    llm = FakeLLMProvider([summary_response()])
    use_llm(client, llm)

    response = summarise(client, problem_id)

    assert response.status_code == 200, response.text
    body = response.json()
    generated_at = body.pop("generated_at")
    assert body == {
        "content": SUMMARY_TEXT,
        "model": "m-used",
        "source_version": 5,
        "stale": False,
    }
    assert get_case(client, problem_id).json()["summary"] == {
        **body,
        "generated_at": generated_at,
    }
    assert stored_summaries(db_pool) == [
        (problem_id, SUMMARY_TEXT, 5, "m-used", "summary-draft-1", 812, Decimal("0.000412"))
    ]
    assert case_state(db_pool, problem_id) == before
    [call] = llm.calls
    assert call.tools is None
    assert call.system.startswith(load_prompts().summary)
    for value in ("Fase actual del caso: action.", "Merma del 4 %", "Mensaje 1", "Respuesta 1"):
        assert value in call.system, value


def test_regenerating_replaces_and_clears_stale(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)
    use_llm(client, FakeLLMProvider([summary_response("Primero"), summary_response("Segundo")]))
    summarise(client, problem_id)
    with db_pool.connection() as conn:
        conn.execute("update problems set version = version + 1 where id = %s", (problem_id,))
    assert get_case(client, problem_id).json()["summary"]["stale"] is True

    body = summarise(client, problem_id).json()

    assert (body["content"], body["source_version"], body["stale"]) == ("Segundo", 1, False)
    assert [row[1] for row in stored_summaries(db_pool)] == ["Segundo"]


class WritingLLM:
    """Runs `sql` on the database while the model 'thinks', then answers."""

    def __init__(self, pool: ConnectionPool, sql: str, response: LLMResponse) -> None:
        self.pool, self.sql, self.response = pool, sql, response
        self.calls = 0

    def complete(self, **kwargs: Any) -> LLMResponse:
        self.calls += 1
        with self.pool.connection() as conn:
            conn.execute(self.sql)
        return self.response


def test_a_newer_summary_stored_meanwhile_is_kept(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)
    newer = (
        "insert into case_summaries (problem_id, content, source_version, model,"
        " prompts_version) select id, 'Más reciente', 3, 'm-otro', 'summary-draft-1'"
        " from problems; update problems set version = 3"
    )
    use_llm(client, WritingLLM(db_pool, newer, summary_response("Viejo")))

    body = summarise(client, problem_id).json()

    assert (body["content"], body["source_version"], body["stale"]) == ("Más reciente", 3, False)
    assert [row[1] for row in stored_summaries(db_pool)] == ["Más reciente"]


def test_a_case_deleted_during_the_call_is_404(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)
    use_llm(client, WritingLLM(db_pool, "delete from problems", summary_response()))

    response = summarise(client, problem_id)

    assert response.status_code == 404
    assert response.json()["detail"][0]["type"] == "case_not_found"
    assert stored_summaries(db_pool) == []


def test_unknown_case_is_404_without_a_call(client: TestClient) -> None:
    llm = FakeLLMProvider()
    use_llm(client, llm)

    response = summarise(client, uuid4())

    assert response.status_code == 404
    assert llm.calls == []


def test_a_case_without_turns_is_409_without_a_call(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    problem_id, _ = add_case(db_pool)
    llm = FakeLLMProvider()
    use_llm(client, llm)

    response = summarise(client, problem_id)

    assert response.status_code == 409
    assert response.json() == {
        "detail": [{"type": "case_empty", "loc": [], "msg": "the case has no turns to summarise"}]
    }
    assert llm.calls == []


def test_a_closed_case_can_be_summarised(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool, state="closed", link=("slack", "C123"))
    add_turn(db_pool, problem_id, 1, phases=("followup", "closed"))
    use_llm(client, FakeLLMProvider([summary_response()]))

    assert summarise(client, problem_id).status_code == 200


class RaisingLLM:
    def __init__(self, error: LLMError) -> None:
        self.error = error

    def complete(self, **kwargs: Any) -> LLMResponse:
        raise self.error


@pytest.mark.parametrize(
    ("error", "status", "type"),
    [
        (LLMConfigError("no key"), 503, "llm_not_configured"),
        (LLMUnavailableError("down", status=502), 502, "llm_unavailable"),
        (LLMRateLimitError("slow", status=429), 502, "llm_rate_limited"),
        (LLMInsufficientCreditsError("broke", status=402), 502, "llm_credits"),
        (LLMAuthError("who", status=401), 502, "llm_auth"),
        (LLMError("other"), 502, "llm_error"),
    ],
)
def test_model_failures_store_nothing(
    client: TestClient, db_pool: ConnectionPool, error: LLMError, status: int, type: str
) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)
    add_summary(db_pool, problem_id)
    before = stored_summaries(db_pool)
    use_llm(client, RaisingLLM(error))

    response = summarise(client, problem_id)

    assert response.status_code == status
    [item] = response.json()["detail"]
    assert item["type"] == type
    assert str(error) not in item["msg"]
    assert stored_summaries(db_pool) == before


def test_an_empty_reply_is_502(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)
    use_llm(client, FakeLLMProvider([text_response("  ")]))

    response = summarise(client, problem_id)

    assert response.status_code == 502
    assert response.json()["detail"][0]["type"] == "llm_error"
    assert stored_summaries(db_pool) == []


def test_without_a_model_key_it_is_503(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)

    response = summarise(client, problem_id)

    assert response.status_code == 503
    assert response.json()["detail"][0]["type"] == "llm_not_configured"


def test_summary_needs_a_valid_id_and_the_key(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    add_turn(db_pool, problem_id, 1)
    llm = FakeLLMProvider()
    use_llm(client, llm)

    assert summarise(client, "case-1").status_code == 422
    assert summarise(client, problem_id, headers={}).status_code == 401
    assert llm.calls == []


def test_summary_input_takes_the_latest_messages(db_pool: ConnectionPool) -> None:
    problem_id, _ = add_case(db_pool)
    for turn_no in range(1, 4):
        add_turn(db_pool, problem_id, turn_no, annotation=True)

    source = read_summary_input(db_pool, problem_id, message_limit=3)

    assert source is not None
    assert source.turns == 3
    assert [m.content for m in source.messages] == ["Respuesta 2", "Mensaje 3", "Respuesta 3"]
    assert source.omitted == 3
    assert [e.event_type for e in source.snapshot.events] == ["evidence"] * 3


def test_summary_content_and_prompt_are_not_logged(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    problem_id, _ = add_case(db_pool, what="Merma confidencial")
    add_turn(db_pool, problem_id, 1)
    use_llm(client, FakeLLMProvider([summary_response("Resumen secreto")]))

    with caplog.at_level("DEBUG"):
        assert summarise(client, problem_id).status_code == 200

    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    assert (
        f"case summary case_id={problem_id} tenant=cliente-acme source_version=0 stored=True"
        in app_messages
    )
    for secret in ("secreto", "confidencial", "Mensaje 1", "Problema"):
        assert not any(secret in m for m in app_messages), secret
