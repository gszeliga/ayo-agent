"""Client for OpenRouter's chat completions (OpenAI-compatible), with tool calling.

The facts this relies on, with the documentation URLs, are in
`docs/decisions/0003-llm-provider.md`. Error messages and logs never hold the key, message
content, tool arguments or a response body: an error body can echo the prompt.
"""

import json
import logging
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from email.utils import parsedate_to_datetime
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
    TOOL_NAME_PATTERN,
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
# Backoff without Retry-After: full jitter, up to 1, 2, 4, ... seconds, never above this.
MAX_BACKOFF_SECONDS = 10.0
# Worth another attempt: the same request can succeed later.
RETRYABLE_ERRORS = (LLMRateLimitError, LLMUnavailableError)

logger = logging.getLogger(__name__)


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
        max_retries: int = 2,
        retry_budget_seconds: float = 90.0,
        base_url: str = DEFAULT_BASE_URL,
        data_collection: Literal["allow", "deny"] = "deny",
        zdr: bool = False,
        reasoning_effort: str | None = None,
        app_url: str | None = None,
        app_title: str | None = None,
        client: httpx2.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        """`clock` measures latency and the retry budget, `sleep` waits between attempts,
        `wall_clock` (Unix time) reads `Retry-After` dates; all injectable for tests."""
        self.model = model
        self.max_retries = max_retries
        self.retry_budget_seconds = retry_budget_seconds
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
        self._sleep = sleep
        self._wall_clock = wall_clock

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
        requested = model or self.model
        payload = self._payload(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            model=requested,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        started = self._clock()
        retried: list[str] = []
        generation_ids: list[str] = []
        attempt = 0
        while True:
            attempt += 1
            try:
                result = parse_completion(self._post(payload), latency_ms=0)
            except LLMError as exc:
                if exc.generation_id:
                    generation_ids.append(exc.generation_id)
                delay = self._retry_delay(exc, attempt=attempt, started=started)
                if delay is None:
                    self._finish_error(exc, attempt, generation_ids)
                    _log_error(exc, requested, retried, self._elapsed_ms(started))
                    raise
                retried.append(exc.reason or type(exc).__name__)
                self._sleep(delay)
                continue
            if result.generation_id:
                generation_ids.append(result.generation_id)
            result = replace(result, latency_ms=self._elapsed_ms(started), attempts=attempt)
            _log_success(result, requested, retried, generation_ids)
            return result

    def _elapsed_ms(self, started: float) -> int:
        return max(0, round((self._clock() - started) * 1000))

    def _retry_delay(self, exc: LLMError, *, attempt: int, started: float) -> float | None:
        """Seconds to wait before the next attempt, or None to give up now: the error is
        not retryable, the attempts are spent, or the wait would end past the budget."""
        if not isinstance(exc, RETRYABLE_ERRORS) or attempt > self.max_retries:
            return None
        if exc.retry_after is not None:
            delay = exc.retry_after
        else:
            delay = random.uniform(0, min(MAX_BACKOFF_SECONDS, 2.0 ** (attempt - 1)))
        if self._clock() - started + delay >= self.retry_budget_seconds:
            return None
        return delay

    @staticmethod
    def _finish_error(exc: LLMError, attempts: int, generation_ids: list[str]) -> None:
        exc.attempts = attempts
        exc.generation_ids = tuple(generation_ids)
        if attempts > 1:
            exc.args = (f"{exc.args[0]}, after {attempts} attempts",)

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
            raise LLMUnavailableError(
                f"OpenRouter timed out ({type(exc).__name__})", reason="timeout"
            ) from None
        except httpx2.TransportError as exc:
            # The exception text is dropped: it can quote the request.
            raise LLMUnavailableError(
                f"OpenRouter unreachable ({type(exc).__name__})", reason="connection"
            ) from None
        if response.status_code != 200:
            retry_after = parse_retry_after(
                response.headers.get("retry-after"), now=self._wall_clock()
            )
            raise error_for_status(response.status_code, retry_after=retry_after)
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


def error_for_status(status: int, *, retry_after: float | None = None) -> LLMError:
    """The exception for a non-200 HTTP answer. The body is dropped: it can echo the input."""
    classified = _classify(status)
    if classified is None:
        return LLMResponseError(
            f"OpenRouter returned an unexpected HTTP {status}",
            status=status,
            reason=f"http_{status}",
        )
    error_type, description = classified
    return error_type(
        f"OpenRouter returned HTTP {status} ({description})",
        status=status,
        reason=f"http_{status}",
        retry_after=retry_after,
    )


def _error_in_body(error: object, generation_id: str | None) -> LLMError:
    """An error object sent with HTTP 200 (the status is committed before generation), mapped
    by its `code` like an HTTP status. Its message is dropped."""
    code = error.get("code") if isinstance(error, Mapping) else None
    classified = _classify(code) if isinstance(code, int) and not isinstance(code, bool) else None
    if classified is None:
        return LLMResponseError(
            "OpenRouter returned an error in a 200 response",
            status=200,
            reason="body_error",
            generation_id=generation_id,
        )
    error_type, description = classified
    return error_type(
        f"OpenRouter returned error code {code} in a 200 response ({description})",
        status=200,
        reason=f"body_{code}",
        generation_id=generation_id,
    )


def _malformed(what: str, generation_id: str | None = None) -> LLMResponseError:
    return LLMResponseError(
        f"OpenRouter returned a malformed response ({what})",
        status=200,
        reason="malformed",
        generation_id=generation_id,
    )


def parse_retry_after(value: str | None, *, now: float) -> float | None:
    """Seconds to wait from a `Retry-After` header: a number of seconds or an HTTP date.
    None when absent or unreadable; a date in the past means no wait."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - now
        except (TypeError, ValueError, IndexError):
            return None
    if seconds != seconds:  # NaN
        return None
    return max(0.0, seconds)


# --- Parsing ----------------------------------------------------------------


def parse_completion(response: httpx2.Response, *, latency_ms: int) -> LLMResponse:
    """Normalize a 200 answer. Raises LLMError subclasses for anything unusable; never keeps
    the raw body."""
    if not response.content.strip():
        raise LLMResponseError("OpenRouter returned an empty body", status=200, reason="empty")
    try:
        body = response.json()
    except ValueError:
        raise LLMResponseError(
            "OpenRouter returned a body that is not JSON", status=200, reason="not_json"
        ) from None
    if not isinstance(body, dict):
        raise _malformed("body is not an object")
    generation_id = _string(body.get("id"))
    if body.get("error") is not None:
        raise _error_in_body(body["error"], generation_id)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError(
            "OpenRouter returned no choices",
            status=200,
            reason="no_choices",
            generation_id=generation_id,
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise _malformed("choice is not an object", generation_id)
    if choice.get("error") is not None:
        raise _error_in_body(choice["error"], generation_id)
    finish_reason = choice.get("finish_reason")
    if finish_reason == "error":
        raise _error_in_body(None, generation_id)
    message = choice.get("message")
    if not isinstance(message, dict):
        raise _malformed("no message", generation_id)
    try:
        text = _text(message.get("content"))
        tool_calls = _tool_calls(message.get("tool_calls"))
    except LLMResponseError as exc:
        exc.generation_id = generation_id
        exc.generation_ids = (generation_id,) if generation_id else ()
        raise

    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        usage=_usage(body.get("usage")),
        model=_string(body.get("model")),
        upstream_provider=_string(body.get("provider")),
        latency_ms=latency_ms,
        reasoning=_string(message.get("reasoning")) or _string(message.get("reasoning_content")),
        generation_id=generation_id,
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


# --- Logging ----------------------------------------------------------------
# One line per call. Only metadata: never message content, the system prompt, tool
# arguments, text, reasoning, response bodies or the key.


def _safe_tool_name(name: str) -> str:
    """A model can return any string as a tool name; only plausible names are logged."""
    return name if TOOL_NAME_PATTERN.match(name) else "<invalid>"


def _or_dash(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _joined(values: Sequence[str]) -> str:
    return ",".join(values) or "-"


def _log_success(
    result: LLMResponse, requested: str, retried: list[str], generation_ids: list[str]
) -> None:
    usage = result.usage
    logger.info(
        "llm call: outcome=ok status=200 model_requested=%s model_used=%s provider=%s"
        " attempts=%d retried=%s latency_ms=%d prompt_tokens=%s completion_tokens=%s"
        " reasoning_tokens=%s cost=%s finish_reason=%s tool_calls=%d tools=%s"
        " generation_ids=%s",
        requested,
        _or_dash(result.model),
        _or_dash(result.upstream_provider),
        result.attempts,
        _joined(retried),
        result.latency_ms,
        _or_dash(usage.prompt_tokens),
        _or_dash(usage.completion_tokens),
        _or_dash(usage.reasoning_tokens),
        _or_dash(usage.cost),
        _or_dash(result.finish_reason),
        len(result.tool_calls),
        _joined([_safe_tool_name(c.name) for c in result.tool_calls]),
        _joined(generation_ids),
    )


def _log_error(exc: LLMError, requested: str, retried: list[str], latency_ms: int) -> None:
    logger.warning(
        "llm call: outcome=error error=%s reason=%s status=%s model_requested=%s attempts=%d"
        " retried=%s latency_ms=%d generation_ids=%s",
        type(exc).__name__,
        _or_dash(exc.reason),
        _or_dash(exc.status),
        requested,
        exc.attempts,
        _joined(retried),
        latency_ms,
        _joined(exc.generation_ids),
    )
