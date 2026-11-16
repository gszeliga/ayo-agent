"""The golden path (spec): one scripted conversation through all five phases over HTTP,
with realistic model responses and the real database, from a vague first message to a
closed case. Each turn checks the response and what the model was offered; the end checks
the stored case, its annotations, actions, traces and the session view."""

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.conversation.context import REFERENCE_TAG
from ayo_copilot.conversation.prompt_files import load_prompts
from ayo_copilot.dependencies import get_llm_provider
from ayo_copilot.llm.fake import FakeLLMProvider, text_response, tool_call, tool_calls_response
from ayo_copilot.llm.types import LLMResponse, Usage
from tests.integration.support import store_chunks

pytestmark = pytest.mark.integration

API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
TENANT = "cliente-acme"
PROMPTS = load_prompts()

FACTS = {
    "what": "Merma del 4 % en el envasado de yogur",
    "where": "Línea 2, llenadora",
    "since": "Desde el lunes 9 de noviembre",
    "standard": "Merma máxima del 1,5 %",
}
OWN_GUIDE = "Calibración del sensor de nivel de la llenadora: revisar cada 500 horas."
COMMON_GUIDE = "Método de los cinco porqués: preguntar por qué hasta llegar a la causa."
OTHER_GUIDE = "Receta reservada del cliente otro"

TOOLS_BY_PHASE = {
    "understand": ["record_field", "propose_transition"],
    "challenge": ["record_field", "log_event", "propose_transition"],
    "analyse": ["log_event", "propose_transition"],
    "action": ["add_action", "update_action", "propose_transition"],
    "followup": ["add_action", "update_action", "propose_transition"],
}


def usage(prompt: int, completion: int) -> Usage:
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        cost=0.0001,
    )


def tools(*calls: tuple[str, dict[str, Any]], text: str | None = None) -> LLMResponse:
    """A response with these calls, each with its own id, and some usage."""
    return tool_calls_response(
        *[tool_call(name, args, call_id=f"call_{i}") for i, (name, args) in enumerate(calls)],
        text=text,
        usage=usage(1200, 60),
        model="scripted/model",
    )


def say(text: str) -> LLMResponse:
    return text_response(text, usage=usage(1300, 80), model="scripted/model")


def record(field: str) -> tuple[str, dict[str, Any]]:
    return ("record_field", {"field": field, "value": FACTS[field]})


def move(target: str, reasoning: str) -> tuple[str, dict[str, Any]]:
    return ("propose_transition", {"target_state": target, "reasoning": reasoning})


def annotate(event_type: str, content: str) -> tuple[str, dict[str, Any]]:
    return ("log_event", {"event_type": event_type, "content": content})


def tool_results(call_messages: Any) -> list[dict[str, Any]]:
    return [json.loads(m.content) for m in call_messages if m.role == "tool"]


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


def fetch(pool: ConnectionPool, query: str, *params: object) -> list[tuple]:
    with pool.connection() as conn:
        return conn.execute(query, params).fetchall()


class Conversation:
    """Sends the user's messages of one session and checks each response's phase."""

    def __init__(self, client: TestClient, llm: FakeLLMProvider) -> None:
        self.client = client
        self.llm = llm
        self.session_id = uuid4()
        self.turns = 0

    def turn(
        self, text: str, *script: LLMResponse, phase: str, changed: bool
    ) -> tuple[dict[str, Any], list[Any]]:
        """Send `text` with the model's `script` queued; returns the body and the model
        calls of this turn (all of the script must be used)."""
        before = len(self.llm.calls)
        self.llm.add(*script)
        response = self.client.post(
            "/copilot/messages",
            json={"session_id": str(self.session_id), "tenant": TENANT, "text": text},
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.turns += 1
        assert body["turn"] == self.turns
        assert (body["phase"], body["phase_changed"]) == (phase, changed)
        assert self.llm.remaining == 0
        calls = self.llm.calls[before:]
        assert len(calls) == len(script)
        return body, calls


def assert_offered(call: Any, phase: str) -> None:
    assert call.tool_names == TOOLS_BY_PHASE[phase]
    assert PROMPTS.for_phase(phase) in call.system


def test_golden_path_from_a_vague_message_to_a_closed_case(
    client: TestClient, db_pool: ConnectionPool, llm: FakeLLMProvider
) -> None:
    own_chunks = store_chunks(db_pool, TENANT, [OWN_GUIDE])
    common_chunks = store_chunks(db_pool, "ayo", [COMMON_GUIDE])
    store_chunks(db_pool, "cliente-otro", [OTHER_GUIDE])
    chat = Conversation(client, llm)

    # 1. understand: a vague message gets a question, nothing recorded.
    body, calls = chat.turn(
        "Tenemos mucha merma en envasado últimamente",
        say("¿Qué producto y cuánta merma estáis viendo, y desde cuándo?"),
        phase="understand",
        changed=False,
    )
    assert body["tools_used"] == []
    assert_offered(calls[0], "understand")
    assert f"<{REFERENCE_TAG}>" not in calls[0].system  # no retrieval in understand

    # 2. understand: two facts, a question for the other two.
    body, calls = chat.turn(
        "Es yogur, un 4 % de merma, desde el lunes 9",
        tools(record("what"), record("since")),
        say("Anotado. ¿En qué línea y máquina ocurre, y cuál es la merma admitida?"),
        phase="understand",
        changed=False,
    )
    assert body["tools_used"] == [{"name": "record_field", "ok": True}] * 2

    # 3. understand -> challenge in one turn: the second call runs under challenge.
    body, calls = chat.turn(
        "En la llenadora de la línea 2. El estándar es un 1,5 % como máximo",
        tools(record("where"), record("standard"), move("challenge", "los cuatro datos")),
        say("Con eso el problema está definido. ¿Qué datos tenéis de la llenadora?"),
        phase="challenge",
        changed=True,
    )
    assert body["previous_phase"] == "understand"
    assert_offered(calls[0], "understand")
    assert_offered(calls[1], "challenge")
    assert "La fase acaba de pasar de understand a challenge" in calls[1].system
    assert body["reply"] == "Con eso el problema está definido. ¿Qué datos tenéis de la llenadora?"

    # 4. challenge: a hypothesis, and a premature move to analyse is refused.
    body, calls = chat.turn(
        "Yo creo que es la bobina de film del proveedor nuevo",
        tools(
            annotate("hypothesis", "La bobina de film del proveedor nuevo"),
            move("analyse", "el usuario tiene una sospecha"),
        ),
        say("Puede ser. ¿Habéis probado con la bobina anterior? ¿Qué pasó con la merma?"),
        phase="challenge",
        changed=False,
    )
    assert body["tools_used"] == [
        {"name": "log_event", "ok": True},
        {"name": "propose_transition", "ok": False},
    ]
    refused = tool_results(calls[1].messages)[-1]
    assert refused["error"] == "criteria_not_met"
    assert refused["missing"] == ["evidence"]

    # 5. challenge -> analyse: the hypothesis is discarded by the evidence; retrieval
    # runs after the hop, over the case's tenant and the common one only.
    body, calls = chat.turn(
        "Probamos con la bobina antigua y la merma sigue igual. El sensor de nivel marca"
        " 3 mm de más",
        tools(
            annotate("hypothesis_discarded", "La bobina de film: con la antigua sigue igual"),
            annotate("evidence", "El sensor de nivel marca 3 mm de más"),
            move("analyse", "hay evidencia"),
        ),
        say("Vamos a la causa. ¿Cuándo se calibró el sensor de nivel por última vez?"),
        phase="analyse",
        changed=True,
    )
    assert_offered(calls[0], "challenge")
    assert f"<{REFERENCE_TAG}>" not in calls[0].system
    assert_offered(calls[1], "analyse")
    reference = calls[1].system[calls[1].system.index(f"<{REFERENCE_TAG}>") :]
    assert OWN_GUIDE in reference and COMMON_GUIDE in reference
    assert OTHER_GUIDE not in calls[1].system

    # 6. analyse -> action: a validated cause.
    body, calls = chat.turn(
        "Ayer recalibramos el sensor y la merma bajó al 1,2 %. Llevaba 900 horas sin revisar",
        tools(
            annotate("validated_cause", "Sensor de nivel descalibrado: 900 h sin revisión"),
            move("action", "causa validada"),
        ),
        say("Causa confirmada. ¿Qué acciones acordáis, con responsable y fecha?"),
        phase="action",
        changed=True,
    )
    assert_offered(calls[0], "analyse")
    assert OWN_GUIDE in calls[0].system  # retrieved at the start of an analyse turn
    assert_offered(calls[1], "action")
    assert f"<{REFERENCE_TAG}>" not in calls[1].system  # action does not retrieve

    # 7. action: one action recorded, one without an owner is refused by its schema.
    body, calls = chat.turn(
        "Ana, de mantenimiento, recalibra los sensores de las tres líneas antes del 20."
        " Y hay que meter el sensor en el plan de mantenimiento preventivo",
        tools(
            (
                "add_action",
                {
                    "description": "Recalibrar los sensores de nivel de las líneas 1 a 3",
                    "owner": "Ana (mantenimiento)",
                    "due_date": "2026-11-20",
                },
            ),
            ("add_action", {"description": "Añadir el sensor al plan preventivo"}),
        ),
        say("Anotada la de Ana. ¿Quién se encarga del plan preventivo y para cuándo?"),
        phase="action",
        changed=False,
    )
    assert body["tools_used"] == [
        {"name": "add_action", "ok": True},
        {"name": "add_action", "ok": False},
    ]
    assert tool_results(calls[1].messages)[-1]["error"] == "invalid_arguments"

    # 8. action -> followup.
    body, calls = chat.turn(
        "Luis, el jefe de mantenimiento, para el 27",
        tools(
            (
                "add_action",
                {
                    "description": "Añadir la revisión del sensor al plan preventivo",
                    "owner": "Luis (jefe de mantenimiento)",
                    "due_date": "2026-11-27",
                },
            ),
            move("followup", "acciones con responsable y fecha"),
        ),
        say("Plan cerrado. Avísame cuando estén hechas."),
        phase="followup",
        changed=True,
    )
    assert_offered(calls[1], "followup")
    action_ids = [row[0] for row in fetch(db_pool, "select id from actions order by id")]
    assert len(action_ids) == 2

    # 9. followup -> closed: both actions done; no call after the case closes.
    body, calls = chat.turn(
        "Las dos acciones están hechas y la merma lleva una semana por debajo del 1,5 %",
        tools(
            ("update_action", {"action_id": action_ids[0], "status": "done"}),
            ("update_action", {"action_id": action_ids[1], "status": "done"}),
            move("closed", "acciones hechas y merma dentro del estándar"),
            text="Estupendo: cierro el caso.",
        ),
        phase="closed",
        changed=True,
    )
    assert body["reply"] == "Estupendo: cierro el caso."
    assert body["tools_used"] == [
        {"name": "update_action", "ok": True},
        {"name": "update_action", "ok": True},
        {"name": "propose_transition", "ok": True},
    ]

    # A closed case takes no more messages, and the model is not called.
    response = client.post(
        "/copilot/messages",
        json={"session_id": str(chat.session_id), "tenant": TENANT, "text": "Una cosa más"},
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "case_closed"
    assert len(llm.calls) == 16

    assert_final_state(db_pool, client, chat.session_id, own_chunks + common_chunks)


def assert_final_state(
    pool: ConnectionPool, client: TestClient, session_id: UUID, retrieved: list[UUID]
) -> None:
    ((problem_id, state, version, closed_at, *facts),) = fetch(
        pool,
        "select id, state, version, closed_at, what, where_, since, standard from problems",
    )
    assert (state, version) == ("closed", 9)
    assert closed_at is not None
    assert dict(zip(FACTS, facts, strict=True)) == FACTS

    events = fetch(
        pool,
        "select event_type, role, state_at_time from problem_events where problem_id = %s"
        " order by id",
        problem_id,
    )
    by_type: dict[str, int] = {}
    for event_type, _, _ in events:
        by_type[event_type] = by_type.get(event_type, 0) + 1
    assert by_type == {
        "message": 18,
        "hypothesis": 1,
        "hypothesis_discarded": 1,
        "evidence": 1,
        "validated_cause": 1,
    }
    messages = [(role, phase) for event_type, role, phase in events if event_type == "message"]
    # A user message carries the phase its turn started in, its reply the phase it ended in.
    phases = [
        ("understand", "understand"),
        ("understand", "understand"),
        ("understand", "challenge"),
        ("challenge", "challenge"),
        ("challenge", "analyse"),
        ("analyse", "action"),
        ("action", "action"),
        ("action", "followup"),
        ("followup", "closed"),
    ]
    assert messages == [
        pair for start, end in phases for pair in (("user", start), ("assistant", end))
    ]

    actions = fetch(
        pool,
        "select owner, due_date::text, status from actions where problem_id = %s order by id",
        problem_id,
    )
    assert actions == [
        ("Ana (mantenimiento)", "2026-11-20", "done"),
        ("Luis (jefe de mantenimiento)", "2026-11-27", "done"),
    ]

    traces = [
        row[0]
        for row in fetch(
            pool,
            "select row_to_json(t) from turn_traces t where problem_id = %s order by turn_no",
            problem_id,
        )
    ]
    assert [t["turn_no"] for t in traces] == list(range(1, 10))
    assert [(t["phase_before"], t["phase_after"]) for t in traces] == phases
    assert [t["llm_calls"] for t in traces] == [1, 2, 2, 2, 2, 2, 2, 2, 1]
    assert all(t["model"] == "scripted/model" and not t["capped"] for t in traces)
    assert traces[2]["total_tokens"] == 1260 + 1380
    assert [t["retrieval_error"] for t in traces] == [None] * 9
    retrieving = [i for i, t in enumerate(traces) if t["retrieved"]]
    assert retrieving == [4, 5]  # the hop into analyse, then the analyse turn
    for index in retrieving:
        assert {UUID(r["chunk_id"]) for r in traces[index]["retrieved"]} == set(retrieved)
    assert traces[3]["tool_calls"] == [
        {"name": "log_event", "ok": True, "error_code": None},
        {"name": "propose_transition", "ok": False, "error_code": "criteria_not_met"},
    ]
    stored = json.dumps(traces, ensure_ascii=False)
    for content in [*FACTS.values(), "3 mm", "bobina", "Ana", "cierro el caso", OWN_GUIDE]:
        assert content not in stored

    session = client.get(f"/copilot/sessions/{session_id}", headers=HEADERS).json()
    assert (session["phase"], session["version"], session["turns"]) == ("closed", 9, 9)
    assert session["fields"] == FACTS
    assert [e["event_type"] for e in session["events"]] == [
        "hypothesis",
        "hypothesis_discarded",
        "evidence",
        "validated_cause",
    ]
    assert [(a["status"], a["overdue"]) for a in session["actions"]] == [("done", False)] * 2
    assert len(session["messages"]) == 18
    assert session["messages"][-1]["content"] == "Estupendo: cierro el caso."
