import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ayo_copilot.config import (
    ENV_FILE_VARIABLE,
    DatabaseSettings,
    LLMSettings,
    Settings,
    default_env_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    assert settings.cors_allowed_origins == []
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


# --- where settings come from ---


def test_env_file_is_at_the_project_root_whatever_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_FILE_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)

    assert default_env_file() == PROJECT_ROOT / ".env"
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_env_file_can_be_overridden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_FILE_VARIABLE, str(tmp_path / "other.env"))

    assert default_env_file() == tmp_path / "other.env"


def test_settings_are_read_from_an_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("CHUNK_SIZE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_API_KEY=from-file\nCHUNK_SIZE=600\nEMBEDDING_PROVIDER=fake\n")

    settings = Settings(_env_file=env_file)

    assert settings.admin_api_key.get_secret_value() == "from-file"
    assert settings.chunk_size == 600


def test_environment_wins_over_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHUNK_SIZE", "700")
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_API_KEY=k\nCHUNK_SIZE=600\nEMBEDDING_PROVIDER=fake\n")

    assert Settings(_env_file=env_file).chunk_size == 700


# --- empty values count as unset ---


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"ADMIN_API_KEY": "", "EMBEDDING_PROVIDER": "fake"}, "admin_api_key"),
        ({"ADMIN_API_KEY": "k", "VOYAGE_API_KEY": ""}, "VOYAGE_API_KEY is required"),
    ],
    ids=["admin", "voyage"],
)
def test_empty_environment_values_count_as_unset(
    monkeypatch: pytest.MonkeyPatch, variables: dict[str, str], message: str
) -> None:
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("ADMIN_API_KEY=\nEMBEDDING_PROVIDER=fake\n", "admin_api_key"),
        ("ADMIN_API_KEY=k\nVOYAGE_API_KEY=\n", "VOYAGE_API_KEY is required"),
    ],
    ids=["admin", "voyage"],
)
def test_empty_env_file_values_count_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str, message: str
) -> None:
    for name in ("ADMIN_API_KEY", "VOYAGE_API_KEY", "EMBEDDING_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(content)

    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=env_file)


@pytest.mark.parametrize("field", ["admin_api_key", "voyage_api_key", "openrouter_api_key"])
def test_empty_secrets_are_refused(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        make_settings(**{field: ""})


def test_empty_database_url_falls_back_to_the_local_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")

    settings = make_settings()

    assert "localhost:5433" in settings.database_url.get_secret_value()


def test_cors_origins_are_comma_separated_trimmed_and_lowercased(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " http://localhost:5173 ,HTTPS://Admin.Example.com,")

    settings = make_settings()

    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "https://admin.example.com",
    ]


def test_empty_cors_origins_mean_cors_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")

    assert make_settings().cors_allowed_origins == []


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://localhost:5173/",
        "https://admin.example.com/ui",
        "ftp://admin.example.com",
        "admin.example.com",
        "http://",
        "http://user@admin.example.com",
        "http://admin.example.com?x=1",
        "http://admin.example.com:port",
    ],
)
def test_malformed_cors_origins_are_refused(origin: str) -> None:
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        make_settings(cors_allowed_origins=f"http://localhost:5173,{origin}")


def test_llm_defaults() -> None:
    settings = make_settings()

    assert settings.llm_provider == "openrouter"
    assert settings.openrouter_api_key is None
    assert settings.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert settings.llm_model == "mistralai/mistral-small-3.2-24b-instruct"
    assert settings.llm_temperature == 0.2
    assert settings.llm_max_tokens == 1024
    assert settings.llm_timeout_seconds == 60
    assert settings.llm_max_retries == 2
    assert settings.llm_retry_budget_seconds == 90
    assert settings.llm_data_collection == "deny"
    assert settings.llm_zdr is False
    assert settings.llm_reasoning_effort is None
    assert settings.llm_app_url is None
    assert settings.llm_app_title is None


def test_llm_settings_load_without_admin_key_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-from-env")
    monkeypatch.setenv("LLM_MODEL", "qwen/qwen3-32b")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    monkeypatch.setenv("LLM_ZDR", "true")

    settings = LLMSettings(_env_file=None)

    assert settings.openrouter_api_key is not None
    assert settings.openrouter_api_key.get_secret_value() == "sk-or-from-env"
    assert settings.llm_model == "qwen/qwen3-32b"
    assert settings.llm_reasoning_effort == "none"
    assert settings.llm_zdr is True


def test_openrouter_key_is_not_shown_in_repr() -> None:
    settings = make_settings(openrouter_api_key="sk-or-secret-value")

    assert "sk-or-secret-value" not in repr(settings)
    assert "sk-or-secret-value" not in str(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_provider", "openai"),
        ("llm_model", ""),
        ("llm_temperature", -0.1),
        ("llm_temperature", 2.1),
        ("llm_max_tokens", 0),
        ("llm_timeout_seconds", 0),
        ("llm_max_retries", -1),
        ("llm_retry_budget_seconds", 0),
        ("llm_data_collection", "maybe"),
        ("llm_reasoning_effort", "extreme"),
    ],
)
def test_invalid_llm_settings_are_refused(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        make_settings(**{field: value})


def _env_example_names() -> set[str]:
    """Variable names assigned in .env.example, commented-out ones included."""
    text = (PROJECT_ROOT / ".env.example").read_text()
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))


def test_env_example_lists_every_setting_and_nothing_else() -> None:
    fields = {name.upper() for name in Settings.model_fields}

    assert _env_example_names() == fields


# --- Conversation engine settings ----------------------------------------------


def test_conversation_defaults() -> None:
    settings = make_settings()

    assert settings.retrieval_phases == ["analyse"]
    assert settings.retrieval_top_k == 5
    assert settings.retrieval_min_similarity is None
    assert settings.common_tenant == "ayo"
    assert settings.context_max_messages == 12
    assert settings.max_tool_rounds == 6
    assert settings.max_phase_hops == 1
    assert settings.turn_timeout_seconds == 90
    assert settings.max_user_message_chars == 4000
    assert settings.field_max_chars == 500
    assert settings.prompts_version == "draft-1"
    assert settings.app_timezone == "Europe/Madrid"
    assert str(settings.timezone()) == "Europe/Madrid"
    assert settings.llm_model_by_phase == {}


def test_conversation_settings_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_PHASES", " analyse, challenge ,,analyse")
    monkeypatch.setenv("RETRIEVAL_MIN_SIMILARITY", "0.4")
    monkeypatch.setenv("LLM_MODEL_BY_PHASE", '{"analyse": " vendor/big-model "}')
    monkeypatch.setenv("APP_TIMEZONE", "America/Mexico_City")
    monkeypatch.setenv("MAX_PHASE_HOPS", "0")

    settings = make_settings()

    assert settings.retrieval_phases == ["analyse", "challenge"]
    assert settings.retrieval_min_similarity == 0.4
    assert settings.llm_model_by_phase == {"analyse": "vendor/big-model"}
    assert settings.app_timezone == "America/Mexico_City"
    assert settings.max_phase_hops == 0


def test_empty_retrieval_phases_mean_no_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_PHASES", " , ")
    assert make_settings().retrieval_phases == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"retrieval_phases": "closed"}, "RETRIEVAL_PHASES: 'closed'"),
        ({"retrieval_phases": "analyse,analysis"}, "RETRIEVAL_PHASES: 'analysis'"),
        ({"retrieval_top_k": 0}, "retrieval_top_k"),
        ({"retrieval_top_k": 51}, "retrieval_top_k"),
        ({"retrieval_min_similarity": 1.5}, "retrieval_min_similarity"),
        ({"retrieval_min_similarity": -0.1}, "retrieval_min_similarity"),
        ({"common_tenant": "AYO"}, "COMMON_TENANT"),
        ({"context_max_messages": 0}, "context_max_messages"),
        ({"max_tool_rounds": 0}, "max_tool_rounds"),
        ({"max_phase_hops": -1}, "max_phase_hops"),
        ({"turn_timeout_seconds": 0}, "turn_timeout_seconds"),
        ({"max_user_message_chars": 0}, "max_user_message_chars"),
        ({"field_max_chars": 0}, "field_max_chars"),
        ({"prompts_version": ""}, "prompts_version"),
        ({"prompts_version": "draft 2"}, "prompts_version"),
        ({"prompts_version": "v" * 65}, "prompts_version"),
        ({"app_timezone": "Europe/Atlantis"}, "APP_TIMEZONE: 'Europe/Atlantis'"),
        ({"app_timezone": "../etc/passwd"}, "APP_TIMEZONE"),
        ({"llm_model_by_phase": {"closed": "m"}}, "LLM_MODEL_BY_PHASE: 'closed'"),
        ({"llm_model_by_phase": {"analyse": " "}}, "the model for 'analyse' is empty"),
    ],
)
def test_invalid_conversation_settings_are_refused(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        make_settings(**overrides)


def test_llm_model_by_phase_must_be_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_BY_PHASE", "analyse=vendor/model")
    with pytest.raises(Exception, match="llm_model_by_phase"):
        make_settings()
