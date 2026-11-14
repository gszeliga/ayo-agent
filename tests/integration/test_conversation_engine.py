"""The turn engine against real Postgres, with a scripted model and controlled embeddings:
the model loop, phase hops, caps, retrieval, traces, failures and conflicts (spec engine
tests 1-13). The HTTP side of failures (502, 409) is E7's."""

import json
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.conversation import engine as engine_module
from ayo_copilot.conversation.case import TurnChanges
from ayo_copilot.conversation.context import KNOWLEDGE_FAILED, REFERENCE_TAG
from ayo_copilot.conversation.engine import (
    RETRIEVAL_EMBEDDING_FAILED,
    CaseClosed,
    TurnEngine,
)
from ayo_copilot.conversation.phases import describe_missing, missing_for
from ayo_copilot.conversation.prompt_files import load_prompts
from ayo_copilot.conversation.query import build_query
from ayo_copilot.conversation.reply import FALLBACK_REPLY
from ayo_copilot.conversation.store import (
    CaseChanged,
    CaseNotFound,
    ChannelKey,
    TurnCommit,
    commit_turn,
    load_snapshot,
    resolve_case,
)
from ayo_copilot.conversation.tools import execute_tool, tools_for_phase
from ayo_copilot.db.conversations import TraceRecord
from ayo_copilot.db.repository import ChunkRecord, DocumentRecord, replace_chunks, upsert_document
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from ayo_copilot.ingestion.service import current_configs
from ayo_copilot.ingestion.signatures import make_doc_id
from ayo_copilot.llm.errors import LLMUnavailableError
from ayo_copilot.llm.fake import (
    FakeLLMProvider,
    invalid_tool_call,
    text_response,
    tool_call,
    tool_calls_response,
)
from ayo_copilot.llm.types import LLMResponse, Message, ToolSpec, Usage

pytestmark = pytest.mark.integration

TENANT = "cliente-acme"
NOW = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)
PROMPTS = load_prompts()
FACTS = {
    "what": "Merma del 4 % en el envasado",
    "where": "Línea 2, llenadora",
    "since": "Desde el lunes 9",
    "standard": "Merma máxima del 1,5 %",
}
# The tool calls that take a fresh case from `understand` to each later phase, in order.
ADVANCE: list[tuple[str, dict[str, str]]] = [
    *[("record_field", {"field": k, "value": v}) for k, v in FACTS.items()],
    ("propose_transition", {"target_state": "challenge", "reasoning": "hechos completos"}),
    ("log_event", {"event_type": "evidence", "content": "El sensor de nivel marca 3 mm de más"}),
    ("propose_transition", {"target_state": "analyse", "reasoning": "hay evidencia"}),
    ("log_event", {"event_type": "validated_cause", "content": "Sensor descalibrado"}),
    ("propose_transition", {"target_state": "action", "reasoning": "causa validada"}),
]


def make_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, admin_api_key="k", embedding_provider="fake", **overrides)


SETTINGS = make_settings()
CHUNKER, EMBEDDER = current_configs(SETTINGS)


def make_engine(
    pool: ConnectionPool,
    llm: Any,
    *,
    embedder: Any = None,
    settings: Settings = SETTINGS,
    monotonic: Callable[[], float] | None = None,
) -> TurnEngine:
    return TurnEngine(
        pool,
        llm,
        embedder or FakeEmbedder(dimensions=settings.embedding_dimensions),
        settings,
        PROMPTS,
        now=lambda: NOW,
        monotonic=monotonic or (lambda: 0.0),
    )


def new_case(pool: ConnectionPool, tenant: str = TENANT) -> UUID:
    key = ChannelKey("web", "web", str(uuid4()))
    return resolve_case(pool, key, tenant=tenant, created_by="u1").problem_id


def advance(pool: ConnectionPool, problem_id: UUID, phase: str) -> None:
    """Commit one turn that moves the case to `phase` (with the facts and annotations its
    exit criteria need)."""
    snapshot = load_snapshot(pool, problem_id, message_limit=12)
    changes = TurnChanges()
    for name, arguments in ADVANCE:
        if snapshot.case.state == phase:
            break
        outcome = execute_tool(snapshot, changes, tool_call(name, arguments))
        assert outcome.ok, outcome.result
    assert snapshot.case.state == phase
    commit_turn(
        pool,
        TurnCommit(
            snapshot=snapshot,
            phase_before="understand",
            user_message="Preparación del caso",
            reply="Hecho",
            changes=changes,
            trace=TraceRecord(prompts_version="draft-1", llm_calls=1, duration_ms=1),
        ),
    )


def fetch(pool: ConnectionPool, query: str, *params: object) -> list[tuple]:
    with pool.connection() as conn:
        return conn.execute(query, params).fetchall()


def traces(pool: ConnectionPool, problem_id: UUID) -> list[dict[str, Any]]:
    rows = fetch(
        pool,
        "select row_to_json(t) from turn_traces t where problem_id = %s order by turn_no",
        problem_id,
    )
    return [row[0] for row in rows]


def facts_calls() -> list:
    return [
        tool_call("record_field", {"field": k, "value": v}, call_id=f"call_{k}")
        for k, v in FACTS.items()
    ]


def store_chunks(pool: ConnectionPool, tenant: str, texts: Sequence[str]) -> list[UUID]:
    """A document of `tenant` whose chunks hold `texts`, embedded with the fake embedder."""
    embedder = FakeEmbedder(dimensions=SETTINGS.embedding_dimensions)
    source_key = f"{tenant}-guia.md"
    document = DocumentRecord(
        doc_id=make_doc_id(tenant, source_key),
        tenant=tenant,
        source_key=source_key,
        title=f"Guía de {tenant}",
        markdown="# Guía\n",
        content_hash="h",
        chunk_signature="c",
        embed_signature="e",
        chunk_count=len(texts),
        chunker_config=CHUNKER,
        embedder_config=EMBEDDER,
    )
    chunks = [
        ChunkRecord(index=i, heading="Guía", text=text, embedding=vector)
        for i, (text, vector) in enumerate(zip(texts, embedder.embed_documents(texts), strict=True))
    ]
    with pool.connection() as conn, conn.transaction():
        replace_chunks(conn, upsert_document(conn, document), chunks)
    rows = fetch(
        pool,
        "select c.id from chunks c join documents d on d.id = c.document_id"
        " where d.tenant = %s order by c.chunk_index",
        tenant,
    )
    return [row[0] for row in rows]


class FailingEmbedder:
    def __init__(self) -> None:
        self.query_calls: list[str] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("a turn never embeds documents")

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        raise EmbeddingError("embedding provider unreachable")


class ScriptedThenFailing:
    """Returns the scripted responses, then raises the given error."""

    def __init__(self, responses: Sequence[LLMResponse], error: Exception) -> None:
        self.fake = FakeLLMProvider(responses)
        self.error = error

    def complete(self, **kwargs: Any) -> LLMResponse:
        if not self.fake.remaining:
            raise self.error
        return self.fake.complete(**kwargs)


class BeforeFirstCall:
    """Runs `hook` once, just before delegating the first call."""

    def __init__(self, fake: FakeLLMProvider, hook: Callable[[], None]) -> None:
        self.fake = fake
        self.hook: Callable[[], None] | None = hook

    def complete(self, **kwargs: Any) -> LLMResponse:
        if self.hook is not None:
            hook, self.hook = self.hook, None
            hook()
        return self.fake.complete(**kwargs)


def tool_results(messages: Sequence[Message]) -> list[dict[str, Any]]:
    return [json.loads(m.content or "") for m in messages if m.role == "tool"]


def names(tools: Sequence[ToolSpec] | None) -> list[str]:
    return [tool.name for tool in tools or ()]


# --- 1. a plain text turn ---------------------------------------------------------------


def test_plain_text_turn_persists_messages_and_trace(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider([text_response("¿En qué línea pasa?")])

    result = make_engine(db_pool, llm).handle_turn(problem_id, "Tenemos merma en envasado")

    assert result.reply == "¿En qué línea pasa?"
    assert (result.phase_before, result.phase_after, result.version, result.turn_no) == (
        "understand",
        "understand",
        1,
        1,
    )
    assert not result.capped
    events = fetch(
        db_pool,
        "select role, event_type, content, state_at_time from problem_events order by id",
    )
    assert events == [
        ("user", "message", "Tenemos merma en envasado", "understand"),
        ("assistant", "message", "¿En qué línea pasa?", "understand"),
    ]
    assert fetch(db_pool, "select state, version from problems") == [("understand", 1)]
    (trace,) = traces(db_pool, problem_id)
    assert (trace["llm_calls"], trace["capped"], trace["tool_calls"]) == (1, False, [])
    assert (trace["phase_before"], trace["phase_after"]) == ("understand", "understand")
    # The first call: understand's prompt and tools, the user message only.
    (call,) = llm.calls
    assert PROMPTS.for_phase("understand") in call.system
    assert names(call.tools) == names(tools_for_phase("understand"))
    assert call.messages == (Message(role="user", content="Tenemos merma en envasado"),)
    assert call.model is None


def test_unknown_case_raises(db_pool: ConnectionPool) -> None:
    llm = FakeLLMProvider()
    with pytest.raises(CaseNotFound):
        make_engine(db_pool, llm).handle_turn(uuid4(), "Hola")
    assert llm.calls == []


# --- 2. an accepted transition and the call under the new phase --------------------------


def test_accepted_transition_runs_the_next_call_under_the_new_phase(
    db_pool: ConnectionPool,
) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                *facts_calls(),
                tool_call(
                    "propose_transition",
                    {"target_state": "challenge", "reasoning": "los cuatro hechos están"},
                ),
                text="Queda claro el problema.",
            ),
            text_response("¿Qué datos tenéis de la llenadora?"),
        ]
    )

    result = make_engine(db_pool, llm).handle_turn(problem_id, "Merma del 4 % en la línea 2")

    assert result.reply == "Queda claro el problema.\n\n¿Qué datos tenéis de la llenadora?"
    assert (result.phase_before, result.phase_after) == ("understand", "challenge")
    first, second = llm.calls
    assert names(first.tools) == names(tools_for_phase("understand"))
    assert PROMPTS.for_phase("challenge") in second.system
    assert "pasar de understand a challenge" in second.system
    assert names(second.tools) == names(tools_for_phase("challenge"))
    # Decision 19: the hop drops the turn's earlier tool exchange.
    assert second.messages == (Message(role="user", content="Merma del 4 % en la línea 2"),)
    row = fetch(db_pool, "select state, what, where_, since, standard, version from problems")
    assert row == [("challenge", *FACTS.values(), 1)]
    events = fetch(db_pool, "select role, state_at_time from problem_events order by id")
    assert events == [("user", "understand"), ("assistant", "challenge")]
    (trace,) = traces(db_pool, problem_id)
    assert (trace["phase_before"], trace["phase_after"], trace["llm_calls"]) == (
        "understand",
        "challenge",
        2,
    )


# --- 3. a rejected transition --------------------------------------------------------------


def test_rejected_transition_returns_the_missing_items(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                tool_call("record_field", {"field": "what", "value": FACTS["what"]}),
                tool_call(
                    "propose_transition", {"target_state": "challenge", "reasoning": "seguimos"}
                ),
            ),
            text_response("¿Dónde ocurre y cuál es el estándar?"),
        ]
    )

    result = make_engine(db_pool, llm).handle_turn(problem_id, "Hay merma")

    assert result.phase_after == "understand"
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    missing = missing_for(snapshot, "challenge")
    assert missing  # where, since, standard
    _, second = llm.calls
    assert PROMPTS.for_phase("understand") in second.system
    record, transition = tool_results(second.messages)
    assert record["ok"] is True
    assert transition == {
        "ok": False,
        "error": "criteria_not_met",
        "detail": describe_missing(missing),
        "missing": missing,
    }
    # The second call continues the exchange: user, assistant with calls, two results.
    assert [m.role for m in second.messages] == ["user", "assistant", "tool", "tool"]
    assert fetch(db_pool, "select state, what from problems") == [("understand", FACTS["what"])]


# --- 4. invalid JSON, then a valid retry ----------------------------------------------------


def test_invalid_json_is_not_executed_and_a_retry_works(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(invalid_tool_call("record_field", '{"field": "what", "value')),
            tool_calls_response(
                tool_call("record_field", {"field": "what", "value": FACTS["what"]}, call_id="c2")
            ),
            text_response("Anotado."),
        ]
    )

    make_engine(db_pool, llm).handle_turn(problem_id, "Hay merma")

    (parse_error,) = tool_results(llm.calls[1].messages)
    assert (parse_error["ok"], parse_error["error"]) == (False, "invalid_json")
    assert fetch(db_pool, "select what from problems") == [(FACTS["what"],)]
    (trace,) = traces(db_pool, problem_id)
    assert trace["tool_calls"] == [
        {"name": "record_field", "ok": False, "error_code": "invalid_json"},
        {"name": "record_field", "ok": True, "error_code": None},
    ]


# --- 5. unknown and not-offered tools -----------------------------------------------------


def test_unknown_and_not_offered_tools_are_not_executed(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                tool_call("borrar_caso", {}, call_id="c1"),
                tool_call(
                    "add_action",
                    {"description": "Calibrar", "owner": "Ana", "due_date": "2026-11-20"},
                    call_id="c2",
                ),
            ),
            text_response("Sigamos con el problema."),
        ]
    )

    make_engine(db_pool, llm).handle_turn(problem_id, "Hay merma")

    unknown, not_offered = tool_results(llm.calls[1].messages)
    assert (unknown["ok"], unknown["error"]) == (False, "unknown_tool")
    assert (not_offered["ok"], not_offered["error"]) == (False, "tool_not_offered")
    assert fetch(db_pool, "select count(*) from actions") == [(0,)]


# --- 6. the hop cap ----------------------------------------------------------------------


def test_second_transition_in_a_turn_is_refused(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    evidence = "El sensor de nivel marca 3 mm de más"
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                *facts_calls(),
                tool_call(
                    "propose_transition", {"target_state": "challenge", "reasoning": "hechos"}
                ),
            ),
            tool_calls_response(
                tool_call("log_event", {"event_type": "evidence", "content": evidence}),
                tool_call(
                    "propose_transition",
                    {"target_state": "analyse", "reasoning": "hay evidencia"},
                    call_id="call_second_hop",
                ),
            ),
            text_response("Analizaremos la causa en el próximo mensaje."),
        ]
    )

    result = make_engine(db_pool, llm).handle_turn(problem_id, "Todo el detalle de una vez")

    assert result.phase_after == "challenge"
    logged, refused = tool_results(llm.calls[2].messages)
    assert logged["ok"] is True
    assert (refused["ok"], refused["error"]) == (False, "phase_hop_limit")
    assert PROMPTS.for_phase("challenge") in llm.calls[2].system
    assert fetch(db_pool, "select state from problems") == [("challenge",)]
    assert fetch(
        db_pool,
        "select event_type, content, state_at_time from problem_events"
        " where event_type <> 'message'",
    ) == [("evidence", evidence, "challenge")]


def test_no_hops_allowed_keeps_the_phase(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                *facts_calls(),
                tool_call("propose_transition", {"target_state": "challenge", "reasoning": "x"}),
            ),
            text_response("En el próximo mensaje pasamos a los datos."),
        ]
    )
    engine = make_engine(db_pool, llm, settings=make_settings(max_phase_hops=0))

    result = engine.handle_turn(problem_id, "Hechos")

    assert result.phase_after == "understand"
    assert tool_results(llm.calls[1].messages)[-1]["error"] == "phase_hop_limit"


# --- 7. caps ----------------------------------------------------------------------------


def test_tool_round_cap_replies_with_the_fallback_and_keeps_changes(
    db_pool: ConnectionPool,
) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                tool_call("record_field", {"field": "what", "value": FACTS["what"]}, call_id="a"),
                text="Apunto el problema.",
            ),
            tool_calls_response(
                tool_call("record_field", {"field": "where", "value": FACTS["where"]}, call_id="b")
            ),
        ]
    )
    engine = make_engine(db_pool, llm, settings=make_settings(max_tool_rounds=2))

    result = engine.handle_turn(problem_id, "Hay merma en la línea 2")

    assert len(llm.calls) == 2  # no third call
    assert result.capped
    assert result.reply == f"Apunto el problema.\n\n{FALLBACK_REPLY}"
    assert fetch(db_pool, "select what, where_ from problems") == [(FACTS["what"], FACTS["where"])]
    (trace,) = traces(db_pool, problem_id)
    assert (trace["capped"], trace["llm_calls"]) == (True, 2)
    assert fetch(db_pool, "select content from problem_events where role = 'assistant'") == [
        (result.reply,)
    ]


def test_timeout_is_checked_between_calls(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    ticks = iter([0.0, 95.0])
    llm = FakeLLMProvider(
        [tool_calls_response(tool_call("record_field", {"field": "what", "value": "Merma"}))]
    )
    engine = make_engine(db_pool, llm, monotonic=lambda: next(ticks, 95.0))

    result = engine.handle_turn(problem_id, "Hay merma")

    assert len(llm.calls) == 1
    assert result.capped and result.reply == FALLBACK_REPLY
    (trace,) = traces(db_pool, problem_id)
    assert (trace["capped"], trace["duration_ms"]) == (True, 95_000)
    assert fetch(db_pool, "select what from problems") == [("Merma",)]


# --- 8. LLM failure after a change: nothing persisted ---------------------------------------


def test_llm_failure_after_a_tool_change_persists_nothing(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = ScriptedThenFailing(
        [
            tool_calls_response(
                *facts_calls(),
                tool_call("propose_transition", {"target_state": "challenge", "reasoning": "x"}),
            )
        ],
        LLMUnavailableError("the provider is unavailable", status=503),
    )

    with pytest.raises(LLMUnavailableError):
        make_engine(db_pool, llm).handle_turn(problem_id, "Hechos completos")

    assert fetch(db_pool, "select state, what, version from problems") == [("understand", None, 0)]
    assert fetch(db_pool, "select count(*) from problem_events") == [(0,)]
    assert fetch(db_pool, "select count(*) from turn_traces") == [(0,)]


# --- 9. a concurrent turn on the same case ---------------------------------------------------


def test_concurrent_turn_conflicts_and_leaves_no_partial_writes(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)

    def other_turn() -> None:
        other = make_engine(db_pool, FakeLLMProvider([text_response("Respuesta del otro")]))
        other.handle_turn(problem_id, "Mensaje del otro")

    llm = BeforeFirstCall(
        FakeLLMProvider(
            [
                tool_calls_response(
                    tool_call("record_field", {"field": "what", "value": FACTS["what"]})
                ),
                text_response("Anotado."),
            ]
        ),
        other_turn,
    )

    with pytest.raises(CaseChanged):
        make_engine(db_pool, llm).handle_turn(problem_id, "Mi mensaje")

    assert fetch(db_pool, "select what, version from problems") == [(None, 1)]
    assert fetch(db_pool, "select content from problem_events order by id") == [
        ("Mensaje del otro",),
        ("Respuesta del otro",),
    ]
    assert len(traces(db_pool, problem_id)) == 1


# --- 10. retrieval ---------------------------------------------------------------------


@pytest.fixture
def search_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    real = engine_module.search

    def spy(*args: Any, **kwargs: Any):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(engine_module, "search", spy)
    return calls


def test_no_retrieval_outside_the_retrieval_phases(
    db_pool: ConnectionPool, search_spy: list[dict[str, Any]]
) -> None:
    problem_id = new_case(db_pool)
    store_chunks(db_pool, TENANT, ["Procedimiento de calibración de la llenadora"])
    embedder = FakeEmbedder(dimensions=SETTINGS.embedding_dimensions)
    llm = FakeLLMProvider([text_response("¿Dónde ocurre?")])

    make_engine(db_pool, llm, embedder=embedder).handle_turn(problem_id, "Hay merma")

    assert search_spy == [] and embedder.query_calls == []
    assert f"<{REFERENCE_TAG}>" not in llm.calls[0].system
    assert traces(db_pool, problem_id)[0]["retrieved"] == []


def test_retrieval_in_analyse_searches_own_and_common_tenant_only(
    db_pool: ConnectionPool, search_spy: list[dict[str, Any]]
) -> None:
    problem_id = new_case(db_pool)
    advance(db_pool, problem_id, "analyse")
    own = store_chunks(db_pool, TENANT, ["Calibración del sensor de nivel de la llenadora"])
    common = store_chunks(db_pool, "ayo", ["Método de los cinco porqués"])
    store_chunks(db_pool, "cliente-otro", ["Secreto industrial del cliente otro"])
    embedder = FakeEmbedder(dimensions=SETTINGS.embedding_dimensions)
    llm = FakeLLMProvider([text_response("Revisemos la calibración.")])
    user_text = "¿Puede ser el sensor?"
    expected_query = build_query(load_snapshot(db_pool, problem_id, message_limit=12), user_text)

    make_engine(db_pool, llm, embedder=embedder).handle_turn(problem_id, user_text)

    (call,) = search_spy
    assert call["tenants"] == [TENANT, "ayo"]
    assert call["query"] == expected_query
    assert call["top_k"] == SETTINGS.retrieval_top_k
    assert call["min_similarity"] is None
    assert embedder.query_calls == [expected_query]
    system = llm.calls[0].system
    reference = system[system.index(f"<{REFERENCE_TAG}>") :]
    assert "Calibración del sensor de nivel" in reference
    assert "Método de los cinco porqués" in reference
    assert "Secreto industrial" not in system
    (trace,) = traces(db_pool, problem_id)[1:]
    assert {UUID(r["chunk_id"]) for r in trace["retrieved"]} == {*own, *common}
    assert trace["retrieval_error"] is None


def test_common_tenant_case_searches_it_once(
    db_pool: ConnectionPool, search_spy: list[dict[str, Any]]
) -> None:
    problem_id = new_case(db_pool, tenant="ayo")
    advance(db_pool, problem_id, "analyse")
    llm = FakeLLMProvider([text_response("Sigamos.")])

    make_engine(db_pool, llm).handle_turn(problem_id, "¿Qué método uso?")

    assert search_spy[0]["tenants"] == ["ayo"]


def test_embedding_failure_continues_without_knowledge(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    advance(db_pool, problem_id, "analyse")
    embedder = FailingEmbedder()
    llm = FakeLLMProvider([text_response("No puedo consultar la base ahora.")])

    result = make_engine(db_pool, llm, embedder=embedder).handle_turn(problem_id, "¿Causa?")

    assert result.reply == "No puedo consultar la base ahora."
    assert len(embedder.query_calls) == 1
    assert KNOWLEDGE_FAILED in llm.calls[0].system
    trace = traces(db_pool, problem_id)[-1]
    assert trace["retrieval_error"] == RETRIEVAL_EMBEDDING_FAILED
    assert trace["retrieved"] == []
    assert "unreachable" not in json.dumps(trace)


def test_hop_into_a_retrieving_phase_retrieves_once(
    db_pool: ConnectionPool, search_spy: list[dict[str, Any]]
) -> None:
    problem_id = new_case(db_pool)
    advance(db_pool, problem_id, "challenge")
    store_chunks(db_pool, TENANT, ["Calibración del sensor de nivel"])
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                tool_call("log_event", {"event_type": "evidence", "content": "Marca 3 mm de más"}),
                tool_call("propose_transition", {"target_state": "analyse", "reasoning": "dato"}),
            ),
            text_response("Busquemos la causa."),
        ]
    )

    make_engine(db_pool, llm).handle_turn(problem_id, "El sensor marca de más")

    first, second = llm.calls
    assert f"<{REFERENCE_TAG}>" not in first.system
    assert "Calibración del sensor de nivel" in second.system
    (call,) = search_spy
    # The query is built after the hop, so it holds the evidence the turn just logged.
    assert "Marca 3 mm de más" in call["query"]
    assert len(traces(db_pool, problem_id)[-1]["retrieved"]) == 1


def test_hop_out_of_a_retrieving_phase_drops_the_knowledge(
    db_pool: ConnectionPool, search_spy: list[dict[str, Any]]
) -> None:
    problem_id = new_case(db_pool)
    advance(db_pool, problem_id, "analyse")
    store_chunks(db_pool, TENANT, ["Calibración del sensor de nivel"])
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                tool_call("log_event", {"event_type": "validated_cause", "content": "Sensor"}),
                tool_call("propose_transition", {"target_state": "action", "reasoning": "ok"}),
            ),
            text_response("Definamos acciones."),
        ]
    )

    make_engine(db_pool, llm).handle_turn(problem_id, "Confirmado: era el sensor")

    first, second = llm.calls
    assert "Calibración del sensor de nivel" in first.system
    assert f"<{REFERENCE_TAG}>" not in second.system
    assert KNOWLEDGE_FAILED not in second.system
    assert len(search_spy) == 1


# --- 11. trace content ------------------------------------------------------------------


SENTINEL = "ZQX-CONTENIDO-PRIVADO"


def test_trace_and_log_hold_metrics_and_no_content(
    db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    problem_id = new_case(db_pool)
    advance(db_pool, problem_id, "analyse")
    chunk_ids = store_chunks(db_pool, TENANT, [f"Fragmento {SENTINEL}"])
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                tool_call("log_event", {"event_type": "hypothesis", "content": SENTINEL}),
                tool_call("nada", {"x": SENTINEL}, call_id="c2"),
                text=f"Pienso {SENTINEL}",
                usage=Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120, cost=0.25),
                model="modelo-a",
            ),
            text_response(
                f"Listo {SENTINEL}",
                usage=Usage(prompt_tokens=150, completion_tokens=30, total_tokens=180, cost=0.5),
                model="modelo-b",
            ),
        ]
    )
    caplog.set_level(logging.DEBUG)

    make_engine(db_pool, llm).handle_turn(problem_id, f"Mensaje {SENTINEL}")

    trace = traces(db_pool, problem_id)[-1]
    assert SENTINEL not in json.dumps(trace)
    assert (trace["prompt_tokens"], trace["completion_tokens"], trace["total_tokens"]) == (
        250,
        50,
        300,
    )
    assert trace["cost"] == pytest.approx(0.75)
    assert trace["model"] == "modelo-a,modelo-b"
    assert trace["llm_calls"] == 2
    assert trace["prompts_version"] == SETTINGS.prompts_version
    assert trace["tool_calls"] == [
        {"name": "log_event", "ok": True, "error_code": None},
        {"name": "nada", "ok": False, "error_code": "unknown_tool"},
    ]
    assert [UUID(r["chunk_id"]) for r in trace["retrieved"]] == chunk_ids
    assert all(set(r) == {"chunk_id", "similarity", "doc_id"} for r in trace["retrieved"])
    messages = [record.getMessage() for record in caplog.records]
    assert any("turn committed" in message for message in messages)
    assert not any(SENTINEL in message for message in messages)


def test_trace_without_usage_has_no_token_counts(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    make_engine(db_pool, FakeLLMProvider([text_response("Hola")])).handle_turn(problem_id, "Hola")
    trace = traces(db_pool, problem_id)[0]
    assert (trace["total_tokens"], trace["cost"], trace["model"]) == (None, None, None)


# --- 12. a closed case ------------------------------------------------------------------


def test_closed_case_rejects_new_messages(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    with db_pool.connection() as conn:
        conn.execute(
            "update problems set state = 'closed', closed_at = now() where id = %s", (problem_id,)
        )
    llm = FakeLLMProvider()

    with pytest.raises(CaseClosed):
        make_engine(db_pool, llm).handle_turn(problem_id, "¿Seguimos?")

    assert llm.calls == []
    assert fetch(db_pool, "select count(*) from problem_events") == [(0,)]


# --- 13. the per-phase model ------------------------------------------------------------


def test_model_by_phase_selects_the_model_per_call(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    llm = FakeLLMProvider(
        [
            tool_calls_response(
                *facts_calls(),
                tool_call("propose_transition", {"target_state": "challenge", "reasoning": "x"}),
            ),
            text_response("¿Qué datos hay?"),
        ]
    )
    settings = make_settings(llm_model_by_phase={"challenge": "modelo/challenge"})

    make_engine(db_pool, llm, settings=settings).handle_turn(problem_id, "Hechos")

    assert [call.model for call in llm.calls] == [None, "modelo/challenge"]
