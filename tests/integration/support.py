from pathlib import Path
from urllib.parse import urlsplit

from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parents[2]
PGVECTOR_IMAGE = "pgvector/pgvector:0.8.7-pg18-trixie"


def is_neon_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "neon.tech" or host.endswith(".neon.tech")


def with_database(url: str, name: str) -> str:
    """The same server URL, pointing at another database."""
    return urlsplit(url)._replace(path=f"/{name}").geturl()


def alembic_config(database_url: str) -> Config:
    config = Config(REPO_ROOT / "alembic.ini")
    config.attributes["database_url"] = database_url
    return config
