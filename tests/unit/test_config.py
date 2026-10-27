from pathlib import Path

import pytest
from pydantic import ValidationError

from ayo_copilot.config import Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "admin_api_key": "test-admin-key",
        "voyage_api_key": "test-voyage-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_defaults() -> None:
    settings = make_settings()

    assert settings.chunk_size == 800
    assert settings.chunk_overlap == 80
    assert settings.min_chunk_size == 100
    assert settings.embedding_model == "voyage-4"
    assert settings.embedding_dimensions == 1024
    assert settings.embedding_provider == "voyage"
    assert settings.docs_enabled is True
    assert settings.knowledge_dir == Path("data/knowledge")
    assert "localhost:5433" in settings.database_url.get_secret_value()


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", "from-env")
    monkeypatch.setenv("CHUNK_SIZE", "500")
    monkeypatch.setenv("DOCS_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")

    settings = Settings(_env_file=None)

    assert settings.admin_api_key.get_secret_value() == "from-env"
    assert settings.chunk_size == 500
    assert settings.docs_enabled is False


def test_admin_api_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="admin_api_key"):
        Settings(_env_file=None)


def test_secrets_are_not_shown_in_repr() -> None:
    settings = make_settings(voyage_api_key="pa-secret-value")

    assert "pa-secret-value" not in repr(settings)
    assert "test-admin-key" not in repr(settings)


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap"):
        make_settings(chunk_size=100, chunk_overlap=100)


def test_dimensions_must_fit_hnsw_limit() -> None:
    with pytest.raises(ValidationError):
        make_settings(embedding_dimensions=2048)


def test_batch_size_must_fit_voyage_limit() -> None:
    assert make_settings(embedding_batch_size=1000).embedding_batch_size == 1000
    with pytest.raises(ValidationError):
        make_settings(embedding_batch_size=1001)


def test_voyage_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="VOYAGE_API_KEY"):
        make_settings(embedding_provider="voyage", voyage_api_key=None)


def test_fake_provider_needs_no_api_key() -> None:
    settings = make_settings(embedding_provider="fake", voyage_api_key=None)

    assert settings.voyage_api_key is None


def test_db_log_level_defaults_to_warning_and_rejects_unknown_levels() -> None:
    assert make_settings().db_log_level == "WARNING"
    assert make_settings(db_log_level="DEBUG").db_log_level == "DEBUG"
    with pytest.raises(ValidationError):
        make_settings(db_log_level="LOUD")
