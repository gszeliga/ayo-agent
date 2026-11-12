"""The phase machine: transitions table, exit criteria and their missing items."""

from datetime import date
from uuid import uuid4

import pytest

from ayo_copilot.conversation.case import (
    PHASES,
    Action,
    Case,
    CaseSnapshot,
    Event,
    Phase,
)
from ayo_copilot.conversation.phases import (
    TRANSITIONS,
    describe_missing,
    is_allowed,
    missing_for,
    targets,
)

ALLOWED = {
    ("understand", "challenge"),
    ("challenge", "analyse"),
    ("analyse", "action"),
    ("action", "followup"),
    ("followup", "action"),
    ("followup", "closed"),
}


def snapshot(state: Phase, **fields: str) -> CaseSnapshot:
    return CaseSnapshot(case=Case(id=uuid4(), tenant="cliente-acme", state=state, **fields))


def annotation(event_type: str, state: Phase = "challenge") -> Event:
    return Event(
        role="assistant",
        event_type=event_type,  # type: ignore[arg-type]
        content="La merma se concentra en el turno de noche.",
        state_at_time=state,
    )


def action(status: str = "pending", owner: str = "Marta (calidad)") -> Action:
    return Action(
        description="Revisar la calibración de la llenadora 3",
        owner=owner,
        due_date=date(2026, 11, 20),
        status=status,  # type: ignore[arg-type]
        id=1,
    )


FOUR_FIELDS = {
    "what": "Merma del 4 % en la línea de envasado",
    "where_": "Línea 2, llenadora 3",
    "since": "Desde el lunes",
    "standard": "Merma máxima del 1,5 %",
}


@pytest.mark.parametrize("source", PHASES)
@pytest.mark.parametrize("target", PHASES)
def test_every_transition_is_allowed_or_not_as_in_the_table(source: Phase, target: Phase) -> None:
    assert is_allowed(source, target) == ((source, target) in ALLOWED)


def test_closed_allows_nothing_and_every_phase_is_in_the_table() -> None:
    assert set(TRANSITIONS) == set(PHASES)
    assert targets("closed") == ()


def test_targets_keep_table_order() -> None:
    assert targets("followup") == ("action", "closed")


def test_every_target_has_a_condition_for_the_model() -> None:
    for reachable in TRANSITIONS.values():
        for target in reachable:
            assert target.condition.strip()


def test_missing_for_refuses_a_transition_that_is_not_allowed() -> None:
    with pytest.raises(ValueError, match="understand -> analyse"):
        missing_for(snapshot("understand"), "analyse")


def test_understand_lists_missing_facts_by_model_name_in_order() -> None:
    assert missing_for(snapshot("understand"), "challenge") == [
        "what",
        "where",
        "since",
        "standard",
    ]
    partial = snapshot("understand", what="Merma alta", since="Desde el lunes", where_="  ")
    assert missing_for(partial, "challenge") == ["where", "standard"]
    assert missing_for(snapshot("understand", **FOUR_FIELDS), "challenge") == []


def test_challenge_needs_evidence_not_just_a_hypothesis() -> None:
    case = snapshot("challenge")
    assert missing_for(case, "analyse") == ["evidence"]
    case.events.append(annotation("hypothesis"))
    assert missing_for(case, "analyse") == ["evidence"]
    case.events.append(annotation("evidence"))
    assert missing_for(case, "analyse") == []


def test_analyse_needs_a_validated_cause() -> None:
    case = snapshot("analyse")
    case.events.append(annotation("evidence"))
    assert missing_for(case, "action") == ["validated_cause"]
    case.events.append(annotation("validated_cause", "analyse"))
    assert missing_for(case, "action") == []


def test_action_needs_complete_actions() -> None:
    case = snapshot("action")
    assert missing_for(case, "followup") == ["action"]
    case.actions.append(action(owner="  "))
    assert missing_for(case, "followup") == ["incomplete_actions"]
    case.actions[0].owner = "Marta (calidad)"
    assert missing_for(case, "followup") == []


def test_followup_can_always_reopen_action() -> None:
    assert missing_for(snapshot("followup"), "action") == []


def test_followup_closes_only_with_actions_and_none_pending() -> None:
    case = snapshot("followup")
    assert missing_for(case, "closed") == ["action"]
    case.actions += [action("done"), action("pending")]
    assert missing_for(case, "closed") == ["pending_actions"]
    case.actions[1].status = "done"
    assert missing_for(case, "closed") == []


def test_describe_missing() -> None:
    assert describe_missing(["where", "standard"]) == "missing facts: where, standard"
    assert describe_missing(["evidence"]) == "no evidence recorded yet"
    assert describe_missing(["validated_cause"]) == "no validated cause recorded yet"
    assert describe_missing(["action"]) == "no action recorded yet"
    assert describe_missing(["incomplete_actions"]) == "some actions have no owner or due date"
    assert describe_missing(["pending_actions"]) == "some actions are still pending"


def test_overdue_is_pending_and_past_due() -> None:
    today = date(2026, 11, 21)
    assert action("pending").is_overdue(today)
    assert not action("done").is_overdue(today)
    assert not action("pending").is_overdue(date(2026, 11, 20))


def test_reprs_hide_content() -> None:
    case = snapshot("understand", **FOUR_FIELDS)
    case.events.append(annotation("evidence"))
    case.actions.append(action())
    text = repr(case)
    for secret in [*FOUR_FIELDS.values(), "turno de noche", "llenadora 3", "Marta"]:
        assert secret not in text
