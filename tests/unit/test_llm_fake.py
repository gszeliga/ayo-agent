import json

import pytest

from ayo_copilot.llm import LLMProvider, LLMResponse, Message, ToolSpec
from ayo_copilot.llm.fake import (
    FakeLLMExhaustedError,
    FakeLLMProvider,
    invalid_tool_call,
    text_response,
    tool_call,
    tool_calls_response,
)

USER = Message(role="user", content="La selladora 3 falla desde el lunes.")
RECORD_FIELD = ToolSpec(
    name="record_field",
    description="Registra un dato del problema.",
    parameters={"type": "object", "properties": {}},
)


def test_the_fake_is_an_llm_provider() -> None:
    assert isinstance(FakeLLMProvider(), LLMProvider)


def test_returns_scripted_responses_in_order() -> None:
    first = text_response("¿Desde cuándo ocurre?")
    second = tool_calls_response(tool_call("record_field", {"field": "since", "value": "lunes"}))
    fake = FakeLLMProvider([first])
    fake.add(second)

    assert fake.remaining == 2
    assert fake.complete(system="s", messages=[USER]) is first
    assert fake.complete(system="s", messages=[USER], tools=[RECORD_FIELD]) is second
    assert fake.remaining == 0


def test_records_every_call() -> None:
    fake = FakeLLMProvider([text_response("ok")])

    fake.complete(
        system="Fase Entender.",
        messages=[USER],
        tools=[RECORD_FIELD],
        tool_choice="record_field",
        model="qwen/qwen3-32b",
        temperature=0.0,
        max_tokens=50,
    )

    (call,) = fake.calls
    assert call.system == "Fase Entender."
    assert call.messages == (USER,)
    assert call.tools == (RECORD_FIELD,)
    assert call.tool_names == ["record_field"]
    assert call.tool_choice == "record_field"
    assert call.model == "qwen/qwen3-32b"
    assert call.temperature == 0.0
    assert call.max_tokens == 50


def test_fails_loudly_when_exhausted_and_still_records_the_call() -> None:
    fake = FakeLLMProvider([text_response("ok")])
    fake.complete(system="s", messages=[USER])

    with pytest.raises(FakeLLMExhaustedError, match="call 2"):
        fake.complete(system="s", messages=[USER])
    assert len(fake.calls) == 2


@pytest.mark.parametrize("bad", ["just text", {"text": "x"}, None])
def test_only_llm_responses_can_be_scripted(bad: object) -> None:
    with pytest.raises(TypeError, match="LLMResponse"):
        FakeLLMProvider([bad])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="LLMResponse"):
        FakeLLMProvider().add(bad)  # type: ignore[arg-type]


def test_malformed_requests_fail_before_using_a_response() -> None:
    fake = FakeLLMProvider([text_response("ok")])

    with pytest.raises(ValueError, match="not offered"):
        fake.complete(system="s", messages=[USER], tool_choice="record_field")
    assert fake.calls == []
    assert fake.remaining == 1


def test_scripted_calls_to_tools_not_offered_are_allowed() -> None:
    """The check command's tests need the fake to imitate a model that invents a tool."""
    response = tool_calls_response(tool_call("delete_case", {}))
    fake = FakeLLMProvider([response])

    assert fake.complete(system="s", messages=[USER], tools=[RECORD_FIELD]) is response


def test_helpers_build_valid_and_invalid_calls() -> None:
    valid = tool_call("record_field", {"field": "where", "value": "Línea 3"}, call_id="c1")
    invalid = invalid_tool_call("record_field", '{"field": "where",')

    assert valid.id == "c1"
    assert json.loads(valid.raw_arguments) == {"field": "where", "value": "Línea 3"}
    assert invalid.arguments is None
    assert invalid.arguments_error == "invalid JSON"
    response = tool_calls_response(valid, invalid, text="Anotado.")
    assert isinstance(response, LLMResponse)
    assert response.finish_reason == "tool_calls"
    assert response.tool_names == ["record_field", "record_field"]
    assert text_response("hola").finish_reason == "stop"


def test_tool_calls_response_needs_a_call() -> None:
    with pytest.raises(ValueError, match="at least one"):
        tool_calls_response()
