"""The conversation engine's storage: resolve a case from a channel, load its snapshot,
commit a turn, read a session. This module owns the transactions; the SQL lives in
`db/conversations.py`.

No transaction stays open between these calls: the engine loads, then calls the model and
the search with no connection held, then commits. The commit checks the version read at
load time (optimistic concurrency), so a concurrent turn on the same case makes it fail
with `CaseChanged` and write nothing.
"""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from psycopg import Rollback
from psycopg_pool import ConnectionPool

from ayo_copilot.conversation.case import (
    FIELDS,
    Action,
    CaseSnapshot,
    Event,
    FieldName,
    Phase,
    TurnChanges,
)
from ayo_copilot.db import conversations as db
from ayo_copilot.db.conversations import TraceRecord


class CaseTenantMismatch(Exception):
    """The conversation belongs to a case of another tenant."""


class CaseChanged(Exception):
    """The case was committed by another turn since this one loaded it."""


class CaseNotFound(Exception):
    """No case with this id."""


@dataclass(frozen=True)
class ChannelKey:
    """What identifies a conversation in a channel (the `conversation_links` key)."""

    channel_type: str
    external_channel_id: str
    external_thread_id: str


@dataclass(frozen=True)
class ResolvedCase:
    problem_id: UUID
    created: bool


@dataclass(frozen=True)
class TurnCommit:
    """Everything a turn writes. `snapshot` is the case as the turn left it (state and
    facts); its `version` is still the one read at load, which the commit checks."""

    snapshot: CaseSnapshot
    phase_before: Phase
    user_message: str = field(repr=False)
    reply: str = field(repr=False)
    changes: TurnChanges
    trace: TraceRecord


@dataclass(frozen=True)
class CommittedTurn:
    version: int
    turn_no: int


@dataclass(frozen=True)
class SessionAction:
    action: Action
    overdue: bool


@dataclass(frozen=True)
class SessionView:
    """A case as the session endpoint shows it: no prompts, traces or retrieved text."""

    problem_id: UUID
    tenant: str
    phase: Phase
    version: int
    turns: int
    fields: dict[FieldName, str | None] = field(repr=False)
    events: list[Event]
    actions: list[SessionAction]
    messages: list[Event]


def resolve_case(
    pool: ConnectionPool, key: ChannelKey, *, tenant: str, created_by: str | None
) -> ResolvedCase:
    """The case linked to `key`, created with its link if there is none.

    Race-safe: when two first messages of the same conversation arrive together, the
    loser's problem row is rolled back (savepoint) and it gets the winner's case. A case
    of another tenant raises `CaseTenantMismatch` and nothing is created.
    """
    args = (key.channel_type, key.external_channel_id, key.external_thread_id)
    created = False
    with pool.connection() as conn, conn.transaction():
        linked = db.find_link(conn, *args)
        if linked is None:
            with conn.transaction() as savepoint:
                problem_id = db.insert_problem(conn, tenant, created_by)
                if db.insert_link(conn, problem_id, *args):
                    created = True
                else:
                    raise Rollback(savepoint)
            linked = (
                db.LinkedCase(problem_id=problem_id, tenant=tenant)
                if created
                else db.find_link(conn, *args)
            )
        assert linked is not None
    if linked.tenant != tenant:
        raise CaseTenantMismatch
    return ResolvedCase(problem_id=linked.problem_id, created=created)


def load_snapshot(pool: ConnectionPool, problem_id: UUID, *, message_limit: int) -> CaseSnapshot:
    """The case, every annotation, the last `message_limit + 1` messages (the extra one
    lets the message window keep the user message of a phase change) and every action;
    events in id order."""
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        case = db.get_case(conn, problem_id)
        if case is None:
            raise CaseNotFound
        annotations = db.list_annotations(conn, problem_id)
        messages = db.list_messages(conn, problem_id, last=message_limit + 1)
        actions = db.list_actions(conn, problem_id)
    events = sorted([*annotations, *messages], key=lambda event: event.id or 0)
    return CaseSnapshot(case=case, events=events, actions=actions)


def commit_turn(pool: ConnectionPool, turn: TurnCommit) -> CommittedTurn:
    """Write the whole turn in one transaction, or nothing (`CaseChanged`).

    The problem row is updated first, under the version check: its lock serializes
    concurrent commits on the case and makes the next turn number safe. Events are
    inserted in order: the user message (phase at the start of the turn), the annotations,
    the reply (phase at the end).
    """
    case = turn.snapshot.case
    events = [
        Event(
            role="user",
            event_type="message",
            content=turn.user_message,
            state_at_time=turn.phase_before,
        ),
        *turn.changes.new_events,
        Event(role="assistant", event_type="message", content=turn.reply, state_at_time=case.state),
    ]
    with pool.connection() as conn, conn.transaction():
        version = db.update_problem(conn, case, expected_version=case.version)
        if version is None:
            raise CaseChanged
        db.insert_events(conn, case.id, events)
        db.insert_actions(conn, case.id, turn.changes.new_actions)
        db.update_action_statuses(conn, case.id, turn.changes.action_updates)
        turn_no = db.insert_trace(
            conn, case.id, turn.trace, phase_before=turn.phase_before, phase_after=case.state
        )
    return CommittedTurn(version=version, turn_no=turn_no)


def read_session(pool: ConnectionPool, key: ChannelKey, *, today: date) -> SessionView | None:
    """The case linked to `key`, for inspection; None if there is none."""
    args = (key.channel_type, key.external_channel_id, key.external_thread_id)
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        linked = db.find_link(conn, *args)
        if linked is None:
            return None
        case = db.get_case(conn, linked.problem_id)
        assert case is not None
        annotations = db.list_annotations(conn, case.id)
        messages = db.list_messages(conn, case.id)
        actions = db.list_actions(conn, case.id)
        turns = db.count_turns(conn, case.id)
    return SessionView(
        problem_id=case.id,
        tenant=case.tenant,
        phase=case.state,
        version=case.version,
        turns=turns,
        fields={name: case.get_field(name) for name in FIELDS},
        events=annotations,
        actions=[SessionAction(action, action.is_overdue(today)) for action in actions],
        messages=messages,
    )
