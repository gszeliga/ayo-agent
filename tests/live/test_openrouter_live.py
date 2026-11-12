"""Real OpenRouter calls with the configured model (LLM_MODEL, from the environment or
.env). Three requests of a few hundred tokens: well under USD 0.001 in total."""

from collections.abc import Iterator

import pytest

from ayo_copilot.config import LLMSettings
from ayo_copilot.llm import Message, ToolSpec
from ayo_copilot.llm.build import build_llm_provider
from ayo_copilot.llm.openrouter import OpenRouterProvider

pytestmark = pytest.mark.live

COLORS = ["rojo", "verde", "azul"]
SET_COLOR = ToolSpec(
    name="set_color",
    description="Fija el color del semáforo de la línea.",
    parameters={
        "type": "object",
        "properties": {"color": {"type": "string", "enum": COLORS}},
        "required": ["color"],
        "additionalProperties": False,
    },
)


@pytest.fixture
def provider() -> Iterator[OpenRouterProvider]:
    settings = LLMSettings()
    if settings.openrouter_api_key is None:
        pytest.skip("OPENROUTER_API_KEY is not set (environment or .env)")
    built = build_llm_provider(settings)
    assert isinstance(built, OpenRouterProvider)
    try:
        yield built
    finally:
        built.close()


def test_minimal_completion(provider: OpenRouterProvider) -> None:
    response = provider.complete(
        system="Responde con una sola palabra.",
        messages=[Message(role="user", content="Responde solo: ok")],
        max_tokens=16,
    )

    assert response.text
    assert response.usage.prompt_tokens and response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens and response.usage.completion_tokens > 0
    assert response.generation_id
    assert response.model


@pytest.mark.parametrize("tool_choice", ["set_color", "required"])
def test_tool_call_is_parsed(provider: OpenRouterProvider, tool_choice: str) -> None:
    response = provider.complete(
        system="Eres un asistente de planta. Usa la herramienta cuando corresponda.",
        messages=[Message(role="user", content="Pon el semáforo de la línea en verde.")],
        tools=[SET_COLOR],
        tool_choice=tool_choice,
        max_tokens=100,
    )

    assert len(response.tool_calls) == 1
    (call,) = response.tool_calls
    assert call.name == "set_color"
    assert call.arguments_error is None
    assert call.arguments == {"color": "verde"}
