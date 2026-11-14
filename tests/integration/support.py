from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from alembic.config import Config

if TYPE_CHECKING:
    from uuid import UUID

    from psycopg_pool import ConnectionPool

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


# --- Conversation cases ------------------------------------------------------------

CASE_FACTS = {
    "what": "Merma del 4 % en el envasado",
    "where": "Línea 2, llenadora",
    "since": "Desde el lunes 9",
    "standard": "Merma máxima del 1,5 %",
}
# The tool calls that take a fresh case from `understand` to each later phase, in order.
ADVANCE_CALLS: list[tuple[str, dict[str, str]]] = [
    *[("record_field", {"field": k, "value": v}) for k, v in CASE_FACTS.items()],
    ("propose_transition", {"target_state": "challenge", "reasoning": "hechos completos"}),
    ("log_event", {"event_type": "evidence", "content": "El sensor de nivel marca 3 mm de más"}),
    ("propose_transition", {"target_state": "analyse", "reasoning": "hay evidencia"}),
    ("log_event", {"event_type": "validated_cause", "content": "Sensor descalibrado"}),
    ("propose_transition", {"target_state": "action", "reasoning": "causa validada"}),
]


def advance_case(pool: "ConnectionPool", problem_id: "UUID", phase: str) -> None:
    """Commit one turn that moves the case to `phase`, with the facts and annotations its
    exit criteria need (no model involved)."""
    from ayo_copilot.conversation.case import TurnChanges
    from ayo_copilot.conversation.store import TurnCommit, commit_turn, load_snapshot
    from ayo_copilot.conversation.tools import execute_tool
    from ayo_copilot.db.conversations import TraceRecord
    from ayo_copilot.llm.fake import tool_call

    snapshot = load_snapshot(pool, problem_id, message_limit=12)
    phase_before = snapshot.case.state
    changes = TurnChanges()
    for name, arguments in ADVANCE_CALLS:
        if snapshot.case.state == phase:
            break
        outcome = execute_tool(snapshot, changes, tool_call(name, arguments))
        if not outcome.ok and outcome.error_code == "tool_not_offered":
            continue  # a step of an earlier phase than the case's
        assert outcome.ok, outcome.result
    assert snapshot.case.state == phase
    commit_turn(
        pool,
        TurnCommit(
            snapshot=snapshot,
            phase_before=phase_before,
            user_message="Preparación del caso",
            reply="Hecho",
            changes=changes,
            trace=TraceRecord(prompts_version="draft-1", llm_calls=1, duration_ms=1),
        ),
    )
