import hashlib
import math
import random
import struct
import time
from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

import httpx2

from ayo_copilot.config import Settings

# Voyage answers these with "retry after a brief wait"; other 4xx need a fixed request.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class EmbeddingError(Exception):
    """The provider could not embed the texts. The message never holds the key or the texts."""


@runtime_checkable
class Embedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic unit vectors derived from a hash of each text. No network; for tests."""

    def __init__(self, *, dimensions: int) -> None:
        self.dimensions = dimensions
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        # Expand the text's hash into enough bytes, two per component, mapped to [-1, 1].
        seed = text.encode()
        raw = b"".join(
            hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
            for i in range(math.ceil(self.dimensions * 2 / 32))
        )
        values = [
            v / 32767.5 - 1
            for v in struct.unpack(f">{self.dimensions}H", raw[: self.dimensions * 2])
        ]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]


class VoyageEmbedder:
    """Thin client for Voyage's `POST /embeddings`, with batching and retries."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        batch_size: int,
        max_retries: int,
        timeout_seconds: float = 30.0,
        base_url: str = "https://api.voyageai.com/v1",
        client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx2.Client(base_url=base_url, timeout=timeout_seconds)
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size]))
        return vectors

    def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        payload = {
            "input": list(texts),
            "model": self.model,
            "input_type": "document",
            "output_dimension": self.dimensions,
            "output_dtype": "float",
            # A chunk longer than the context is a chunker bug; fail instead of embedding a prefix.
            "truncation": False,
        }
        response = self._post_with_retries(payload)
        return self._parse(response, expected=len(texts))

    def _post_with_retries(self, payload: dict[str, object]) -> httpx2.Response:
        for attempt in range(self.max_retries + 1):
            is_last = attempt == self.max_retries
            try:
                response = self._client.post("/embeddings", json=payload, headers=self._headers)
            except httpx2.TransportError as exc:
                # The exception text is dropped: it can quote the request.
                if is_last:
                    raise EmbeddingError(
                        f"Embedding provider unreachable ({type(exc).__name__})"
                    ) from None
            else:
                if response.status_code == 200:
                    return response
                # The response body is dropped: a 4xx `detail` can echo the input.
                if is_last or response.status_code not in RETRYABLE_STATUS:
                    raise EmbeddingError(f"Embedding provider returned HTTP {response.status_code}")
            # Exponential backoff with full jitter: up to 1, 2, 4, ... seconds.
            self._sleep(random.uniform(0.1, 2.0**attempt))
        raise AssertionError("unreachable")

    def _parse(self, response: httpx2.Response, *, expected: int) -> list[list[float]]:
        try:
            items = response.json()["data"]
            by_index = {item["index"]: item["embedding"] for item in items}
            vectors = [by_index[i] for i in range(expected)]
        except (ValueError, KeyError, TypeError):
            raise EmbeddingError("Embedding provider returned a malformed response") from None
        if len(items) != expected or any(
            not isinstance(v, list) or len(v) != self.dimensions for v in vectors
        ):
            raise EmbeddingError("Embedding provider returned a malformed response")
        return vectors


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "fake":
        return FakeEmbedder(dimensions=settings.embedding_dimensions)
    assert settings.voyage_api_key is not None  # enforced by Settings
    return VoyageEmbedder(
        api_key=settings.voyage_api_key.get_secret_value(),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        max_retries=settings.embedding_max_retries,
        timeout_seconds=settings.embedding_timeout_seconds,
        base_url=settings.voyage_base_url,
    )
