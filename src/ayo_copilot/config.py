import os
import re
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ayo_copilot.conversation.case import PHASES
from ayo_copilot.ingestion.storage import TENANT_PATTERN

# pgvector cannot build an HNSW index on a `vector` column wider than this.
HNSW_MAX_DIMENSIONS = 2000
# Voyage accepts at most this many texts per embeddings request.
VOYAGE_MAX_BATCH_SIZE = 1000
# A database on any other host needs ALLOW_REMOTE_DATABASE=true.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Most chunks one search returns (POST /admin/search and the engine's retrieval).
MAX_SEARCH_TOP_K = 50


# Set in the environment to read settings from another file than the project's `.env`.
ENV_FILE_VARIABLE = "AYO_ENV_FILE"


def default_env_file() -> Path:
    """`AYO_ENV_FILE` if set, else `.env` at the project root, whatever the working directory.

    Installed as a package there is no project root, so the path points nowhere and only
    real environment variables apply (a missing file is skipped).
    """
    override = os.environ.get(ENV_FILE_VARIABLE)
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / ".env"


def database_host(url: str) -> str | None:
    """The host of a database URL; None for a Unix socket (no host in the URL)."""
    return urlsplit(url).hostname


# Validation errors would otherwise echo the raw input, URLs with passwords included.
# Empty values (`VOYAGE_API_KEY=`) count as unset, so a required one fails at startup.
SETTINGS_CONFIG = SettingsConfigDict(
    env_file=default_env_file(),
    env_file_encoding="utf-8",
    env_ignore_empty=True,
    extra="ignore",
    hide_input_in_errors=True,
)


def normalize_origin(origin: str) -> str:
    """`scheme://host[:port]` with scheme and host lowercased, as browsers send `Origin`.
    Raises ValueError for anything else, `*` included."""
    try:
        parts = urlsplit(origin)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        parts = None
    if (
        parts is None
        or parts.scheme.lower() not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.path
        or parts.query
        or parts.fragment
        or origin.endswith(("?", "#"))
    ):
        raise ValueError(
            f"CORS_ALLOWED_ORIGINS: {origin!r} is not an origin like https://host[:port]"
            " (no path, no trailing slash, no *)"
        )
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


class BuildSettings(BaseSettings):
    """Read when the app is built, before the rest: FastAPI needs the docs URLs and the
    middleware up front."""

    model_config = SETTINGS_CONFIG

    # Serve /docs, /redoc and /openapi.json. They are public when on: restricting who can
    # reach them is left to the infrastructure (proxy or private network).
    docs_enabled: bool = True
    # Browser origins allowed to call the API (comma-separated in the environment). Empty
    # means CORS is off: browsers on other origins can't read the answers.
    cors_allowed_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _check_origins(cls, origins: list[str]) -> list[str]:
        return [normalize_origin(origin) for origin in origins]


class DatabaseSettings(BaseSettings):
    """The database settings alone, for tools such as Alembic that need nothing else."""

    model_config = SETTINGS_CONFIG

    # Defaults to the local dev database started by scripts/dev_db.sh, never production.
    database_url: SecretStr = SecretStr("postgresql://ayo:ayo@localhost:5433/ayo")
    # Alembic uses this when set (e.g. Neon's direct endpoint, since the pooled one runs
    # PgBouncer); otherwise DATABASE_URL.
    migrations_database_url: SecretStr | None = None
    # Guard against pointing a dev run at a remote database by accident.
    allow_remote_database: bool = False
    # Level of the `psycopg` logger (pool events at INFO, connection attempts at DEBUG).
    db_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "WARNING"

    @model_validator(mode="after")
    def _refuse_remote_database(self) -> Self:
        if self.allow_remote_database:
            return self
        for name, url in (
            ("DATABASE_URL", self.database_url),
            ("MIGRATIONS_DATABASE_URL", self.migrations_database_url),
        ):
            host = database_host(url.get_secret_value()) if url else None
            if host is not None and host.lower() not in LOCAL_HOSTS:
                raise ValueError(
                    f"{name} points at the remote host {host!r};"
                    " set ALLOW_REMOTE_DATABASE=true to use it"
                )
        return self

    def migrations_url(self) -> str:
        url = self.migrations_database_url or self.database_url
        return url.get_secret_value()


ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


class LLMSettings(BaseSettings):
    """The language model settings alone, for tools such as `ayo-llm-check` that need no
    database or admin key. Nothing here is required at startup: a missing API key only
    fails when the model is actually called."""

    model_config = SETTINGS_CONFIG

    llm_provider: Literal["openrouter"] = "openrouter"
    openrouter_api_key: SecretStr | None = Field(default=None, min_length=1)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default model; each call can override it.
    llm_model: str = Field(default="mistralai/mistral-small-3.2-24b-instruct", min_length=1)
    # Always sent: upstream providers' own defaults differ (OpenRouter documents 1.0).
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    # Reasoning tokens count against this limit too.
    llm_max_tokens: int = Field(default=1024, gt=0)
    # Read timeout per request; the connect timeout is fixed (see the provider).
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    # No new attempt starts once this much time has passed since the first one.
    llm_retry_budget_seconds: float = Field(default=90.0, gt=0)
    # OpenRouter routing: "deny" uses only upstream providers that do not store prompts or
    # train on them; prompts will hold customer content.
    llm_data_collection: Literal["allow", "deny"] = "deny"
    # OpenRouter routing: only Zero Data Retention endpoints (stricter, fewer providers).
    llm_zdr: bool = False
    # Unset: the model's own default. "none" turns reasoning off where the model allows it.
    llm_reasoning_effort: ReasoningEffort | None = None
    # Optional OpenRouter attribution headers (HTTP-Referer, X-OpenRouter-Title).
    llm_app_url: str | None = None
    llm_app_title: str | None = None


# The phases that can retrieve or have their own model: every phase but `closed`.
ACTIVE_PHASES = tuple(phase for phase in PHASES if phase != "closed")


class ConversationSettings(BaseSettings):
    """The conversation engine's settings. All have defaults: none is required."""

    model_config = SETTINGS_CONFIG

    # Phases whose turns search the knowledge base (comma-separated); empty: none.
    retrieval_phases: Annotated[list[str], NoDecode] = ["analyse"]
    retrieval_top_k: int = Field(default=5, ge=1, le=MAX_SEARCH_TOP_K)
    # Unset keeps every result: no validated threshold yet.
    retrieval_min_similarity: float | None = Field(default=None, ge=0, le=1)
    # Searched with the case's own tenant: the shared knowledge (AYO's method).
    common_tenant: str = "ayo"
    # Messages of the current phase sent to the model, at most.
    context_max_messages: int = Field(default=12, ge=1)
    # Model calls per turn, at most.
    max_tool_rounds: int = Field(default=6, ge=1)
    # Accepted phase changes per turn; 0: the phase only changes between messages.
    max_phase_hops: int = Field(default=1, ge=0)
    # Checked between model calls; a call in flight has the provider's own timeouts.
    turn_timeout_seconds: float = Field(default=90.0, gt=0)
    max_user_message_chars: int = Field(default=4000, ge=1)
    # Each case fact is cut to this length when shown to the model.
    field_max_chars: int = Field(default=500, ge=1)
    # Recorded in every turn trace; bump it when the prompt files change.
    prompts_version: str = Field(default="draft-1", min_length=1, max_length=64, pattern=r"^\S+$")
    # Today's date for the model ("el viernes") is taken in this time zone.
    app_timezone: str = "Europe/Madrid"
    # JSON, e.g. {"analyse": "<model id>"}; a phase without an entry uses LLM_MODEL.
    llm_model_by_phase: dict[str, str] = {}

    @field_validator("retrieval_phases", mode="before")
    @classmethod
    def _split_phases(cls, value: object) -> object:
        if isinstance(value, str):
            return [phase.strip() for phase in value.split(",") if phase.strip()]
        return value

    @field_validator("retrieval_phases")
    @classmethod
    def _check_phases(cls, phases: list[str]) -> list[str]:
        for phase in phases:
            _check_active_phase("RETRIEVAL_PHASES", phase)
        return list(dict.fromkeys(phases))

    @field_validator("common_tenant")
    @classmethod
    def _check_common_tenant(cls, tenant: str) -> str:
        if not re.fullmatch(TENANT_PATTERN, tenant):
            raise ValueError(f"COMMON_TENANT must match {TENANT_PATTERN}")
        return tenant

    @field_validator("app_timezone")
    @classmethod
    def _check_timezone(cls, name: str) -> str:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"APP_TIMEZONE: {name!r} is not a known time zone (e.g. Europe/Madrid)"
            ) from None
        return name

    @field_validator("llm_model_by_phase")
    @classmethod
    def _check_models_by_phase(cls, mapping: dict[str, str]) -> dict[str, str]:
        for phase, model in mapping.items():
            _check_active_phase("LLM_MODEL_BY_PHASE", phase)
            if not model.strip():
                raise ValueError(f"LLM_MODEL_BY_PHASE: the model for {phase!r} is empty")
        return {phase: model.strip() for phase, model in mapping.items()}

    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


def _check_active_phase(setting: str, phase: str) -> None:
    if phase not in ACTIVE_PHASES:
        raise ValueError(f"{setting}: {phase!r} is not one of {', '.join(ACTIVE_PHASES)}")


class Settings(ConversationSettings, LLMSettings, DatabaseSettings, BuildSettings):
    """Application settings, read from environment variables (and `.env`)."""

    # Provisional admin authentication (see routers/admin.py).
    admin_api_key: SecretStr = Field(min_length=1)

    max_upload_bytes: int = Field(default=5 * 1024 * 1024, gt=0)

    # Chunk sizes are measured in characters, not tokens.
    chunk_size: int = Field(default=800, gt=0)
    chunk_overlap: int = Field(default=80, ge=0)
    # Starting value to tune, not a validated number.
    min_chunk_size: int = Field(default=100, ge=0)

    embedding_provider: Literal["voyage", "fake"] = "voyage"
    embedding_model: str = "voyage-4"
    embedding_dimensions: int = Field(default=1024, gt=0, le=HNSW_MAX_DIMENSIONS)
    voyage_api_key: SecretStr | None = Field(default=None, min_length=1)
    voyage_base_url: str = "https://api.voyageai.com/v1"
    embedding_batch_size: int = Field(default=128, gt=0, le=VOYAGE_MAX_BATCH_SIZE)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_max_retries: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.embedding_provider == "voyage" and self.voyage_api_key is None:
            raise ValueError("VOYAGE_API_KEY is required when EMBEDDING_PROVIDER=voyage")
        return self
