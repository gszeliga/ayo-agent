from types import SimpleNamespace

import httpx2
import pytest

from ayo_copilot.config import LLMSettings
from ayo_copilot.dependencies import get_llm_provider
from ayo_copilot.llm import LLMConfigError, LLMProvider, Message
from ayo_copilot.llm.build import build_llm_provider, describe_llm_provider
from ayo_copilot.llm.fake import FakeLLMProvider
from ayo_copilot.llm.openrouter import OpenRouterProvider

KEY = "sk-or-v1-build-test-key"


def llm_settings(**overrides: object) -> LLMSettings:
    return LLMSettings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def no_key_in_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_maps_every_setting() -> None:
    settings = llm_settings(
        openrouter_api_key=KEY,
        openrouter_base_url="https://openrouter.test/api/v1",
        llm_model="qwen/qwen3-32b",
        llm_temperature=0.5,
        llm_max_tokens=300,
        llm_timeout_seconds=25,
        llm_max_retries=4,
        llm_retry_budget_seconds=40,
        llm_data_collection="allow",
        llm_zdr=True,
        llm_reasoning_effort="low",
        llm_app_url="https://ayo.example",
        llm_app_title="AYO",
    )

    provider = build_llm_provider(settings)

    assert isinstance(provider, OpenRouterProvider)
    try:
        assert provider.model == "qwen/qwen3-32b"
        assert provider.temperature == 0.5
        assert provider.max_tokens == 300
        assert provider.client_timeout.read == 25
        assert provider.client_timeout.connect == 10
        assert provider.max_retries == 4
        assert provider.retry_budget_seconds == 40
        assert provider.data_collection == "allow"
        assert provider.zdr is True
        assert provider.reasoning_effort == "low"
        assert provider._attribution == {
            "HTTP-Referer": "https://ayo.example",
            "X-OpenRouter-Title": "AYO",
        }
        assert provider._api_key == KEY
        assert str(provider._client.base_url).rstrip("/") == "https://openrouter.test/api/v1"
    finally:
        provider.close()


def test_builds_without_a_key_and_fails_only_on_use() -> None:
    provider = build_llm_provider(llm_settings())
    assert isinstance(provider, OpenRouterProvider)
    requests: list[httpx2.Request] = []
    provider._client = httpx2.Client(
        transport=httpx2.MockTransport(lambda r: requests.append(r) or httpx2.Response(200))
    )

    with pytest.raises(LLMConfigError, match="OPENROUTER_API_KEY"):
        provider.complete(system="s", messages=[Message(role="user", content="Hola")])
    assert requests == []
    provider.close()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {},
            "llm: openrouter model=mistralai/mistral-small-3.2-24b-instruct"
            " data_collection=deny zdr=false reasoning_effort=default key=missing",
        ),
        (
            {"openrouter_api_key": KEY, "llm_zdr": True, "llm_reasoning_effort": "none"},
            "llm: openrouter model=mistralai/mistral-small-3.2-24b-instruct"
            " data_collection=deny zdr=true reasoning_effort=none key=set",
        ),
    ],
)
def test_describe_never_shows_the_key(overrides: dict[str, object], expected: str) -> None:
    settings = llm_settings(**overrides)
    provider = build_llm_provider(settings)

    assert describe_llm_provider(provider, settings) == expected
    provider.close()


def test_describe_another_provider() -> None:
    assert describe_llm_provider(FakeLLMProvider(), llm_settings()) == "llm: FakeLLMProvider"


def test_get_llm_provider_returns_the_app_state_provider() -> None:
    fake = FakeLLMProvider()
    request = SimpleNamespace(state=SimpleNamespace(llm=fake))

    provider = get_llm_provider(request)  # type: ignore[arg-type]

    assert provider is fake
    assert isinstance(provider, LLMProvider)
