"""The interface every language model provider implements."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ayo_copilot.llm.types import TOOL_CHOICE_MODES, LLMResponse, Message, ToolChoice, ToolSpec


@runtime_checkable
class LLMProvider(Protocol):
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
        """One completion. `model`, `temperature` and `max_tokens` override the provider's
        defaults for this call only. Synchronous, like the embedder: callers run it from
        sync endpoints (in FastAPI's thread pool), never on the event loop."""
        ...


def check_request(
    *,
    system: str,
    messages: Sequence[Message],
    tools: Sequence[ToolSpec] | None,
    tool_choice: ToolChoice,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> None:
    """Reject a request no provider could serve, before any network call. These are
    programming errors (TypeError or ValueError), not provider failures."""
    if not isinstance(system, str):
        raise TypeError("system must be a string")
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence):
        raise TypeError("messages must be a list of Message")
    if not messages:
        raise ValueError("messages must not be empty")
    if not all(isinstance(m, Message) for m in messages):
        raise TypeError("messages must only hold Message objects")
    names: list[str] = []
    if tools is not None:
        if isinstance(tools, (str, bytes)) or not isinstance(tools, Sequence):
            raise TypeError("tools must be a list of ToolSpec or None")
        if not all(isinstance(t, ToolSpec) for t in tools):
            raise TypeError("tools must only hold ToolSpec objects")
        names = [t.name for t in tools]
        if len(set(names)) != len(names):
            raise ValueError("tool names must be unique")
    if not isinstance(tool_choice, str) or not tool_choice:
        raise ValueError("tool_choice must be 'auto', 'none', 'required' or a tool name")
    if tool_choice not in TOOL_CHOICE_MODES and tool_choice not in names:
        raise ValueError("tool_choice names a tool that is not offered")
    if tool_choice == "required" and not names:
        raise ValueError("tool_choice 'required' needs at least one tool")
    if model is not None and (not isinstance(model, str) or not model):
        raise ValueError("model must be a non-empty string or None")
    if temperature is not None and (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not 0 <= temperature <= 2
    ):
        raise ValueError("temperature must be between 0 and 2")
    if max_tokens is not None and (
        isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0
    ):
        raise ValueError("max_tokens must be a positive integer")
