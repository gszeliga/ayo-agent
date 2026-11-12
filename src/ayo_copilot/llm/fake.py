"""A scripted provider for tests: no network, fully deterministic.

It returns the queued responses in order and records every call. It fails loudly when it
runs out, when anything but an `LLMResponse` is queued, and when a request is malformed
(the same checks a real provider makes before calling out). It does not check that a
scripted tool call names an offered tool: tests need it to imitate models that get that
wrong.
"""

import json
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ayo_copilot.llm.provider import check_request
from ayo_copilot.llm.types import LLMResponse, Message, ToolCall, ToolChoice, ToolSpec, Usage


class FakeLLMExhaustedError(AssertionError):
    """The fake was called more times than responses were scripted."""


@dataclass(frozen=True)
class RecordedCall:
    """One call received by the fake, as given (lists copied to tuples)."""

    system: str = field(repr=False)
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] | None
    tool_choice: ToolChoice
    model: str | None
    temperature: float | None
    max_tokens: int | None

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools or ()]


class FakeLLMProvider:
    def __init__(self, responses: Iterable[LLMResponse] = ()) -> None:
        self._queue: deque[LLMResponse] = deque()
        self.calls: list[RecordedCall] = []
        self.add(*responses)

    def add(self, *responses: LLMResponse) -> None:
        """Queue more responses, returned after the ones already queued."""
        for response in responses:
            if not isinstance(response, LLMResponse):
                raise TypeError(
                    f"FakeLLMProvider can only return LLMResponse, got {type(response).__name__}"
                )
        self._queue.extend(responses)

    @property
    def remaining(self) -> int:
        """Responses queued and not returned yet."""
        return len(self._queue)

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
        # Recorded before the queue is checked, so a test can see the unexpected call.
        self.calls.append(
            RecordedCall(
                system=system,
                messages=tuple(messages),
                tools=None if tools is None else tuple(tools),
                tool_choice=tool_choice,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
        if not self._queue:
            raise FakeLLMExhaustedError(
                f"FakeLLMProvider has no scripted response left for call {len(self.calls)}"
            )
        return self._queue.popleft()


def tool_call(name: str, arguments: Mapping[str, Any], *, call_id: str | None = None) -> ToolCall:
    """A valid tool call; its raw arguments are the JSON of `arguments`."""
    return ToolCall(
        id=call_id or f"call_{name}",
        name=name,
        arguments=dict(arguments),
        raw_arguments=json.dumps(arguments, ensure_ascii=False),
    )


def invalid_tool_call(
    name: str,
    raw_arguments: str,
    *,
    call_id: str | None = None,
    error: str = "invalid JSON",
) -> ToolCall:
    """A tool call whose arguments did not parse, as a provider reports it."""
    return ToolCall(
        id=call_id or f"call_{name}",
        name=name,
        arguments=None,
        raw_arguments=raw_arguments,
        arguments_error=error,
    )


def text_response(text: str, **fields: Any) -> LLMResponse:
    """A text-only response (`finish_reason` "stop" unless given)."""
    fields.setdefault("finish_reason", "stop")
    fields.setdefault("usage", Usage())
    return LLMResponse(text=text, **fields)


def tool_calls_response(*calls: ToolCall, text: str | None = None, **fields: Any) -> LLMResponse:
    """A response with these tool calls, in order (`finish_reason` "tool_calls")."""
    if not calls:
        raise ValueError("tool_calls_response needs at least one ToolCall")
    fields.setdefault("finish_reason", "tool_calls")
    return LLMResponse(text=text, tool_calls=calls, **fields)
