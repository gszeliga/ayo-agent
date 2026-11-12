from typing import Any

import pytest

from ayo_copilot.llm.check.evaluate import evaluate
from ayo_copilot.llm.check.scenarios import build_scenarios
from ayo_copilot.llm.fake import invalid_tool_call, text_response, tool_call, tool_calls_response
from ayo_copilot.llm.types import LLMResponse, ToolCall

S = {s.id: s for s in build_scenarios()}
SECRET = "valor confidencial del cliente 4,2 bar"


def calls(*specs: tuple[str, dict[str, Any]], text: str | None = None) -> LLMResponse:
    return tool_calls_response(
        *(tool_call(name, args, call_id=f"c{i}") for i, (name, args) in enumerate(specs)),
        text=text,
    )


def record(field: str) -> tuple[str, dict[str, Any]]:
    return ("record_field", {"field": field, "value": "dato"})


def event(event_type: str) -> tuple[str, dict[str, Any]]:
    return ("log_event", {"event_type": event_type, "content": "hecho"})


def transition(target: str) -> tuple[str, dict[str, Any]]:
    return ("propose_transition", {"target_state": target, "reasoning": "motivo"})


# --- Checks on every call ---------------------------------------------------


def test_invalid_json() -> None:
    response = tool_calls_response(invalid_tool_call("record_field", "{nope"))

    verdict = evaluate(S["understand_all_facts"], response)

    assert "invalid_json" in verdict.failures
    assert verdict.bad_argument_calls == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"field": "why", "value": "x"},  # not in the enum
        {"field": "what"},  # missing value
        {"field": "what", "value": "x", "extra": 1},  # additional property
        {"field": "what", "value": ""},  # too short
    ],
)
def test_schema_violations(arguments: dict[str, Any]) -> None:
    verdict = evaluate(S["understand_all_facts"], calls(("record_field", arguments)))

    assert "schema_violation" in verdict.failures
    assert verdict.bad_argument_calls == 1


def test_a_tool_not_offered() -> None:
    verdict = evaluate(S["greeting"], calls(("delete_case", {})))

    assert verdict.failures == ("unexpected_tool", "wrong_tool")
    assert verdict.bad_argument_calls == 0


def test_details_never_quote_argument_values() -> None:
    response = calls(("record_field", {"field": SECRET, "value": SECRET}))

    verdict = evaluate(S["understand_all_facts"], response)

    assert verdict.details
    assert not any(SECRET in d for d in verdict.details)


# --- Each scenario: a passing and a failing response ------------------------


def all_four() -> list[tuple[str, dict[str, Any]]]:
    return [record(f) for f in ("what", "where", "since", "standard")]


CASES: list[tuple[str, LLMResponse, tuple[str, ...]]] = [
    ("understand_all_facts", calls(*all_four()), ()),
    ("understand_all_facts", calls(*all_four(), transition("challenge")), ()),
    ("understand_all_facts", calls(record("what"), record("where")), ("wrong_arguments",)),
    ("understand_all_facts", text_response("¿Algo más?"), ("missing_tool",)),
    ("understand_vague", text_response("¿Qué defecto veis y en qué línea?"), ()),
    ("understand_vague", text_response("Entendido."), ("missing_text",)),
    ("understand_vague", calls(record("what"), text="¿Dónde?"), ("wrong_tool",)),
    ("understand_confirmed", calls(transition("challenge")), ()),
    ("understand_confirmed", text_response("Perfecto."), ("missing_tool",)),
    ("challenge_cause_without_data", text_response("¿Qué datos lo apoyan?"), ()),
    (
        "challenge_cause_without_data",
        calls(event("hypothesis"), text="Lo anoto. ¿Tenéis datos por turno?"),
        (),
    ),
    (
        "challenge_cause_without_data",
        calls(event("validated_cause"), text="¿Seguro?"),
        ("wrong_arguments",),
    ),
    (
        "challenge_cause_without_data",
        calls(transition("analyse")),
        ("wrong_tool", "missing_text"),
    ),
    ("challenge_contradicting_data", calls(event("hypothesis_discarded")), ()),
    ("challenge_contradicting_data", calls(event("evidence")), ()),
    ("challenge_contradicting_data", calls(event("hypothesis")), ("wrong_arguments",)),
    ("challenge_contradicting_data", text_response("Interesante."), ("missing_tool",)),
    ("analyse_validated_cause", calls(event("validated_cause")), ()),
    ("analyse_validated_cause", calls(event("evidence")), ("wrong_arguments",)),
    ("enum_skip_ahead", text_response("Antes hay que cuestionar las causas."), ()),
    ("enum_skip_ahead", calls(transition("challenge")), ()),
    ("enum_skip_ahead", calls(transition("action")), ("schema_violation",)),
    ("greeting", text_response("¡Hola! ¿En qué problema trabajamos?"), ()),
    ("greeting", calls(record("what")), ("wrong_tool",)),
    ("rejected_transition", text_response("¿Qué evidencia tenemos del operador?"), ()),
    ("rejected_transition", calls(transition("analyse")), ("wrong_tool", "missing_text")),
    (
        "rejected_transition",
        calls(transition("analyse"), text="¿Lo intento otra vez?"),
        ("wrong_tool",),
    ),
]


@pytest.mark.parametrize(
    ("scenario_id", "response", "failures"),
    CASES,
    ids=[f"{sid}-{i}" for i, (sid, _, _) in enumerate(CASES)],
)
def test_expectations(scenario_id: str, response: LLMResponse, failures: tuple[str, ...]) -> None:
    verdict = evaluate(S[scenario_id], response)

    assert verdict.failures == failures
    assert verdict.passed is (failures == ())


def test_several_failure_reasons_in_one_run() -> None:
    bad: ToolCall = invalid_tool_call("log_event", "{", call_id="c9")
    response = tool_calls_response(
        bad, tool_call("propose_transition", {"target_state": "analyse", "reasoning": "x"})
    )

    verdict = evaluate(S["challenge_cause_without_data"], response)

    assert verdict.failures == ("invalid_json", "wrong_tool", "missing_text")
    assert verdict.tool_calls == 2
    assert verdict.bad_argument_calls == 1
