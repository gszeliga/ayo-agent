from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# pgvector cannot build an HNSW index on a `vector` column wider than this.
HNSW_MAX_DIMENSIONS = 2000
# Voyage accepts at most this many texts per embeddings request.
VOYAGE_MAX_BATCH_SIZE = 1000
# A database on any other host needs ALLOW_REMOTE_DATABASE=true.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def database_host(url: str) -> str | None:
    """The host of a database URL; None for a Unix socket (no host in the URL)."""
    return urlsplit(url).hostname


class DatabaseSettings(BaseSettings):
    """The database settings alone, for tools such as Alembic that need nothing else."""

    # Validation errors would otherwise echo the raw input, URLs with passwords included.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

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


class Settings(DatabaseSettings):
    """Application settings, read from environment variables (and `.env`)."""

    # Provisional admin authentication (see routers/admin.py).
    admin_api_key: SecretStr

    knowledge_dir: Path = Path("data/knowledge")
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    docs_enabled: bool = True

    # Chunk sizes are measured in characters, not tokens.
    chunk_size: int = Field(default=800, gt=0)
    chunk_overlap: int = Field(default=80, ge=0)
    # Starting value to tune, not a validated number.
    min_chunk_size: int = Field(default=100, ge=0)

    embedding_provider: Literal["voyage", "fake"] = "voyage"
    embedding_model: str = "voyage-4"
    embedding_dimensions: int = Field(default=1024, gt=0, le=HNSW_MAX_DIMENSIONS)
    voyage_api_key: SecretStr | None = None
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
