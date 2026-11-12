from typing import Any

import pytest

from ayo_copilot.llm.provider import check_request
from ayo_copilot.llm.types import LLMResponse, Message, ToolCall, ToolSpec, Usage

SECRET = "Presión de sellado 4,2 bar en la línea 3 del cliente"

RECORD_FIELD = ToolSpec(
    name="record_field",
    description="Registra un dato del problema.",
    parameters={
        "type": "object",
        "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
        "required": ["field", "value"],
    },
)


def valid_call(**overrides: Any) -> ToolCall:
    values: dict[str, Any] = {
        "id": "call_1",
        "name": "record_field",
        "arguments": {"field": "what", "value": SECRET},
        "raw_arguments": '{"field": "what", "value": "..."}',
    }
    values.update(overrides)
    return ToolCall(**values)


# --- ToolSpec ---------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "has space", "a" * 65, "ñandú"])
def test_tool_names_follow_the_function_name_rule(name: str) -> None:
    with pytest.raises(ValueError, match="tool name"):
        ToolSpec(name=name, description="", parameters={"type": "object"})


@pytest.mark.parametrize("parameters", [{}, {"type": "string"}, []])
def test_tool_parameters_must_be_an_object_schema(parameters: Any) -> None:
    with pytest.raises(ValueError, match="parameters"):
        ToolSpec(name="t", description="", parameters=parameters)


# --- ToolCall ---------------------------------------------------------------


def test_a_valid_tool_call() -> None:
    call = valid_call()

    assert call.is_valid
    assert call.arguments_error is None


def test_an_invalid_tool_call_keeps_the_raw_arguments() -> None:
    call = valid_call(arguments=None, raw_arguments='{"field": ', arguments_error="bad JSON")

    assert not call.is_valid
    assert call.raw_arguments == '{"field": '


@pytest.mark.parametrize(
    "overrides",
    [
        {"arguments": None},  # neither arguments nor an error
        {"arguments_error": "bad JSON"},  # both
    ],
)
def test_a_tool_call_has_arguments_or_an_error(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="either arguments or an arguments_error"):
        valid_call(**overrides)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"id": ""}, ValueError),
        ({"name": ""}, ValueError),
        ({"raw_arguments": None}, TypeError),
        ({"arguments": ["not", "an", "object"]}, TypeError),
    ],
)
def test_tool_call_fields_are_checked(overrides: dict[str, Any], error: type[Exception]) -> None:
    with pytest.raises(error):
        valid_call(**overrides)


# --- Message ----------------------------------------------------------------


def test_the_three_roles() -> None:
    call = valid_call()

    user = Message(role="user", content="Hola")
    assistant = Message(role="assistant", tool_calls=[call])
    tool = Message(role="tool", content='{"ok": true}', tool_call_id="call_1")

    assert user.content == "Hola"
    assert assistant.tool_calls == (call,)  # a list is stored as a tuple
    assert tool.tool_call_id == "call_1"


def test_assistant_may_carry_text_and_tool_calls() -> None:
    message = Message(role="assistant", content="Lo registro.", tool_calls=(valid_call(),))

    assert message.content == "Lo registro."
    assert len(message.tool_calls) == 1


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"role": "system", "content": "x"}, "role must be"),
        ({"role": "user"}, "user message needs content"),
        ({"role": "assistant"}, "needs content, tool_calls or both"),
        ({"role": "tool", "content": "x"}, "needs the tool_call_id"),
        ({"role": "tool", "tool_call_id": "call_1"}, "needs content"),
        ({"role": "user", "content": "x", "tool_call_id": "call_1"}, "only tool messages"),
    ],
)
def test_message_rules(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Message(**kwargs)


def test_only_assistant_messages_carry_tool_calls() -> None:
    with pytest.raises(ValueError, match="only assistant"):
        Message(role="user", content="x", tool_calls=(valid_call(),))


def test_message_tool_calls_must_be_tool_calls() -> None:
    with pytest.raises(TypeError, match="ToolCall"):
        Message(role="assistant", tool_calls=[{"name": "record_field"}])  # type: ignore[list-item]


# --- Usage and LLMResponse --------------------------------------------------


def test_usage_defaults_to_unknown() -> None:
    usage = Usage()

    assert usage.prompt_tokens is None
    assert usage.cost is None


@pytest.mark.parametrize(
    "kwargs",
    [{"prompt_tokens": -1}, {"total_tokens": 1.5}, {"reasoning_tokens": True}, {"cost": -0.1}],
)
def test_usage_values_are_checked(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        Usage(**kwargs)


def test_a_response_keeps_tool_calls_in_order() -> None:
    first = valid_call(id="call_1")
    second = valid_call(id="call_2", name="log_event")

    response = LLMResponse(tool_calls=[first, second], finish_reason="tool_calls")

    assert response.tool_calls == (first, second)
    assert response.tool_names == ["record_field", "log_event"]
    assert response.text is None


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"text": 3}, TypeError),
        ({"reasoning": 3}, TypeError),
        ({"tool_calls": ["record_field"]}, TypeError),
        ({"usage": {"prompt_tokens": 1}}, TypeError),
        ({"latency_ms": 1.5}, TypeError),
        ({"latency_ms": -1}, ValueError),
        ({"generation_id": 7}, TypeError),
        ({"attempts": 0}, ValueError),
        ({"attempts": 1.0}, TypeError),
    ],
)
def test_response_fields_are_checked(kwargs: dict[str, Any], error: type[Exception]) -> None:
    with pytest.raises(error):
        LLMResponse(**kwargs)


# --- Privacy ----------------------------------------------------------------


def test_content_never_appears_in_reprs() -> None:
    call = valid_call(raw_arguments=f'{{"value": "{SECRET}"}}')
    objects = [
        call,
        Message(role="user", content=SECRET),
        Message(role="assistant", content=SECRET, tool_calls=(call,)),
        Message(role="tool", content=SECRET, tool_call_id="call_1"),
        LLMResponse(text=SECRET, reasoning=SECRET, tool_calls=(call,)),
    ]

    for obj in objects:
        assert SECRET not in repr(obj)
    # What is safe to show still is.
    assert "record_field" in repr(call)
    assert "call_1" in repr(call)


# --- check_request ----------------------------------------------------------


def request(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "system": "Eres un asistente.",
        "messages": [Message(role="user", content="Hola")],
        "tools": None,
        "tool_choice": "auto",
        "model": None,
        "temperature": None,
        "max_tokens": None,
    }
    values.update(overrides)
    return values


def test_a_well_formed_request_passes() -> None:
    check_request(**request())
    check_request(
        **request(
            tools=[RECORD_FIELD],
            tool_choice="record_field",
            model="qwen/qwen3-32b",
            temperature=0,
            max_tokens=10,
        )
    )
    check_request(**request(tools=[RECORD_FIELD], tool_choice="required"))


@pytest.mark.parametrize(
    ("overrides", "error", "match"),
    [
        ({"system": None}, TypeError, "system"),
        ({"messages": []}, ValueError, "must not be empty"),
        ({"messages": "Hola"}, TypeError, "list of Message"),
        ({"messages": [{"role": "user", "content": "Hola"}]}, TypeError, "Message objects"),
        ({"tools": [{"name": "x"}]}, TypeError, "ToolSpec objects"),
        ({"tools": [RECORD_FIELD, RECORD_FIELD]}, ValueError, "unique"),
        ({"tool_choice": ""}, ValueError, "tool_choice must be"),
        ({"tool_choice": "record_field"}, ValueError, "not offered"),
        ({"tool_choice": "required"}, ValueError, "at least one tool"),
        ({"model": ""}, ValueError, "model"),
        ({"temperature": 2.5}, ValueError, "temperature"),
        ({"temperature": True}, ValueError, "temperature"),
        ({"max_tokens": 0}, ValueError, "max_tokens"),
    ],
)
def test_malformed_requests_are_rejected(
    overrides: dict[str, Any], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        check_request(**request(**overrides))
