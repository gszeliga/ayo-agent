"""Language model access: provider-independent types, the provider interface, errors and a
scripted fake for tests. No endpoint uses it yet."""

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
from ayo_copilot.llm.provider import LLMProvider
from ayo_copilot.llm.types import LLMResponse, Message, ToolCall, ToolChoice, ToolSpec, Usage

__all__ = [
    "LLMAuthError",
    "LLMBadRequestError",
    "LLMConfigError",
    "LLMError",
    "LLMInsufficientCreditsError",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMResponseError",
    "LLMUnavailableError",
    "Message",
    "ToolCall",
    "ToolChoice",
    "ToolSpec",
    "Usage",
]
