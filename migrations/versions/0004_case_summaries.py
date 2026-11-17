"""Case summaries: the AI summary of a case, one per case, regenerated on request.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17

A table of its own, not columns on `problems`: writing a summary must never bump the case's
`version` (the turn engine's concurrency check) or its `updated_at` (the listing's order).
`source_version` is the case version the summary was generated from; the API reports the
summary as stale once the case has moved on.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `content` is customer content (a narrative of the case). Tokens and cost are kept for
    # cost tracking; `created_at` is when the summary was generated.
    op.execute(
        """
        create table case_summaries (
          problem_id uuid primary key references problems(id) on delete cascade,
          content text not null,
          source_version int not null,
          model text not null,
          prompts_version text not null,
          total_tokens int,
          cost numeric(12, 6),
          created_at timestamptz not null default now(),
          constraint case_summaries_source_version_check check (source_version >= 0)
        )
        """
    )


def downgrade() -> None:
    op.execute("drop table case_summaries")
