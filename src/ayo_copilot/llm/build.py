"""Build the configured language model provider from the settings."""

from ayo_copilot.config import LLMSettings
from ayo_copilot.llm.openrouter import OpenRouterProvider
from ayo_copilot.llm.provider import LLMProvider


def build_llm_provider(settings: LLMSettings) -> LLMProvider:
    """Never fails for a missing key and makes no request: building is cheap, and a call
    without a key raises `LLMConfigError`. So the app starts without a language model."""
    # LLM_PROVIDER only allows "openrouter" for now; a second provider branches here.
    key = settings.openrouter_api_key
    return OpenRouterProvider(
        api_key=key.get_secret_value() if key is not None else None,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_budget_seconds=settings.llm_retry_budget_seconds,
        base_url=settings.openrouter_base_url,
        data_collection=settings.llm_data_collection,
        zdr=settings.llm_zdr,
        reasoning_effort=settings.llm_reasoning_effort,
        app_url=settings.llm_app_url,
        app_title=settings.llm_app_title,
    )


def describe_llm_provider(provider: LLMProvider, settings: LLMSettings) -> str:
    """One line for the startup log: the configuration, and whether a key is set (never
    the key itself)."""
    if isinstance(provider, OpenRouterProvider):
        return (
            f"llm: openrouter model={provider.model} data_collection={provider.data_collection}"
            f" zdr={str(provider.zdr).lower()}"
            f" reasoning_effort={provider.reasoning_effort or 'default'}"
            f" key={'set' if settings.openrouter_api_key is not None else 'missing'}"
        )
    return f"llm: {type(provider).__name__}"
