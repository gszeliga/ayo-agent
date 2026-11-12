"""Judge one model response against a scenario.

Every call is checked (offered tool, valid JSON, valid against the tool's schema, enums
included), then the scenario's expectations. A run passes only with no failure at all;
otherwise every reason found is listed. Details name tools and schema locations only,
never argument values or text: they go into reports and logs.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from jsonschema import Draft202012Validator

from ayo_copilot.llm.check.scenarios import Scenario, ValueRule
from ayo_copilot.llm.types import LLMResponse, ToolCall

FailureReason = Literal[
    "invalid_json",  # the arguments are not a JSON object
    "schema_violation",  # they do not fit the tool's schema (enums included)
    "unexpected_tool",  # a tool that was not offered
    "wrong_tool",  # a forbidden tool, or any tool when none was expected
    "missing_tool",  # a required tool was not called
    "wrong_arguments",  # valid for the schema, but not what the scenario expects
    "missing_text",  # the text lacks the expected question
]
FAILURE_REASONS: tuple[FailureReason, ...] = (
    "invalid_json",
    "schema_violation",
    "unexpected_tool",
    "wrong_tool",
    "missing_tool",
    "wrong_arguments",
    "missing_text",
)


@dataclass(frozen=True)
class Verdict:
    failures: tuple[FailureReason, ...]  # unique, in FAILURE_REASONS order
    details: tuple[str, ...]  # one safe line per problem found
    tool_calls: int
    bad_argument_calls: int  # invalid JSON or schema violation, offered tools only

    @property
    def passed(self) -> bool:
        return not self.failures


def evaluate(scenario: Scenario, response: LLMResponse) -> Verdict:
    found: list[tuple[FailureReason, str]] = []
    offered = {tool.name: tool for tool in scenario.tools}
    valid_calls: list[ToolCall] = []
    bad_arguments = 0

    for call in response.tool_calls:
        if call.name not in offered:
            found.append(("unexpected_tool", "a call to a tool that was not offered"))
            continue
        if call.arguments is None:
            bad_arguments += 1
            found.append(("invalid_json", f"{call.name}: arguments are not a JSON object"))
            continue
        errors = _schema_errors(offered[call.name].parameters, call.arguments)
        if errors:
            bad_arguments += 1
            found.extend(("schema_violation", f"{call.name}: {e}") for e in errors)
            continue
        valid_calls.append(call)

    exp = scenario.expectations
    names = [call.name for call in response.tool_calls]
    if exp.must_call_none and names:
        found.append(("wrong_tool", "a tool was called where none was expected"))
    if exp.must_call_any and not exp.must_call_any.intersection(names):
        found.append(("missing_tool", f"none of {sorted(exp.must_call_any)} was called"))
    for name in sorted(exp.forbidden_tools.intersection(names)):
        found.append(("wrong_tool", f"{name} must not be called"))
    for rule in exp.forbidden_values:
        if any(_value_in(call, rule) for call in valid_calls):
            found.append(("wrong_arguments", f"{_rule(rule)} is not allowed here"))
    for rule in exp.required_values:
        calls = [c for c in valid_calls if c.name == rule.tool]
        if not any(c.name == rule.tool for c in response.tool_calls):
            found.append(("missing_tool", f"{rule.tool} was not called"))
        elif not any(_value_in(c, rule) for c in calls):
            found.append(("wrong_arguments", f"no {rule.tool} call with {_rule(rule)}"))
    if exp.must_cover is not None:
        rule = exp.must_cover
        if not any(c.name == rule.tool for c in response.tool_calls):
            found.append(("missing_tool", f"{rule.tool} was not called"))
        else:
            seen = {_field(c, rule.field) for c in valid_calls if c.name == rule.tool}
            missing = sorted(rule.values - seen)
            if missing:
                found.append(
                    ("wrong_arguments", f"{rule.tool}.{rule.field} never set to {missing}")
                )
    if exp.needs_question and "?" not in (response.text or ""):
        found.append(("missing_text", "the text asks no question"))

    reasons = {reason for reason, _ in found}
    return Verdict(
        failures=tuple(r for r in FAILURE_REASONS if r in reasons),
        details=tuple(detail for _, detail in found),
        tool_calls=len(response.tool_calls),
        bad_argument_calls=bad_arguments,
    )


def _schema_errors(schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> list[str]:
    """Where the arguments break the schema, as schema locations (ours, never their values)."""
    validator = Draft202012Validator(dict(schema))
    return sorted(
        "/".join(str(part) for part in error.schema_path) or "(root)"
        for error in validator.iter_errors(dict(arguments))
    )


def _field(call: ToolCall, name: str) -> str | None:
    """A string argument, or None (absent, or not a string: values may be unhashable)."""
    value = call.arguments.get(name) if call.arguments is not None else None
    return value if isinstance(value, str) else None


def _value_in(call: ToolCall, rule: ValueRule) -> bool:
    return call.name == rule.tool and _field(call, rule.field) in rule.values


def _rule(rule: ValueRule) -> str:
    return f"{rule.tool}.{rule.field} in {sorted(rule.values)}"
