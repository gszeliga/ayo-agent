import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from ayo_copilot.llm import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMInsufficientCreditsError,
    LLMProvider,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
    Message,
    ToolSpec,
)
from ayo_copilot.llm.fake import invalid_tool_call, tool_call
from ayo_copilot.llm.openrouter import OpenRouterProvider

API_KEY = "sk-or-v1-secret-test-key"
BASE_URL = "https://openrouter.test/api/v1"
SECRET = "Contenido confidencial: presión de sellado 4,2 bar en la línea 3"
USER = Message(role="user", content=SECRET)

RECORD_FIELD = ToolSpec(
    name="record_field",
    description="Registra uno de los cuatro datos del problema.",
    parameters={
        "type": "object",
        "properties": {
            "field": {"type": "string", "enum": ["what", "where", "since", "standard"]},
            "value": {"type": "string"},
        },
        "required": ["field", "value"],
    },
)
GREET = ToolSpec(name="greet", description="Sin parámetros.", parameters={"type": "object"})

Handler = Callable[[httpx2.Request], httpx2.Response]


class Recorder:
    """A MockTransport handler that answers with a fixed response and keeps the requests."""

    def __init__(self, response: httpx2.Response | None = None) -> None:
        self.response = response or completion(message={"role": "assistant", "content": "ok"})
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.response

    @property
    def body(self) -> dict[str, Any]:
        (request,) = self.requests
        return json.loads(request.content)


def completion(
    *,
    message: dict[str, Any] | None = None,
    finish_reason: str | None = "stop",
    usage: dict[str, Any] | None = None,
    status: int = 200,
    **top: Any,
) -> httpx2.Response:
    body: dict[str, Any] = {
        "id": "gen-123",
        "object": "chat.completion",
        "model": "mistralai/mistral-small-3.2-24b-instruct",
        "provider": "Mistral",
        "choices": [
            {
                "index": 0,
                "message": message or {"role": "assistant", "content": "ok"},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    body.update(top)
    return httpx2.Response(status, json=body)


def make_provider(handler: Handler, **overrides: Any) -> OpenRouterProvider:
    values: dict[str, Any] = {
        "api_key": API_KEY,
        "model": "mistralai/mistral-small-3.2-24b-instruct",
        "temperature": 0.2,
        "max_tokens": 1024,
        "base_url": BASE_URL,
        "client": httpx2.Client(base_url=BASE_URL, transport=httpx2.MockTransport(handler)),
    }
    values.update(overrides)
    return OpenRouterProvider(**values)


def call(provider: OpenRouterProvider, **kwargs: Any) -> Any:
    kwargs.setdefault("system", "Eres el copiloto AYO.")
    kwargs.setdefault("messages", [USER])
    return provider.complete(**kwargs)


def respond_with(message: dict[str, Any], **kwargs: Any) -> Any:
    recorder = Recorder(completion(message=message, **kwargs))
    return call(make_provider(recorder))


def test_is_an_llm_provider() -> None:
    assert isinstance(make_provider(Recorder()), LLMProvider)


# --- Request building -------------------------------------------------------


def test_posts_to_chat_completions_with_the_key_only_in_authorization() -> None:
    recorder = Recorder()
    call(make_provider(recorder))

    (request,) = recorder.requests
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    others = [v for k, v in request.headers.items() if k != "authorization"]
    assert not any(API_KEY in v for v in others)
    assert API_KEY not in request.content.decode()
    assert "http-referer" not in request.headers
    assert "x-openrouter-title" not in request.headers


def test_attribution_headers_when_set() -> None:
    recorder = Recorder()
    call(make_provider(recorder, app_url="https://ayo.example", app_title="AYO Copilot"))

    (request,) = recorder.requests
    assert request.headers["http-referer"] == "https://ayo.example"
    assert request.headers["x-openrouter-title"] == "AYO Copilot"


def test_body_without_tools() -> None:
    recorder = Recorder()
    call(make_provider(recorder))

    assert recorder.body == {
        "model": "mistralai/mistral-small-3.2-24b-instruct",
        "messages": [
            {"role": "system", "content": "Eres el copiloto AYO."},
            {"role": "user", "content": SECRET},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "provider": {"require_parameters": True, "data_collection": "deny"},
    }


def test_an_empty_system_prompt_is_not_sent() -> None:
    recorder = Recorder()
    call(make_provider(recorder), system="")

    assert recorder.body["messages"] == [{"role": "user", "content": SECRET}]


def test_tools_are_offered_in_the_openai_format() -> None:
    recorder = Recorder()
    call(make_provider(recorder), tools=[RECORD_FIELD, GREET])

    body = recorder.body
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "record_field",
                "description": RECORD_FIELD.description,
                "parameters": RECORD_FIELD.parameters,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "greet",
                "description": "Sin parámetros.",
                "parameters": {"type": "object"},
            },
        },
    ]
    assert body["tool_choice"] == "auto"
    assert body["provider"]["require_parameters"] is True
    assert "parallel_tool_calls" not in body


@pytest.mark.parametrize(
    ("tool_choice", "expected"),
    [
        ("auto", "auto"),
        ("none", "none"),
        ("required", "required"),
        ("record_field", {"type": "function", "function": {"name": "record_field"}}),
    ],
)
def test_tool_choice(tool_choice: str, expected: object) -> None:
    recorder = Recorder()
    call(make_provider(recorder), tools=[RECORD_FIELD], tool_choice=tool_choice)

    assert recorder.body["tool_choice"] == expected


def test_no_tool_choice_without_tools() -> None:
    recorder = Recorder()
    call(make_provider(recorder), tool_choice="none")

    assert "tools" not in recorder.body
    assert "tool_choice" not in recorder.body


def test_per_call_overrides() -> None:
    recorder = Recorder()
    call(make_provider(recorder), model="qwen/qwen3-32b", temperature=0.0, max_tokens=64)

    body = recorder.body
    assert body["model"] == "qwen/qwen3-32b"
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 64


def test_data_policy_zdr_and_reasoning_when_configured() -> None:
    recorder = Recorder()
    provider = make_provider(recorder, data_collection="allow", zdr=True, reasoning_effort="none")
    call(provider)

    body = recorder.body
    assert body["provider"] == {
        "require_parameters": True,
        "data_collection": "allow",
        "zdr": True,
    }
    assert body["reasoning"] == {"effort": "none"}


# --- Multi-turn serialization ----------------------------------------------


def test_assistant_tool_calls_and_tool_results_serialize_exactly() -> None:
    first = tool_call("record_field", {"field": "what", "value": "fugas"}, call_id="call_a")
    second = invalid_tool_call("record_field", '{"field": "where",', call_id="call_b")
    history = [
        USER,
        Message(role="assistant", content=None, tool_calls=(first, second)),
        Message(role="tool", tool_call_id="call_a", content='{"ok": true}'),
        Message(role="tool", tool_call_id="call_b", content='{"error": "invalid JSON"}'),
        Message(role="assistant", content="Anotado. ¿Dónde ocurre?"),
        Message(role="user", content="En la línea 3."),
    ]
    recorder = Recorder()
    call(make_provider(recorder), messages=history, tools=[RECORD_FIELD])

    assert recorder.body["messages"][1:] == [
        {"role": "user", "content": SECRET},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "record_field", "arguments": first.raw_arguments},
                },
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "record_field", "arguments": '{"field": "where",'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": '{"ok": true}'},
        {"role": "tool", "tool_call_id": "call_b", "content": '{"error": "invalid JSON"}'},
        {"role": "assistant", "content": "Anotado. ¿Dónde ocurre?"},
        {"role": "user", "content": "En la línea 3."},
    ]


# --- Response parsing -------------------------------------------------------


def function_call(call_id: str | None, name: str, arguments: object) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "function", "function": {"name": name, "arguments": arguments}}
    if call_id is not None:
        item["id"] = call_id
    return item


def test_text_only() -> None:
    recorder = Recorder(
        completion(
            message={"role": "assistant", "content": "¿Desde cuándo ocurre?"},
            usage={"prompt_tokens": 120, "completion_tokens": 8, "total_tokens": 128},
        )
    )
    response = call(make_provider(recorder))

    assert response.text == "¿Desde cuándo ocurre?"
    assert response.tool_calls == ()
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 120
    assert response.usage.completion_tokens == 8
    assert response.usage.total_tokens == 128
    assert response.usage.cost is None
    assert response.model == "mistralai/mistral-small-3.2-24b-instruct"
    assert response.upstream_provider == "Mistral"
    assert response.reasoning is None


def test_tool_calls_only_with_null_content() -> None:
    response = respond_with(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                function_call("call_1", "record_field", '{"field": "what", "value": "x"}')
            ],
        },
        finish_reason="tool_calls",
    )

    assert response.text is None
    assert response.finish_reason == "tool_calls"
    (only,) = response.tool_calls
    assert only.id == "call_1"
    assert only.name == "record_field"
    assert only.arguments == {"field": "what", "value": "x"}
    assert only.raw_arguments == '{"field": "what", "value": "x"}'
    assert only.arguments_error is None


def test_text_plus_several_tool_calls_in_order() -> None:
    response = respond_with(
        {
            "role": "assistant",
            "content": "Registro los datos.",
            "tool_calls": [
                function_call("c1", "record_field", '{"field": "what", "value": "a"}'),
                function_call("c2", "record_field", '{"field": "where", "value": "b"}'),
                function_call("c3", "log_event", '{"event_type": "evidence", "content": "c"}'),
            ],
        },
        finish_reason="tool_calls",
    )

    assert response.text == "Registro los datos."
    assert [c.id for c in response.tool_calls] == ["c1", "c2", "c3"]
    assert response.tool_names == ["record_field", "record_field", "log_event"]


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ('{"field": "what", "value": ', "invalid JSON"),
        ("not json at all", "invalid JSON"),
        ('["what", "x"]', "not a JSON object"),
        ('"what"', "not a JSON object"),
    ],
)
def test_bad_arguments_never_raise(raw: str, error: str) -> None:
    response = respond_with(
        {"role": "assistant", "content": None, "tool_calls": [function_call("c1", "t", raw)]}
    )

    (bad,) = response.tool_calls
    assert bad.arguments is None
    assert bad.raw_arguments == raw
    assert bad.arguments_error is not None
    assert error in bad.arguments_error
    assert raw not in bad.arguments_error  # the reason never quotes the arguments


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_arguments_parse_as_an_empty_object(raw: str | None) -> None:
    response = respond_with(
        {"role": "assistant", "content": None, "tool_calls": [function_call("c1", "greet", raw)]}
    )

    (only,) = response.tool_calls
    assert only.arguments == {}
    assert only.arguments_error is None


def test_arguments_sent_as_an_object_are_accepted() -> None:
    response = respond_with(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [function_call("c1", "record_field", {"field": "since", "value": "ñ"})],
        }
    )

    (only,) = response.tool_calls
    assert only.arguments == {"field": "since", "value": "ñ"}
    assert json.loads(only.raw_arguments) == {"field": "since", "value": "ñ"}


def test_missing_tool_call_ids_are_generated() -> None:
    response = respond_with(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [function_call(None, "greet", "{}"), function_call("", "greet", "{}")],
        }
    )

    assert [c.id for c in response.tool_calls] == ["call_0", "call_1"]


def test_empty_content_is_no_text() -> None:
    response = respond_with(
        {"role": "assistant", "content": "", "tool_calls": [function_call("c1", "greet", "{}")]}
    )

    assert response.text is None


def test_reasoning_is_kept_out_of_text() -> None:
    response = respond_with(
        {"role": "assistant", "content": "Respuesta.", "reasoning": "Pienso que..."},
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 50,
            "total_tokens": 60,
            "completion_tokens_details": {"reasoning_tokens": 42},
            "cost": 0.000123,
        },
    )

    assert response.text == "Respuesta."
    assert response.reasoning == "Pienso que..."
    assert response.usage.reasoning_tokens == 42
    assert response.usage.cost == pytest.approx(0.000123)


def test_reasoning_content_alias() -> None:
    response = respond_with(
        {"role": "assistant", "content": "Respuesta.", "reasoning_content": "Pienso..."}
    )

    assert response.reasoning == "Pienso..."
    assert response.text == "Respuesta."


def test_missing_usage_model_and_provider() -> None:
    recorder = Recorder(
        httpx2.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )
    )
    response = call(make_provider(recorder))

    assert response.usage.prompt_tokens is None
    assert response.usage.total_tokens is None
    assert response.finish_reason is None
    assert response.model is None
    assert response.upstream_provider is None


def test_malformed_usage_values_become_unknown() -> None:
    response = respond_with(
        {"role": "assistant", "content": "ok"},
        usage={"prompt_tokens": "10", "completion_tokens": -1, "total_tokens": True, "cost": "x"},
    )

    assert response.usage.prompt_tokens is None
    assert response.usage.completion_tokens is None
    assert response.usage.total_tokens is None
    assert response.usage.cost is None


@pytest.mark.parametrize("finish_reason", ["stop", "length", "tool_calls", "content_filter"])
def test_finish_reason_variants(finish_reason: str) -> None:
    response = respond_with({"role": "assistant", "content": "x"}, finish_reason=finish_reason)

    assert response.finish_reason == finish_reason


def test_latency_is_measured_around_the_request() -> None:
    ticks = iter([10.0, 10.25])
    response = call(make_provider(Recorder(), clock=lambda: next(ticks)))

    assert response.latency_ms == 250


# --- Errors -----------------------------------------------------------------


def error_response(status: int, **headers: str) -> httpx2.Response:
    return httpx2.Response(
        status,
        json={"error": {"code": status, "message": f"Echo of the prompt: {SECRET}"}},
        headers=headers,
    )


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, LLMBadRequestError),
        (401, LLMAuthError),
        (402, LLMInsufficientCreditsError),
        (403, LLMBadRequestError),
        (404, LLMBadRequestError),
        (408, LLMUnavailableError),
        (429, LLMRateLimitError),
        (500, LLMUnavailableError),
        (502, LLMUnavailableError),
        (503, LLMUnavailableError),
        (504, LLMUnavailableError),
    ],
)
def test_http_errors_are_mapped(status: int, error: type[LLMError]) -> None:
    provider = make_provider(Recorder(error_response(status, **{"Retry-After": "1"})))

    with pytest.raises(error) as excinfo:
        call(provider)
    assert excinfo.value.status == status
    assert str(status) in str(excinfo.value)
    assert SECRET not in str(excinfo.value)
    assert API_KEY not in str(excinfo.value)


@pytest.mark.parametrize(
    ("exception", "match"),
    [
        (httpx2.ReadTimeout("read timed out"), "timed out"),
        (httpx2.ConnectTimeout("connect timed out"), "timed out"),
        (httpx2.ConnectError(f"cannot connect, request had {SECRET}"), "unreachable"),
    ],
)
def test_transport_errors_are_unavailable(exception: Exception, match: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise exception

    with pytest.raises(LLMUnavailableError, match=match) as excinfo:
        call(make_provider(handler))
    assert SECRET not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


@pytest.mark.parametrize(
    ("code", "error"),
    [
        (402, LLMInsufficientCreditsError),
        (429, LLMRateLimitError),
        (502, LLMUnavailableError),
        (503, LLMUnavailableError),
        (400, LLMBadRequestError),
    ],
)
def test_an_error_object_in_a_200_body_is_mapped_by_its_code(
    code: int, error: type[LLMError]
) -> None:
    body = {"error": {"code": code, "message": SECRET, "metadata": {"provider_name": "X"}}}
    provider = make_provider(Recorder(httpx2.Response(200, json=body)))

    with pytest.raises(error, match="in a 200 response") as excinfo:
        call(provider)
    assert excinfo.value.status == 200
    assert SECRET not in str(excinfo.value)


def test_an_error_inside_the_choice_is_mapped() -> None:
    body = {
        "choices": [
            {
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "error",
                "error": {"code": 502, "message": SECRET},
            }
        ]
    }
    provider = make_provider(Recorder(httpx2.Response(200, json=body)))

    with pytest.raises(LLMUnavailableError, match="in a 200 response"):
        call(provider)


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": SECRET}},  # no code
        {"error": "boom"},
        {"choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "error"}]},
    ],
)
def test_an_unclassified_error_in_a_200_body_is_a_response_error(body: dict[str, Any]) -> None:
    provider = make_provider(Recorder(httpx2.Response(200, json=body)))

    with pytest.raises(LLMResponseError) as excinfo:
        call(provider)
    assert SECRET not in str(excinfo.value)


@pytest.mark.parametrize(
    ("response", "match"),
    [
        (httpx2.Response(200, content=b""), "empty body"),
        (httpx2.Response(200, content=f"<html>{SECRET}".encode()), "not JSON"),
        (httpx2.Response(200, json=[1, 2]), "malformed"),
        (httpx2.Response(200, json={"choices": []}), "no choices"),
        (httpx2.Response(200, json={"object": "chat.completion"}), "no choices"),
        (httpx2.Response(200, json={"choices": [{"finish_reason": "stop"}]}), "malformed"),
        (
            httpx2.Response(
                200, json={"choices": [{"message": {"role": "assistant", "content": 42}}]}
            ),
            "malformed",
        ),
        (
            httpx2.Response(
                200,
                json={
                    "choices": [{"message": {"content": None, "tool_calls": [{"function": {}}]}}]
                },
            ),
            "malformed",
        ),
    ],
)
def test_unusable_200_bodies_are_response_errors(response: httpx2.Response, match: str) -> None:
    with pytest.raises(LLMResponseError, match=match) as excinfo:
        call(make_provider(Recorder(response)))
    assert SECRET not in str(excinfo.value)


def test_an_unexpected_status_is_a_response_error() -> None:
    with pytest.raises(LLMResponseError, match="HTTP 302"):
        call(make_provider(Recorder(httpx2.Response(302))))


# --- Configuration ----------------------------------------------------------


def test_a_missing_key_fails_on_use_without_calling_out() -> None:
    recorder = Recorder()
    provider = make_provider(recorder, api_key=None)

    with pytest.raises(LLMConfigError, match="OPENROUTER_API_KEY"):
        call(provider)
    assert recorder.requests == []


def test_malformed_requests_fail_before_the_key_check() -> None:
    provider = make_provider(Recorder(), api_key=None)

    with pytest.raises(ValueError, match="must not be empty"):
        call(provider, messages=[])


def test_builds_its_own_client_with_both_timeouts() -> None:
    provider = OpenRouterProvider(
        api_key=API_KEY, model="m", base_url=BASE_URL, timeout_seconds=45.0
    )
    try:
        timeout = provider.client_timeout
        assert timeout.read == 45.0
        assert timeout.connect == 10.0
    finally:
        provider.close()
