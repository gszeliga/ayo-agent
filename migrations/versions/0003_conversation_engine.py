"""Conversation engine: cases (problems), their events, actions, channel links, turn traces.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12

Closed sets of values (phases, roles, event types, action status) are `text` columns with
named `CHECK` constraints, not native enums: adding or removing a value is dropping and
re-adding one constraint in an ordinary transaction, while `ALTER TYPE ... ADD VALUE` has
transaction restrictions and an enum value cannot be removed at all, which would make
downgrades awkward. The phase set will change as AYO's method is refined.

Constraints and indexes are named explicitly so later migrations can address them.
`gen_random_uuid()` is built into Postgres 13+, so no extension is needed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One case per problem being solved. The four facts are free text as the user said them
    # ("desde el lunes"); `where_` because `where` is reserved. `version` is bumped once per
    # committed turn: the turn engine's optimistic concurrency check.
    op.execute(
        """
        create table problems (
          id uuid primary key default gen_random_uuid(),
          tenant text not null,
          state text not null default 'understand',
          what text,
          where_ text,
          since text,
          standard text,
          created_by text,
          version int not null default 0,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          closed_at timestamptz,
          constraint problems_state_check
            check (state in ('understand','challenge','analyse','action','followup','closed'))
        )
        """
    )
    op.execute("create index problems_tenant_updated_at_idx on problems (tenant, updated_at desc)")

    # Conversation messages (`message`) and the model's annotations (the other types, always
    # role `assistant`). The identity id gives a deterministic order within a case.
    op.execute(
        """
        create table problem_events (
          id bigint generated always as identity primary key,
          problem_id uuid not null references problems(id) on delete cascade,
          role text not null,
          content text not null,
          event_type text not null default 'message',
          state_at_time text not null,
          created_at timestamptz not null default now(),
          constraint problem_events_role_check check (role in ('user','assistant')),
          constraint problem_events_event_type_check
            check (event_type in
              ('message','evidence','hypothesis','hypothesis_discarded','validated_cause'))
        )
        """
    )
    op.execute("create index problem_events_problem_id_id_idx on problem_events (problem_id, id)")
    op.execute(
        "create index problem_events_problem_id_event_type_idx"
        " on problem_events (problem_id, event_type)"
    )

    # "Overdue" (pending and past `due_date`) is computed, never stored.
    op.execute(
        """
        create table actions (
          id bigint generated always as identity primary key,
          problem_id uuid not null references problems(id) on delete cascade,
          description text not null,
          owner text not null,
          due_date date not null,
          status text not null default 'pending',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint actions_status_check check (status in ('pending','done'))
        )
        """
    )
    op.execute("create index actions_problem_id_idx on actions (problem_id)")

    # Maps a channel's conversation ('web' now; Slack, Google Chat later) to a case. The
    # unique key also serves the lookup, so it needs no separate index.
    op.execute(
        """
        create table conversation_links (
          id uuid primary key default gen_random_uuid(),
          problem_id uuid not null references problems(id) on delete cascade,
          channel_type text not null,
          external_channel_id text not null,
          external_thread_id text not null,
          created_at timestamptz not null default now(),
          constraint conversation_links_channel_thread_key
            unique (channel_type, external_channel_id, external_thread_id)
        )
        """
    )

    # One row per committed turn, content-free: ids, phases, counts, tokens, tool names and
    # validity, retrieved chunk ids and similarities. Never messages, arguments or text.
    op.execute(
        """
        create table turn_traces (
          id bigint generated always as identity primary key,
          problem_id uuid not null references problems(id) on delete cascade,
          turn_no int not null,
          phase_before text not null,
          phase_after text not null,
          model text,
          prompts_version text not null,
          llm_calls int not null,
          prompt_tokens int,
          completion_tokens int,
          total_tokens int,
          cost numeric,
          tool_calls jsonb not null default '[]',
          retrieved jsonb not null default '[]',
          retrieval_error text,
          capped boolean not null default false,
          duration_ms int not null,
          created_at timestamptz not null default now(),
          constraint turn_traces_problem_id_turn_no_key unique (problem_id, turn_no)
        )
        """
    )


def downgrade() -> None:
    op.execute("drop table turn_traces")
    op.execute("drop table conversation_links")
    op.execute("drop table actions")
    op.execute("drop table problem_events")
    op.execute("drop table problems")
