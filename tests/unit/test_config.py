import pytest
from pydantic import ValidationError

from ayo_copilot.config import DatabaseSettings, Settings


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


NEON_URL = "postgresql://ayo:NEON-PASSWORD@ep-dev-123-pooler.eu-central-1.aws.neon.tech/ayo"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://ayo:ayo@localhost:5433/ayo",
        "postgresql://ayo:ayo@127.0.0.1:5433/ayo",
        "postgresql://ayo:ayo@[::1]:5433/ayo",
        "postgresql:///ayo",
    ],
)
def test_local_database_urls_are_accepted(url: str) -> None:
    assert make_settings(database_url=url).database_url.get_secret_value() == url


@pytest.mark.parametrize("field", ["database_url", "migrations_database_url"])
def test_remote_database_is_refused_by_default(field: str) -> None:
    with pytest.raises(ValidationError, match="ALLOW_REMOTE_DATABASE") as excinfo:
        make_settings(**{field: NEON_URL})

    assert "NEON-PASSWORD" not in str(excinfo.value)
    assert field.upper() in str(excinfo.value)


def test_remote_database_is_accepted_when_allowed() -> None:
    settings = make_settings(database_url=NEON_URL, allow_remote_database=True)

    assert settings.database_url.get_secret_value() == NEON_URL


def test_validation_errors_never_echo_secret_inputs() -> None:
    with pytest.raises(ValidationError) as excinfo:
        make_settings(database_url="postgresql://u:pw-SECRET@h/x", voyage_api_key=None)

    assert "pw-SECRET" not in str(excinfo.value)
    assert "test-admin-key" not in str(excinfo.value)


def test_migrations_use_their_own_url_when_set() -> None:
    direct = "postgresql://ayo:ayo@localhost:5434/ayo"

    assert make_settings().migrations_url() == make_settings().database_url.get_secret_value()
    assert make_settings(migrations_database_url=direct).migrations_url() == direct


def test_database_settings_alone_apply_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", NEON_URL)

    with pytest.raises(ValidationError, match="ALLOW_REMOTE_DATABASE"):
        DatabaseSettings(_env_file=None)

    monkeypatch.setenv("ALLOW_REMOTE_DATABASE", "true")
    assert DatabaseSettings(_env_file=None).migrations_url() == NEON_URL
