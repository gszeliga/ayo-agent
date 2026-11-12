"""OpenRouter's public models listing: tool support, context length, prices and ZDR.

`GET /models` and `GET /models?zdr=true` (the models with a Zero Data Retention endpoint).
The listing is public, so no key is sent. Prices are USD per token, as strings, for the
model's listed (default) endpoint; the endpoint actually used may differ, so costs computed
from them are approximate.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx2

from ayo_copilot.llm.check.runner import Pricing

CATALOG_TIMEOUT_SECONDS = 30.0


class CatalogError(Exception):
    """The models listing could not be read. The message holds no response body."""


@dataclass(frozen=True)
class ModelInfo:
    id: str
    tools: bool
    context_length: int | None
    prompt_price: float | None  # USD per token
    completion_price: float | None
    zdr: bool  # has at least one Zero Data Retention endpoint
    # "-" (no reasoning metadata), "optional", "default on" or "mandatory".
    reasoning: str

    @property
    def pricing(self) -> Pricing | None:
        if self.prompt_price is None or self.completion_price is None:
            return None
        return Pricing(prompt=self.prompt_price, completion=self.completion_price)


def fetch_catalog(client: httpx2.Client) -> dict[str, ModelInfo]:
    """Every listed model by id. `client` has the OpenRouter base URL."""
    zdr_ids = {model["id"] for model in _get_models(client, zdr=True)}
    return {
        model["id"]: _model_info(model, zdr=model["id"] in zdr_ids)
        for model in _get_models(client, zdr=False)
    }


def catalog_client(base_url: str) -> httpx2.Client:
    return httpx2.Client(base_url=base_url, timeout=CATALOG_TIMEOUT_SECONDS)


def _get_models(client: httpx2.Client, *, zdr: bool) -> list[dict[str, Any]]:
    params = {"zdr": "true"} if zdr else None
    try:
        response = client.get("/models", params=params)
    except httpx2.TransportError as exc:
        name = type(exc).__name__
        raise CatalogError(f"OpenRouter models listing unreachable ({name})") from None
    if response.status_code != 200:
        raise CatalogError(f"OpenRouter models listing returned HTTP {response.status_code}")
    try:
        data = response.json()["data"]
    except (ValueError, KeyError, TypeError):
        raise CatalogError("OpenRouter models listing is malformed") from None
    if not isinstance(data, list):
        raise CatalogError("OpenRouter models listing is malformed")
    return [m for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]


def _price(pricing: object, key: str) -> float | None:
    value = pricing.get(key) if isinstance(pricing, Mapping) else None
    try:
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def _reasoning(raw: object) -> str:
    if not isinstance(raw, Mapping):
        return "-"
    if raw.get("mandatory") is True:
        return "mandatory"
    if raw.get("default_enabled") is True:
        return "default on"
    return "optional"


def _model_info(model: Mapping[str, Any], *, zdr: bool) -> ModelInfo:
    parameters = model.get("supported_parameters")
    context = model.get("context_length")
    return ModelInfo(
        id=model["id"],
        tools=isinstance(parameters, list) and "tools" in parameters,
        context_length=context if type(context) is int else None,
        prompt_price=_price(model.get("pricing"), "prompt"),
        completion_price=_price(model.get("pricing"), "completion"),
        zdr=zdr,
        reasoning=_reasoning(model.get("reasoning")),
    )
