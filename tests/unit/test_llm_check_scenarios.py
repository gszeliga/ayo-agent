import pytest
from jsonschema import Draft202012Validator

from ayo_copilot.llm.check.scenarios import PHASES, Scenario, build_scenarios
from ayo_copilot.llm.provider import check_request

SCENARIOS = build_scenarios()
BY_ID = {s.id: s for s in SCENARIOS}


def test_nine_scenarios_with_unique_ids() -> None:
    assert len(SCENARIOS) == 9
    assert len(BY_ID) == 9


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_scenario_is_well_formed(scenario: Scenario) -> None:
    assert scenario.phase in PHASES
    assert scenario.title
    for tool in scenario.tools:
        Draft202012Validator.check_schema(dict(tool.parameters))
    # Expectations only name tools the scenario offers.
    assert scenario.expectations.tools_named() <= set(scenario.tool_names)
    # A provider would accept the request as built.
    check_request(
        system=scenario.system,
        messages=list(scenario.messages),
        tools=list(scenario.tools),
        tool_choice="auto",
        model=None,
        temperature=None,
        max_tokens=None,
    )


def transition_targets(scenario: Scenario) -> list[str]:
    (tool,) = [t for t in scenario.tools if t.name == "propose_transition"]
    return tool.parameters["properties"]["target_state"]["enum"]


def test_transition_targets_change_per_scenario() -> None:
    assert transition_targets(BY_ID["understand_confirmed"]) == ["challenge"]
    assert transition_targets(BY_ID["enum_skip_ahead"]) == ["challenge"]
    assert transition_targets(BY_ID["rejected_transition"]) == ["analyse"]
    assert transition_targets(BY_ID["analyse_validated_cause"]) == ["action"]


def test_rejected_transition_history_ends_with_the_tool_result() -> None:
    messages = BY_ID["rejected_transition"].messages

    assistant, tool = messages[-2], messages[-1]
    assert assistant.role == "assistant"
    assert [c.name for c in assistant.tool_calls] == ["propose_transition"]
    assert tool.role == "tool"
    assert tool.tool_call_id == assistant.tool_calls[0].id
    assert "rejected" in (tool.content or "")


def test_scenarios_are_marked_as_drafts() -> None:
    from ayo_copilot.llm.check import scenarios

    doc = " ".join((scenarios.__doc__ or "").split())
    assert "DRAFT" in doc
    assert "NOT the production prompts" in doc
