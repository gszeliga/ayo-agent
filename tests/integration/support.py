from collections.abc import Sequence
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


DIMENSIONS = 1024


def axis_vector(*weights: tuple[int, float], dimensions: int = DIMENSIONS) -> list[float]:
    """A vector with the given (axis, weight) components and zeros elsewhere: lets a test
    place chunks at known cosine similarities (same axes: 1, disjoint axes: 0)."""
    vector = [0.0] * dimensions
    for axis, weight in weights:
        vector[axis] += weight
    return vector


class ScriptedEmbedder:
    """Answers each query with the vector scripted for it; records queries and documents."""

    def __init__(self, queries: dict[str, list[float]]) -> None:
        self.queries = queries
        self.query_calls: list[str] = []
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        raise AssertionError("a search never embeds documents")

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self.queries[text]
