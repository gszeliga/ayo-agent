import logging
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from ayo_copilot.db.schema import SCHEMA_REVISIONS, describe_schema

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_revisions_match_the_alembic_chain() -> None:
    # Reads migrations/ only: no database. Fails when a migration is not listed.
    script = ScriptDirectory.from_config(Config(REPO_ROOT / "alembic.ini"))
    chain = [revision.revision for revision in script.walk_revisions()]

    assert script.get_heads() == [SCHEMA_REVISIONS[-1]]
    assert tuple(reversed(chain)) == SCHEMA_REVISIONS


def test_the_head_is_current() -> None:
    level, message = describe_schema(SCHEMA_REVISIONS[-1])

    assert level == logging.INFO
    assert message == f"database schema: revision {SCHEMA_REVISIONS[-1]} (current)"


@pytest.mark.parametrize("revision", SCHEMA_REVISIONS[:-1])
def test_an_older_revision_is_outdated(revision: str) -> None:
    level, message = describe_schema(revision)

    assert level == logging.WARNING
    assert message == (
        f"database schema: revision {revision}, outdated (code expects {SCHEMA_REVISIONS[-1]}):"
        " run `uv run alembic upgrade head`"
    )


@pytest.mark.parametrize("revision", ["9999", "0003+0004", "abc123"])
def test_an_unlisted_revision_is_unknown(revision: str) -> None:
    level, message = describe_schema(revision)

    assert level == logging.WARNING
    assert message.startswith(f"database schema: revision {revision} unknown to this code")
    assert f"expects {SCHEMA_REVISIONS[-1]}" in message
    assert "newer than the code" in message


def test_no_revision_says_to_migrate() -> None:
    level, message = describe_schema(None)

    assert level == logging.WARNING
    assert "no Alembic revision recorded" in message
    assert "alembic upgrade head" in message
