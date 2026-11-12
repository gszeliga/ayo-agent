"""Provider-independent request and response types for language models.

Message content, tool arguments, response text and reasoning hold customer content: they
are left out of every `repr`, so an accidental log line or assertion message cannot leak
them. Each type checks its own invariants when built and raises TypeError or ValueError.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant", "tool"]
ROLES: frozenset[str] = frozenset({"user", "assistant", "tool"})

# "auto", "none", "required", or the name of one offered tool to force.
ToolChoice = Literal["auto", "none", "required"] | str
TOOL_CHOICE_MODES: frozenset[str] = frozenset({"auto", "none", "required"})

# The function-name rule of the OpenAI-compatible tools format.
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _tuple_of(value: object, item_type: type, what: str) -> tuple[Any, ...]:
    """`value` as a tuple, accepting any list or tuple of `item_type`."""
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{what} must be a list or tuple of {item_type.__name__}")
    for item in value:
        if not isinstance(item, item_type):
            raise TypeError(f"{what} must only hold {item_type.__name__} objects")
    return tuple(value)


@dataclass(frozen=True)
class ToolSpec:
    """A tool offered to the model. `parameters` is a JSON Schema of type object."""

    name: str
    description: str
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not TOOL_NAME_PATTERN.match(self.name):
            raise ValueError("tool name must be 1-64 letters, digits, '_' or '-'")
        if not isinstance(self.description, str):
            raise TypeError("tool description must be a string")
        if not isinstance(self.parameters, Mapping) or self.parameters.get("type") != "object":
            raise ValueError(f"tool {self.name}: parameters must be a JSON Schema of type object")


@dataclass(frozen=True)
class ToolCall:
    """A tool call the model asked for.

    `arguments` is the parsed JSON object, or None when the model's JSON was invalid; then
    `arguments_error` says why, and `raw_arguments` keeps exactly what came back, so the
    caller can decide what to do (for example, send the error back to the model).
    """

    id: str
    name: str
    arguments: Mapping[str, Any] | None = field(repr=False)
    raw_arguments: str = field(repr=False)
    arguments_error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("tool call id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("tool call name must be a non-empty string")
        if not isinstance(self.raw_arguments, str):
            raise TypeError("tool call raw_arguments must be a string")
        if (self.arguments is None) == (self.arguments_error is None):
            raise ValueError("a tool call has either arguments or an arguments_error, not both")
        if self.arguments is not None and not isinstance(self.arguments, Mapping):
            raise TypeError("tool call arguments must be a JSON object (a mapping)")

    @property
    def is_valid(self) -> bool:
        """Whether the arguments parsed as a JSON object (not whether they fit the schema)."""
        return self.arguments is not None


@dataclass(frozen=True)
class Message:
    """One turn of the conversation. The system prompt is not a message: providers take it
    as a separate argument.

    - `user`: `content` only.
    - `assistant`: `content`, `tool_calls` or both.
    - `tool`: the result (`content`) of the call named by `tool_call_id`.
    """

    role: Role
    content: str | None = field(default=None, repr=False)
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {sorted(ROLES)}")
        if self.content is not None and not isinstance(self.content, str):
            raise TypeError("message content must be a string or None")
        object.__setattr__(
            self, "tool_calls", _tuple_of(self.tool_calls, ToolCall, "message tool_calls")
        )
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages carry tool_calls")
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("a tool message needs the tool_call_id it answers")
            if self.content is None:
                raise ValueError("a tool message needs content (the tool's result)")
        elif self.tool_call_id is not None:
            raise ValueError("only tool messages carry a tool_call_id")
        if self.role == "user" and self.content is None:
            raise ValueError("a user message needs content")
        if self.role == "assistant" and self.content is None and not self.tool_calls:
            raise ValueError("an assistant message needs content, tool_calls or both")


@dataclass(frozen=True)
class Usage:
    """Token counts and cost as the provider reported them; None when not reported."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    # Part of completion_tokens, when the model reasons and the provider reports it.
    reasoning_tokens: int | None = None
    # In the provider's billing unit (OpenRouter: credits, about USD).
    cost: float | None = None

    def __post_init__(self) -> None:
        for name in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"usage {name} must be a non-negative integer or None")
        if self.cost is not None and (
            isinstance(self.cost, bool) or not isinstance(self.cost, (int, float)) or self.cost < 0
        ):
            raise ValueError("usage cost must be a non-negative number or None")


@dataclass(frozen=True)
class LLMResponse:
    """A normalized model response. It never keeps the raw body, only these fields.

    `text` is None when the model only called tools. `reasoning` is the model's reasoning,
    if it returned any, kept apart from `text` and never logged.
    """

    text: str | None = field(default=None, repr=False)
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    model: str | None = None
    upstream_provider: str | None = None
    # The whole call, retries and waits included.
    latency_ms: int = 0
    reasoning: str | None = field(default=None, repr=False)
    # The provider's id for this generation (OpenRouter: `gen-...`), to look the call up.
    generation_id: str | None = None
    attempts: int = 1

    def __post_init__(self) -> None:
        if self.text is not None and not isinstance(self.text, str):
            raise TypeError("response text must be a string or None")
        if self.reasoning is not None and not isinstance(self.reasoning, str):
            raise TypeError("response reasoning must be a string or None")
        object.__setattr__(
            self, "tool_calls", _tuple_of(self.tool_calls, ToolCall, "response tool_calls")
        )
        if not isinstance(self.usage, Usage):
            raise TypeError("response usage must be a Usage")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise TypeError("response latency_ms must be an integer")
        if self.latency_ms < 0:
            raise ValueError("response latency_ms must not be negative")
        if self.generation_id is not None and not isinstance(self.generation_id, str):
            raise TypeError("response generation_id must be a string or None")
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("response attempts must be an integer")
        if self.attempts < 1:
            raise ValueError("response attempts must be at least 1")

    @property
    def tool_names(self) -> list[str]:
        """The names of the tools called, in order (safe to log)."""
        return [call.name for call in self.tool_calls]
