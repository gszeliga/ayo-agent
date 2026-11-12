"""The tools: specs, exposure per phase, validation and handlers on a snapshot."""

import json
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from ayo_copilot.conversation.case import (
    PHASES,
    Action,
    Case,
    CaseSnapshot,
    Event,
    Phase,
    Transition,
    TurnChanges,
)
from ayo_copilot.conversation.tools import (
    TOOL_NAMES,
    ToolOutcome,
    clean_text,
    execute_tool,
    log_event_tool,
    propose_transition_tool,
    tools_for_phase,
)
from ayo_copilot.llm.fake import invalid_tool_call, tool_call

EXPOSURE: dict[Phase, list[str]] = {
    "understand": ["record_field", "propose_transition"],
    "challenge": ["record_field", "log_event", "propose_transition"],
    "analyse": ["log_event", "propose_transition"],
    "action": ["add_action", "update_action", "propose_transition"],
    "followup": ["add_action", "update_action", "propose_transition"],
    "closed": [],
}

FACTS = {
    "what": "Merma del 4 % en la línea de envasado",
    "where": "Línea 2, llenadora 3",
    "since": "Desde el lunes",
    "standard": "Merma máxima del 1,5 %",
}


def new_snapshot(state: Phase, actions: list[Action] | None = None) -> CaseSnapshot:
    return CaseSnapshot(
        case=Case(id=uuid4(), tenant="cliente-acme", state=state), actions=actions or []
    )


def stored_action(action_id: int = 7, status: str = "pending") -> Action:
    return Action(
        description="Revisar la calibración de la llenadora 3",
        owner="Marta (calidad)",
        due_date=date(2026, 11, 20),
        status=status,  # type: ignore[arg-type]
        id=action_id,
    )


def run(
    snapshot: CaseSnapshot,
    changes: TurnChanges,
    name: str,
    arguments: dict[str, Any],
    **kwargs: Any,
) -> ToolOutcome:
    return execute_tool(snapshot, changes, tool_call(name, arguments), **kwargs)


def assert_error(outcome: ToolOutcome, code: str) -> None:
    assert outcome.ok is False
    assert outcome.error_code == code
    assert outcome.result["ok"] is False
    assert outcome.result["error"] == code
    assert isinstance(outcome.result["detail"], str) and outcome.result["detail"]


# --- Specs and exposure -------------------------------------------------------


@pytest.mark.parametrize("phase", PHASES)
def test_exposure_per_phase(phase: Phase) -> None:
    assert [spec.name for spec in tools_for_phase(phase)] == EXPOSURE[phase]


@pytest.mark.parametrize("phase", PHASES)
def test_every_spec_is_a_valid_strict_schema(phase: Phase) -> None:
    for spec in tools_for_phase(phase):
        Draft202012Validator.check_schema(dict(spec.parameters))
        assert spec.parameters["additionalProperties"] is False
        assert spec.parameters["required"] == list(spec.parameters["properties"])
        assert spec.description.strip()


def test_log_event_enum_is_restricted_per_phase() -> None:
    def enum(phase: Phase) -> list[str]:
        return log_event_tool(phase).parameters["properties"]["event_type"]["enum"]

    assert enum("challenge") == ["evidence", "hypothesis", "hypothesis_discarded"]
    assert enum("analyse") == ["evidence", "hypothesis", "hypothesis_discarded", "validated_cause"]
    assert "validated_cause" not in log_event_tool("challenge").description
    with pytest.raises(ValueError):
        log_event_tool("understand")


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        ("understand", ["challenge"]),
        ("challenge", ["analyse"]),
        ("analyse", ["action"]),
        ("action", ["followup"]),
        ("followup", ["action", "closed"]),
    ],
)
def test_propose_transition_enum_and_description_come_from_the_table(
    phase: Phase, expected: list[str]
) -> None:
    spec = propose_transition_tool(phase)
    assert spec.parameters["properties"]["target_state"]["enum"] == expected
    for other in PHASES:
        line = f"- {other}:"
        assert (line in spec.description) == (other in expected)


def test_propose_transition_is_not_built_for_closed() -> None:
    with pytest.raises(ValueError):
        propose_transition_tool("closed")


def test_text_limits_in_the_schemas() -> None:
    props = {spec.name: spec.parameters["properties"] for spec in tools_for_phase("challenge")}
    assert props["record_field"]["value"]["maxLength"] == 500
    assert props["log_event"]["content"]["maxLength"] == 1000
    assert props["propose_transition"]["reasoning"]["maxLength"] == 500
    actions = {spec.name: spec.parameters["properties"] for spec in tools_for_phase("action")}
    assert actions["add_action"]["description"]["maxLength"] == 500
    assert actions["add_action"]["owner"]["maxLength"] == 100


def test_tool_names_cover_every_handler() -> None:
    offered = {spec.name for phase in PHASES for spec in tools_for_phase(phase)}
    assert offered == set(TOOL_NAMES)


# --- Rejections before any handler ----------------------------------------------


def test_unknown_tool_is_not_executed() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    outcome = run(snapshot, changes, "delete_case", {})
    assert_error(outcome, "unknown_tool")
    assert changes.is_empty


def test_tool_not_offered_in_the_phase_is_not_executed() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    outcome = run(snapshot, changes, "log_event", {"event_type": "evidence", "content": "x"})
    assert_error(outcome, "tool_not_offered")
    assert "understand" in outcome.result["detail"]
    assert snapshot.events == [] and changes.is_empty


def test_closed_case_gets_no_tool_at_all() -> None:
    snapshot, changes = new_snapshot("closed"), TurnChanges()
    outcome = run(snapshot, changes, "propose_transition", {"target_state": "action"})
    assert_error(outcome, "tool_not_offered")


def test_unparsable_arguments_return_the_parse_error() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    call = invalid_tool_call("record_field", '{"field": "what", "value": ', error="bad JSON at 27")
    outcome = execute_tool(snapshot, changes, call)
    assert_error(outcome, "invalid_json")
    assert "bad JSON at 27" in outcome.result["detail"]
    assert changes.is_empty


@pytest.mark.parametrize(
    ("arguments", "where"),
    [
        ({"field": "who", "value": "Marta"}, "field"),
        ({"field": "what"}, "(arguments)"),
        ({"field": "what", "value": ""}, "value"),
        ({"field": "what", "value": "x" * 501}, "value"),
        ({"field": "what", "value": 5}, "value"),
        ({"field": "what", "value": "Merma", "extra": 1}, "(arguments)"),
        ({"field": "where_", "value": "Línea 2"}, "field"),
    ],
)
def test_schema_violations_are_rejected(arguments: dict[str, Any], where: str) -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    outcome = run(snapshot, changes, "record_field", arguments)
    assert_error(outcome, "invalid_arguments")
    assert outcome.result["detail"].startswith(f"{where}:")
    assert snapshot.case.missing_fields() == ["what", "where", "since", "standard"]
    assert changes.is_empty


def test_schema_detail_is_capped_per_error() -> None:
    outcome = run(
        new_snapshot("understand"),
        TurnChanges(),
        "record_field",
        {
            "field": "what",
            "value": "x" * 501,
        },
    )
    assert len(outcome.result["detail"]) <= 200 + len("value: ")


def test_log_event_type_of_another_phase_is_rejected() -> None:
    snapshot, changes = new_snapshot("challenge"), TurnChanges()
    outcome = run(
        snapshot,
        changes,
        "log_event",
        {"event_type": "validated_cause", "content": "La boquilla está desgastada"},
    )
    assert_error(outcome, "invalid_arguments")
    assert snapshot.events == []


def test_clean_text_strips_control_characters_but_keeps_newlines_and_tabs() -> None:
    assert clean_text("  Línea\x00 2\x1b[31m\r\n\tllenadora\x07  ") == "Línea 2[31m\n\tllenadora"


def test_text_that_is_empty_after_cleaning_is_rejected() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    outcome = run(snapshot, changes, "record_field", {"field": "what", "value": " \x00\x01 \n"})
    assert_error(outcome, "invalid_arguments")
    assert outcome.result["detail"] == "value: is empty"
    assert changes.is_empty


# --- Handlers -------------------------------------------------------------------


def test_record_field_stores_cleaned_value_under_the_column_name() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    outcome = run(snapshot, changes, "record_field", {"field": "where", "value": " Línea 2\x00 "})
    assert outcome.ok and outcome.error_code is None
    assert outcome.result == {"ok": True, "field": "where", "overwrote": False}
    assert snapshot.case.where_ == "Línea 2"
    assert changes.fields == {"where": "Línea 2"}


def test_record_field_overwrites_to_correct_a_fact() -> None:
    snapshot, changes = new_snapshot("challenge"), TurnChanges()
    snapshot.case.since = "Desde el lunes"
    outcome = run(snapshot, changes, "record_field", {"field": "since", "value": "Desde el martes"})
    assert outcome.result == {"ok": True, "field": "since", "overwrote": True}
    assert snapshot.case.since == "Desde el martes"
    assert changes.fields == {"since": "Desde el martes"}


def test_log_event_appends_an_assistant_annotation_in_the_current_phase() -> None:
    snapshot, changes = new_snapshot("analyse"), TurnChanges()
    outcome = run(
        snapshot,
        changes,
        "log_event",
        {"event_type": "validated_cause", "content": "La boquilla 3 está desgastada"},
    )
    assert outcome.result == {"ok": True, "event_type": "validated_cause"}
    event = snapshot.events[-1]
    assert (event.role, event.event_type, event.state_at_time) == (
        "assistant",
        "validated_cause",
        "analyse",
    )
    assert event.content == "La boquilla 3 está desgastada"
    assert event.id is None
    assert changes.new_events == [event]


def test_add_action_appends_a_pending_action_without_an_id() -> None:
    snapshot, changes = new_snapshot("action"), TurnChanges()
    outcome = run(
        snapshot,
        changes,
        "add_action",
        {
            "description": "Sustituir la boquilla 3",
            "owner": "Jordi (mantenimiento)",
            "due_date": "2026-11-20",
        },
    )
    assert outcome.result == {"ok": True, "due_date": "2026-11-20", "status": "pending"}
    action = snapshot.actions[-1]
    assert (action.id, action.status, action.due_date) == (None, "pending", date(2026, 11, 20))
    assert changes.new_actions == [action]


def test_add_action_accepts_a_past_date() -> None:
    outcome = run(
        new_snapshot("followup"),
        TurnChanges(),
        "add_action",
        {"description": "Revisar el registro", "owner": "Marta", "due_date": "2020-01-31"},
    )
    assert outcome.ok


@pytest.mark.parametrize(
    ("due_date", "code"),
    [
        ("2026-02-30", "invalid_date"),
        ("2026-13-01", "invalid_date"),
        ("20-11-2026", "invalid_arguments"),
        ("el viernes", "invalid_arguments"),
    ],
)
def test_add_action_rejects_a_date_that_is_not_real(due_date: str, code: str) -> None:
    snapshot, changes = new_snapshot("action"), TurnChanges()
    outcome = run(
        snapshot,
        changes,
        "add_action",
        {"description": "Sustituir la boquilla 3", "owner": "Jordi", "due_date": due_date},
    )
    assert_error(outcome, code)
    assert snapshot.actions == [] and changes.is_empty


def test_update_action_changes_a_stored_action() -> None:
    snapshot, changes = new_snapshot("followup", [stored_action(7)]), TurnChanges()
    outcome = run(snapshot, changes, "update_action", {"action_id": 7, "status": "done"})
    assert outcome.result == {"ok": True, "action_id": 7, "status": "done", "changed": True}
    assert snapshot.actions[0].status == "done"
    assert changes.action_updates == {7: "done"}


def test_update_action_with_the_same_status_is_ok_and_unchanged() -> None:
    snapshot, changes = new_snapshot("followup", [stored_action(7, "done")]), TurnChanges()
    outcome = run(snapshot, changes, "update_action", {"action_id": 7, "status": "done"})
    assert outcome.result == {"ok": True, "action_id": 7, "status": "done", "changed": False}
    assert changes.is_empty


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"action_id": 8, "status": "done"}, "action_not_found"),
        ({"action_id": 0, "status": "done"}, "invalid_arguments"),
        ({"action_id": "7", "status": "done"}, "invalid_arguments"),
        ({"action_id": True, "status": "done"}, "invalid_arguments"),
        ({"action_id": 7, "status": "cancelled"}, "invalid_arguments"),
    ],
)
def test_update_action_rejections(arguments: dict[str, Any], code: str) -> None:
    snapshot, changes = new_snapshot("action", [stored_action(7)]), TurnChanges()
    outcome = run(snapshot, changes, "update_action", arguments)
    assert_error(outcome, code)
    assert snapshot.actions[0].status == "pending" and changes.is_empty


def test_update_action_cannot_reach_an_action_added_this_turn() -> None:
    snapshot, changes = new_snapshot("action"), TurnChanges()
    run(
        snapshot,
        changes,
        "add_action",
        {"description": "Sustituir la boquilla 3", "owner": "Jordi", "due_date": "2026-11-20"},
    )
    outcome = run(snapshot, changes, "update_action", {"action_id": 1, "status": "done"})
    assert_error(outcome, "action_not_found")


def test_update_action_accepts_an_integral_float_id() -> None:
    snapshot = new_snapshot("action", [stored_action(7)])
    outcome = run(snapshot, TurnChanges(), "update_action", {"action_id": 7.0, "status": "done"})
    assert outcome.result["action_id"] == 7


# --- propose_transition ---------------------------------------------------------


def test_rejected_transition_names_what_is_missing() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    run(snapshot, changes, "record_field", {"field": "what", "value": FACTS["what"]})
    run(snapshot, changes, "record_field", {"field": "since", "value": FACTS["since"]})
    outcome = run(
        snapshot,
        changes,
        "propose_transition",
        {"target_state": "challenge", "reasoning": "Tenemos el problema definido"},
    )
    assert outcome.result == {
        "ok": False,
        "error": "criteria_not_met",
        "detail": "missing facts: where, standard",
        "missing": ["where", "standard"],
    }
    assert snapshot.case.state == "understand"
    assert changes.transitions == []


def test_criteria_see_changes_made_earlier_in_the_same_turn() -> None:
    snapshot, changes = new_snapshot("understand"), TurnChanges()
    for name, value in FACTS.items():
        assert run(snapshot, changes, "record_field", {"field": name, "value": value}).ok
    outcome = run(
        snapshot,
        changes,
        "propose_transition",
        {"target_state": "challenge", "reasoning": "Los cuatro datos están registrados"},
    )
    assert outcome.result == {"ok": True, "previous_phase": "understand", "phase": "challenge"}
    assert snapshot.case.state == "challenge"
    assert changes.transitions == [Transition("understand", "challenge")]
    assert [spec.name for spec in tools_for_phase(snapshot.case.state)] == EXPOSURE["challenge"]


def test_challenge_rejection_says_no_evidence_then_accepts_after_log_event() -> None:
    snapshot, changes = new_snapshot("challenge"), TurnChanges()
    proposal = {"target_state": "analyse", "reasoning": "Hay datos suficientes"}
    outcome = run(snapshot, changes, "propose_transition", proposal)
    assert outcome.result["detail"] == "no evidence recorded yet"
    assert outcome.result["missing"] == ["evidence"]
    run(
        snapshot,
        changes,
        "log_event",
        {"event_type": "evidence", "content": "La merma sube solo en el turno de noche"},
    )
    assert run(snapshot, changes, "propose_transition", proposal).ok


def test_followup_closes_after_the_last_action_is_done_in_the_same_turn() -> None:
    snapshot = new_snapshot("followup", [stored_action(7), stored_action(8, "done")])
    changes = TurnChanges()
    proposal = {"target_state": "closed", "reasoning": "Todas las acciones hechas"}
    assert run(snapshot, changes, "propose_transition", proposal).result["missing"] == [
        "pending_actions"
    ]
    run(snapshot, changes, "update_action", {"action_id": 7, "status": "done"})
    outcome = run(snapshot, changes, "propose_transition", proposal)
    assert outcome.result == {"ok": True, "previous_phase": "followup", "phase": "closed"}
    assert changes.transitions == [Transition("followup", "closed")]


def test_followup_reopens_action() -> None:
    snapshot = new_snapshot("followup")
    outcome = run(
        snapshot,
        TurnChanges(),
        "propose_transition",
        {"target_state": "action", "reasoning": "Hace falta otra acción"},
    )
    assert outcome.ok and snapshot.case.state == "action"


def test_target_outside_the_generated_enum_is_a_schema_error() -> None:
    snapshot = new_snapshot("understand")
    outcome = run(
        snapshot,
        TurnChanges(),
        "propose_transition",
        {"target_state": "analyse", "reasoning": "Saltamos"},
    )
    assert_error(outcome, "invalid_arguments")
    assert snapshot.case.state == "understand"


def test_hop_cap_refuses_without_checking_criteria() -> None:
    snapshot, changes = new_snapshot("followup"), TurnChanges()
    outcome = run(
        snapshot,
        changes,
        "propose_transition",
        {"target_state": "action", "reasoning": "Reabrir"},
        allow_transition=False,
    )
    assert_error(outcome, "phase_hop_limit")
    assert "next message" in outcome.result["detail"]
    assert snapshot.case.state == "followup" and changes.is_empty


# --- Results ------------------------------------------------------------------------


def test_outcome_content_is_the_json_result_and_repr_hides_it() -> None:
    snapshot = new_snapshot("challenge")
    snapshot.events.append(
        Event(role="user", event_type="message", content="hola", state_at_time="understand")
    )
    outcome = run(
        snapshot,
        TurnChanges(),
        "log_event",
        {"event_type": "evidence", "content": "La merma sube en el turno de noche"},
    )
    assert json.loads(outcome.content()) == {"ok": True, "event_type": "evidence"}
    error = run(
        snapshot, TurnChanges(), "record_field", {"field": "what", "value": ["Marta López"]}
    )
    assert "Marta López" in error.content()
    assert "Marta López" not in repr(error)
    assert "turno de noche" not in repr(snapshot) + repr(TurnChanges(new_events=snapshot.events))
