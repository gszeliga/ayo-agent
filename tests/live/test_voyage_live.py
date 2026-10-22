import pytest
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ayo_copilot.ingestion.embedding import VoyageEmbedder

pytestmark = pytest.mark.live


class _VoyageKey(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    voyage_api_key: SecretStr | None = None


def test_real_voyage_request() -> None:
    key = _VoyageKey().voyage_api_key
    if key is None:
        pytest.skip("VOYAGE_API_KEY is not set (environment or .env)")
    embedder = VoyageEmbedder(
        api_key=key.get_secret_value(),
        model="voyage-4",
        dimensions=1024,
        batch_size=128,
        max_retries=2,
    )
    try:
        vectors = embedder.embed_documents(["Control de sellado", "Revisar la presión"])
    finally:
        embedder.close()

    assert [len(v) for v in vectors] == [1024, 1024]
    assert vectors[0] != vectors[1]
