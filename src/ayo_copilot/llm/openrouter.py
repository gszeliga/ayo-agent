"""Client for OpenRouter's chat completions (OpenAI-compatible), with tool calling.

The facts this relies on, with the documentation URLs, are in
`docs/decisions/0003-llm-provider.md`. One request per call for now; retries come later.
Error messages never hold the key, message content or a response body: an error body can
echo the prompt.
"""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import httpx2

from ayo_copilot.llm.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMInsufficientCreditsError,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
)
from ayo_copilot.llm.provider import check_request
from ayo_copilot.llm.types import (
    TOOL_CHOICE_MODES,
    LLMResponse,
    Message,
    ToolCall,
    ToolChoice,
    ToolSpec,
    Usage,
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
COMPLETIONS_PATH = "/chat/completions"
# Fixed: a connection that takes longer is not coming. The read timeout is configurable.
CONNECT_TIMEOUT_SECONDS = 10.0


class OpenRouterProvider:
    """`LLMProvider` over OpenRouter. Built without a key it still constructs, so the app
    starts; `complete` then raises `LLMConfigError` before any network call."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout_seconds: float = 60.0,
        base_url: str = DEFAULT_BASE_URL,
        data_collection: Literal["allow", "deny"] = "deny",
        zdr: bool = False,
        reasoning_effort: str | None = None,
        app_url: str | None = None,
        app_title: str | None = None,
        client: httpx2.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.data_collection = data_collection
        self.zdr = zdr
        self.reasoning_effort = reasoning_effort
        self._api_key = api_key
        self._attribution = {
            name: value
            for name, value in (("HTTP-Referer", app_url), ("X-OpenRouter-Title", app_title))
            if value
        }
        self._client = client or httpx2.Client(
            base_url=base_url,
            timeout=httpx2.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS),
        )
        self._clock = clock

    @property
    def client_timeout(self) -> httpx2.Timeout:
        return self._client.timeout

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        check_request(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if self._api_key is None:
            raise LLMConfigError("OPENROUTER_API_KEY is not set: the language model is unavailable")
        payload = self._payload(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            model=model or self.model,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        started = self._clock()
        response = self._post(payload)
        latency_ms = max(0, round((self._clock() - started) * 1000))
        return parse_completion(response, latency_ms=latency_ms)

    def _payload(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None,
        tool_choice: ToolChoice,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        wire_messages = [{"role": "system", "content": system}] if system else []
        wire_messages.extend(serialize_message(m) for m in messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": wire_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [serialize_tool(t) for t in tools]
            payload["tool_choice"] = serialize_tool_choice(tool_choice)
        # Only upstream providers that honour every parameter we send: one that silently
        # ignored `tools` would look like a model that never calls tools.
        preferences: dict[str, Any] = {
            "require_parameters": True,
            "data_collection": self.data_collection,
        }
        if self.zdr:
            preferences["zdr"] = True
        payload["provider"] = preferences
        if self.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        return payload

    def _post(self, payload: dict[str, Any]) -> httpx2.Response:
        headers = {"Authorization": f"Bearer {self._api_key}", **self._attribution}
        try:
            response = self._client.post(COMPLETIONS_PATH, json=payload, headers=headers)
        except httpx2.TimeoutException as exc:
            raise LLMUnavailableError(f"OpenRouter timed out ({type(exc).__name__})") from None
        except httpx2.TransportError as exc:
            # The exception text is dropped: it can quote the request.
            raise LLMUnavailableError(f"OpenRouter unreachable ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise error_for_status(response.status_code)
        return response


# --- Serialization ----------------------------------------------------------


def serialize_message(message: Message) -> dict[str, Any]:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                # Exactly what the model produced, invalid JSON included: the caller decides.
                "function": {"name": call.name, "arguments": call.raw_arguments},
            }
            for call in message.tool_calls
        ]
    return wire


def serialize_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
        },
    }


def serialize_tool_choice(tool_choice: ToolChoice) -> str | dict[str, Any]:
    if tool_choice in TOOL_CHOICE_MODES:
        return tool_choice
    return {"type": "function", "function": {"name": tool_choice}}


# --- Errors -----------------------------------------------------------------

_STATUS_ERRORS: dict[int, tuple[type[LLMError], str]] = {
    401: (LLMAuthError, "API key refused"),
    402: (LLMInsufficientCreditsError, "insufficient credits"),
    403: (LLMBadRequestError, "forbidden: moderation or guardrail"),
    408: (LLMUnavailableError, "request timed out"),
    429: (LLMRateLimitError, "rate limited"),
}


def _classify(code: int) -> tuple[type[LLMError], str] | None:
    """The exception and a short reason for an error status, None if it is not one."""
    if code in _STATUS_ERRORS:
        return _STATUS_ERRORS[code]
    if 500 <= code < 600:
        return LLMUnavailableError, "provider or model unavailable"
    if 400 <= code < 500:
        return LLMBadRequestError, "request rejected"
    return None


def error_for_status(status: int) -> LLMError:
    """The exception for a non-200 HTTP answer. The body is dropped: it can echo the input."""
    classified = _classify(status)
    if classified is None:
        return LLMResponseError(f"OpenRouter returned an unexpected HTTP {status}", status=status)
    error_type, reason = classified
    return error_type(f"OpenRouter returned HTTP {status} ({reason})", status=status)


def _error_in_body(error: object) -> LLMError:
    """An error object sent with HTTP 200 (the status is committed before generation), mapped
    by its `code` like an HTTP status. Its message is dropped."""
    code = error.get("code") if isinstance(error, Mapping) else None
    classified = _classify(code) if isinstance(code, int) and not isinstance(code, bool) else None
    if classified is None:
        return LLMResponseError("OpenRouter returned an error in a 200 response", status=200)
    error_type, reason = classified
    return error_type(
        f"OpenRouter returned error code {code} in a 200 response ({reason})", status=200
    )


def _malformed(what: str) -> LLMResponseError:
    return LLMResponseError(f"OpenRouter returned a malformed response ({what})", status=200)


# --- Parsing ----------------------------------------------------------------


def parse_completion(response: httpx2.Response, *, latency_ms: int) -> LLMResponse:
    """Normalize a 200 answer. Raises LLMError subclasses for anything unusable; never keeps
    the raw body."""
    if not response.content.strip():
        raise LLMResponseError("OpenRouter returned an empty body", status=200)
    try:
        body = response.json()
    except ValueError:
        raise LLMResponseError("OpenRouter returned a body that is not JSON", status=200) from None
    if not isinstance(body, dict):
        raise _malformed("body is not an object")
    if body.get("error") is not None:
        raise _error_in_body(body["error"])
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError("OpenRouter returned no choices", status=200)
    choice = choices[0]
    if not isinstance(choice, dict):
        raise _malformed("choice is not an object")
    if choice.get("error") is not None:
        raise _error_in_body(choice["error"])
    finish_reason = choice.get("finish_reason")
    if finish_reason == "error":
        raise LLMResponseError("OpenRouter returned an error in a 200 response", status=200)
    message = choice.get("message")
    if not isinstance(message, dict):
        raise _malformed("no message")

    return LLMResponse(
        text=_text(message.get("content")),
        tool_calls=_tool_calls(message.get("tool_calls")),
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        usage=_usage(body.get("usage")),
        model=_string(body.get("model")),
        upstream_provider=_string(body.get("provider")),
        latency_ms=latency_ms,
        reasoning=_string(message.get("reasoning")) or _string(message.get("reasoning_content")),
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _text(content: object) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):  # content parts: keep the text ones, in order
        parts = [
            p["text"] for p in content if isinstance(p, dict) and isinstance(p.get("text"), str)
        ]
        return "".join(parts) or None
    raise _malformed("content is not text")


def _tool_calls(raw: object) -> tuple[ToolCall, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise _malformed("tool_calls is not a list")
    calls = []
    for index, item in enumerate(raw):
        function = item.get("function") if isinstance(item, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name:
            raise _malformed("tool call without a function name")
        call_id = item.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"call_{index}"
        arguments, raw_arguments, error = parse_arguments(function.get("arguments"))
        calls.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
                raw_arguments=raw_arguments,
                arguments_error=error,
            )
        )
    return tuple(calls)


def parse_arguments(raw: object) -> tuple[dict[str, Any] | None, str, str | None]:
    """(arguments, raw string, error). Never raises: invalid arguments are data for the
    caller. Empty arguments are an empty object (a tool without parameters). The error says
    where parsing failed, never what the arguments were."""
    if raw is None:
        raw = ""
    if isinstance(raw, Mapping):  # some providers send an object instead of a JSON string
        return dict(raw), json.dumps(raw, ensure_ascii=False), None
    if not isinstance(raw, str):
        return None, json.dumps(raw, ensure_ascii=False), "arguments are not a JSON object"
    if not raw.strip():
        return {}, raw, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, raw, f"invalid JSON: {exc.msg} at position {exc.pos}"
    if not isinstance(parsed, dict):
        return None, raw, "arguments are not a JSON object"
    return parsed, raw, None


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _usage(raw: object) -> Usage:
    if not isinstance(raw, dict):
        return Usage()
    details = raw.get("completion_tokens_details")
    cost = raw.get("cost")
    return Usage(
        prompt_tokens=_count(raw.get("prompt_tokens")),
        completion_tokens=_count(raw.get("completion_tokens")),
        total_tokens=_count(raw.get("total_tokens")),
        reasoning_tokens=_count(details.get("reasoning_tokens"))
        if isinstance(details, dict)
        else None,
        cost=float(cost)
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0
        else None,
    )
