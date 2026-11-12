"""Conversation storage against real Postgres: resolving cases, snapshots, turn commits
with the version check, and the session view."""

import threading
from dataclasses import replace
from datetime import date
from uuid import UUID, uuid4

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.conversation import store as store_module
from ayo_copilot.conversation.case import Action, CaseSnapshot, Event, TurnChanges
from ayo_copilot.conversation.store import (
    CaseChanged,
    CaseNotFound,
    CaseTenantMismatch,
    ChannelKey,
    TurnCommit,
    commit_turn,
    load_snapshot,
    read_session,
    resolve_case,
)
from ayo_copilot.conversation.tools import execute_tool
from ayo_copilot.db.conversations import RetrievedTrace, ToolCallTrace, TraceRecord
from ayo_copilot.llm.fake import tool_call

pytestmark = pytest.mark.integration

TENANT = "cliente-acme"


def web_key(session: str | None = None) -> ChannelKey:
    return ChannelKey("web", "web", session or str(uuid4()))


def new_case(pool: ConnectionPool, key: ChannelKey | None = None) -> UUID:
    return resolve_case(pool, key or web_key(), tenant=TENANT, created_by="u1").problem_id


def trace(**overrides: object) -> TraceRecord:
    values: dict[str, object] = {"prompts_version": "draft-1", "llm_calls": 1, "duration_ms": 12}
    values.update(overrides)
    return TraceRecord(**values)  # type: ignore[arg-type]


def turn(
    snapshot: CaseSnapshot,
    changes: TurnChanges | None = None,
    *,
    user: str = "Tenemos merma en la línea 2",
    reply: str = "¿Desde cuándo?",
    phase_before: str | None = None,
    **trace_overrides: object,
) -> TurnCommit:
    return TurnCommit(
        snapshot=snapshot,
        phase_before=phase_before or snapshot.case.state,  # type: ignore[arg-type]
        user_message=user,
        reply=reply,
        changes=changes or TurnChanges(),
        trace=trace(**trace_overrides),
    )


def run_tool(snapshot: CaseSnapshot, changes: TurnChanges, name: str, **arguments: object):
    outcome = execute_tool(snapshot, changes, tool_call(name, arguments))
    assert outcome.ok, outcome.result
    return outcome


def fetch(pool: ConnectionPool, query: str, *params: object) -> list[tuple]:
    with pool.connection() as conn:
        return conn.execute(query, params).fetchall()


def facts_turn(pool: ConnectionPool, problem_id: UUID) -> CaseSnapshot:
    """Commit one turn recording the four facts and moving to `challenge`."""
    snapshot = load_snapshot(pool, problem_id, message_limit=12)
    changes = TurnChanges()
    for name, value in {
        "what": "Merma del 4 %",
        "where": "Línea 2",
        "since": "Desde el lunes",
        "standard": "1,5 %",
    }.items():
        run_tool(snapshot, changes, "record_field", field=name, value=value)
    run_tool(snapshot, changes, "propose_transition", target_state="challenge", reasoning="ok")
    commit_turn(pool, turn(snapshot, changes, phase_before="understand", reply="¿Qué datos?"))
    return snapshot


# --- resolve_case ---------------------------------------------------------------------------


def test_first_message_creates_the_case_and_link_then_reuses_them(db_pool: ConnectionPool) -> None:
    key = web_key()
    first = resolve_case(db_pool, key, tenant=TENANT, created_by="u1")
    second = resolve_case(db_pool, key, tenant=TENANT, created_by="u2")

    assert first.created and not second.created
    assert first.problem_id == second.problem_id
    rows = fetch(db_pool, "select tenant, state, version, created_by from problems")
    assert rows == [(TENANT, "understand", 0, "u1")]
    links = fetch(
        db_pool,
        "select problem_id, channel_type, external_channel_id, external_thread_id"
        " from conversation_links",
    )
    assert links == [(first.problem_id, "web", "web", key.external_thread_id)]


def test_other_threads_and_channels_are_other_cases(db_pool: ConnectionPool) -> None:
    key = web_key()
    a = new_case(db_pool, key)
    b = new_case(db_pool)
    c = new_case(db_pool, ChannelKey("slack", "web", key.external_thread_id))
    assert len({a, b, c}) == 3


def test_tenant_mismatch_raises_and_creates_nothing(db_pool: ConnectionPool) -> None:
    key = web_key()
    new_case(db_pool, key)
    with pytest.raises(CaseTenantMismatch):
        resolve_case(db_pool, key, tenant="cliente-otro", created_by=None)
    assert fetch(db_pool, "select count(*) from problems") == [(1,)]


def test_concurrent_first_messages_share_one_case(db_pool: ConnectionPool) -> None:
    key = web_key()
    barrier = threading.Barrier(4)
    results: list = []
    errors: list = []

    def worker() -> None:
        try:
            barrier.wait()
            results.append(resolve_case(db_pool, key, tenant=TENANT, created_by=None))
        except Exception as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len({r.problem_id for r in results}) == 1
    assert sum(r.created for r in results) == 1
    assert fetch(db_pool, "select count(*) from problems") == [(1,)]
    assert fetch(db_pool, "select count(*) from conversation_links") == [(1,)]


def test_losing_the_race_rolls_back_its_problem_and_returns_the_winner(
    db_pool: ConnectionPool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic version of the race: the first lookup misses a link that a concurrent
    request has just committed, so the insert conflicts and takes the savepoint path."""
    key = web_key()
    winner = new_case(db_pool, key)
    real_find_link = store_module.db.find_link
    calls: list[int] = []

    def stale_then_real(*args: object):
        calls.append(1)
        return None if len(calls) == 1 else real_find_link(*args)

    monkeypatch.setattr(store_module.db, "find_link", stale_then_real)
    resolved = resolve_case(db_pool, key, tenant=TENANT, created_by=None)

    assert resolved.problem_id == winner and not resolved.created
    assert len(calls) == 2
    assert fetch(db_pool, "select id from problems") == [(winner,)]


# --- load_snapshot ----------------------------------------------------------------------------


def test_snapshot_of_a_new_case(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    assert snapshot.case.id == problem_id
    assert (snapshot.case.tenant, snapshot.case.state, snapshot.case.version) == (
        TENANT,
        "understand",
        0,
    )
    assert snapshot.case.missing_fields() == ["what", "where", "since", "standard"]
    assert snapshot.events == [] and snapshot.actions == []


def test_snapshot_unknown_case(db_pool: ConnectionPool) -> None:
    with pytest.raises(CaseNotFound):
        load_snapshot(db_pool, uuid4(), message_limit=12)


def test_snapshot_keeps_every_annotation_and_the_last_messages(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    facts_turn(db_pool, problem_id)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    changes = TurnChanges()
    run_tool(snapshot, changes, "log_event", event_type="evidence", content="Turno de noche")
    commit_turn(db_pool, turn(snapshot, changes, user="m3", reply="r3"))
    for n in range(4, 8):
        snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
        commit_turn(db_pool, turn(snapshot, user=f"m{n}", reply=f"r{n}"))

    snapshot = load_snapshot(db_pool, problem_id, message_limit=3)

    assert snapshot.case.state == "challenge" and snapshot.case.version == 6
    assert snapshot.case.where_ == "Línea 2"
    kinds = [(e.event_type, e.content) for e in snapshot.events]
    # Every annotation, but only the last 3 + 1 messages.
    assert kinds == [
        ("evidence", "Turno de noche"),
        ("message", "m6"),
        ("message", "r6"),
        ("message", "m7"),
        ("message", "r7"),
    ]
    ids = [e.id for e in snapshot.events]
    assert ids == sorted(ids)
    assert all(e.created_at is not None for e in snapshot.events)


# --- commit_turn -------------------------------------------------------------------------------


def test_a_turn_writes_everything_in_order(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    snapshot = facts_turn(db_pool, problem_id)

    assert fetch(
        db_pool,
        "select state, what, where_, since, standard, version, closed_at from problems",
    ) == [("challenge", "Merma del 4 %", "Línea 2", "Desde el lunes", "1,5 %", 1, None)]
    events = fetch(
        db_pool, "select role, event_type, content, state_at_time from problem_events order by id"
    )
    assert events == [
        ("user", "message", "Tenemos merma en la línea 2", "understand"),
        ("assistant", "message", "¿Qué datos?", "challenge"),
    ]
    traces = fetch(
        db_pool,
        "select turn_no, phase_before, phase_after, prompts_version, llm_calls, capped"
        " from turn_traces",
    )
    assert traces == [(1, "understand", "challenge", "draft-1", 1, False)]
    assert snapshot.case.version == 0  # the snapshot keeps the version it was loaded with


def test_annotations_go_between_the_user_message_and_the_reply(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    facts_turn(db_pool, problem_id)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    changes = TurnChanges()
    run_tool(snapshot, changes, "log_event", event_type="hypothesis", content="Boquilla 3")
    run_tool(snapshot, changes, "log_event", event_type="evidence", content="Solo de noche")
    committed = commit_turn(db_pool, turn(snapshot, changes, user="u", reply="r"))

    assert (committed.version, committed.turn_no) == (2, 2)
    rows = fetch(
        db_pool,
        "select role, event_type, content from problem_events where id > 2 order by id",
    )
    assert rows == [
        ("user", "message", "u"),
        ("assistant", "hypothesis", "Boquilla 3"),
        ("assistant", "evidence", "Solo de noche"),
        ("assistant", "message", "r"),
    ]


def test_version_only_changes_on_commit(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    changes = TurnChanges()
    run_tool(snapshot, changes, "record_field", field="what", value="Merma")
    load_snapshot(db_pool, problem_id, message_limit=12)
    assert fetch(db_pool, "select version, what from problems") == [(0, None)]

    commit_turn(db_pool, turn(snapshot, changes))
    assert fetch(db_pool, "select version, what from problems") == [(1, "Merma")]


def test_actions_are_inserted_updated_and_closing_sets_closed_at(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    other_id = new_case(db_pool)
    with db_pool.connection() as conn:
        conn.execute("update problems set state = 'action'")
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    changes = TurnChanges()
    run_tool(
        snapshot,
        changes,
        "add_action",
        description="Cambiar la boquilla 3",
        owner="Jordi",
        due_date="2026-11-20",
    )
    run_tool(snapshot, changes, "propose_transition", target_state="followup", reasoning="ok")
    commit_turn(db_pool, turn(snapshot, changes))
    # An action of another case, with the id the model will try next.
    other = load_snapshot(db_pool, other_id, message_limit=12)
    other_changes = TurnChanges()
    run_tool(other, other_changes, "add_action", description="x", owner="y", due_date="2026-11-21")
    commit_turn(db_pool, turn(other, other_changes))

    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    (action,) = snapshot.actions
    assert (action.id, action.description, action.owner, action.due_date, action.status) == (
        1,
        "Cambiar la boquilla 3",
        "Jordi",
        date(2026, 11, 20),
        "pending",
    )
    changes = TurnChanges()
    run_tool(snapshot, changes, "update_action", action_id=1, status="done")
    run_tool(snapshot, changes, "propose_transition", target_state="closed", reasoning="ok")
    # Forge an update for the other case's action: it must not be touched.
    changes.action_updates[2] = "done"
    commit_turn(db_pool, turn(snapshot, changes))

    assert fetch(db_pool, "select id, status from actions order by id") == [
        (1, "done"),
        (2, "pending"),
    ]
    rows = fetch(
        db_pool, "select state, closed_at is not null from problems where id = %s", problem_id
    )
    assert rows == [("closed", True)]
    assert fetch(db_pool, "select closed_at from problems where id = %s", other_id) == [(None,)]


def test_turn_numbers_count_up_per_case(db_pool: ConnectionPool) -> None:
    a, b = new_case(db_pool), new_case(db_pool)
    numbers = []
    for problem_id in (a, a, b, a):
        snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
        numbers.append(commit_turn(db_pool, turn(snapshot)).turn_no)
    assert numbers == [1, 2, 1, 3]


def test_trace_is_stored_without_content(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    chunk_id = uuid4()
    commit_turn(
        db_pool,
        turn(
            snapshot,
            model="vendor/a,vendor/b",
            llm_calls=3,
            prompt_tokens=1200,
            completion_tokens=80,
            total_tokens=1280,
            cost=0.00042,
            tool_calls=(
                ToolCallTrace("record_field", True),
                ToolCallTrace("x" * 100, False, "unknown_tool"),
            ),
            retrieved=(RetrievedTrace(chunk_id, 0.8123, "d" * 64),),
            retrieval_error=None,
            capped=True,
            duration_ms=2345,
        ),
    )
    (row,) = fetch(
        db_pool,
        "select model, llm_calls, prompt_tokens, completion_tokens, total_tokens, cost::float,"
        " tool_calls, retrieved, retrieval_error, capped, duration_ms from turn_traces",
    )
    assert row == (
        "vendor/a,vendor/b",
        3,
        1200,
        80,
        1280,
        0.00042,
        [
            {"name": "record_field", "ok": True, "error_code": None},
            {"name": "x" * 64, "ok": False, "error_code": "unknown_tool"},
        ],
        [{"chunk_id": str(chunk_id), "similarity": 0.8123, "doc_id": "d" * 64}],
        None,
        True,
        2345,
    )


def test_stale_version_writes_nothing(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    first = load_snapshot(db_pool, problem_id, message_limit=12)
    second = load_snapshot(db_pool, problem_id, message_limit=12)
    commit_turn(db_pool, turn(first, user="primero"))

    changes = TurnChanges()
    run_tool(second, changes, "record_field", field="what", value="Merma")
    with pytest.raises(CaseChanged):
        commit_turn(db_pool, turn(second, changes, user="segundo"))

    assert fetch(db_pool, "select version, what from problems") == [(1, None)]
    assert fetch(db_pool, "select content from problem_events where role = 'user'") == [
        ("primero",)
    ]
    assert fetch(db_pool, "select count(*) from turn_traces") == [(1,)]


def test_concurrent_commits_from_one_snapshot_one_wins(db_pool: ConnectionPool) -> None:
    problem_id = new_case(db_pool)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker(text: str) -> None:
        own = replace(snapshot, case=replace(snapshot.case))
        barrier.wait()
        try:
            commit_turn(db_pool, turn(own, user=text))
            outcomes.append("ok")
        except CaseChanged:
            outcomes.append("changed")

    threads = [threading.Thread(target=worker, args=(t,)) for t in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["changed", "ok"]
    assert fetch(db_pool, "select version from problems") == [(1,)]
    assert fetch(db_pool, "select count(*) from problem_events") == [(2,)]
    assert fetch(db_pool, "select count(*) from turn_traces") == [(1,)]


# --- read_session -------------------------------------------------------------------------------


def test_session_view(db_pool: ConnectionPool) -> None:
    key = web_key()
    problem_id = new_case(db_pool, key)
    facts_turn(db_pool, problem_id)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    changes = TurnChanges()
    run_tool(snapshot, changes, "log_event", event_type="evidence", content="Solo de noche")
    snapshot.case.state = "action"  # skip ahead for the test: actions need that phase
    run_tool(snapshot, changes, "add_action", description="A", owner="Ana", due_date="2026-11-10")
    run_tool(snapshot, changes, "add_action", description="B", owner="Bo", due_date="2026-11-30")
    commit_turn(db_pool, turn(snapshot, changes, phase_before="challenge", user="u2", reply="r2"))

    view = read_session(db_pool, key, today=date(2026, 11, 13))

    assert view is not None
    assert (view.problem_id, view.tenant, view.phase, view.version, view.turns) == (
        problem_id,
        TENANT,
        "action",
        2,
        2,
    )
    assert view.fields == {
        "what": "Merma del 4 %",
        "where": "Línea 2",
        "since": "Desde el lunes",
        "standard": "1,5 %",
    }
    assert [(e.event_type, e.content, e.state_at_time) for e in view.events] == [
        ("evidence", "Solo de noche", "challenge")
    ]
    assert [(a.action.id, a.action.description, a.overdue) for a in view.actions] == [
        (1, "A", True),
        (2, "B", False),
    ]
    assert [(m.role, m.content, m.state_at_time) for m in view.messages] == [
        ("user", "Tenemos merma en la línea 2", "understand"),
        ("assistant", "¿Qué datos?", "challenge"),
        ("user", "u2", "challenge"),
        ("assistant", "r2", "action"),
    ]
    assert all(m.id is not None and m.created_at is not None for m in view.messages)
    assert "Merma" not in repr(view)


def test_session_view_unknown(db_pool: ConnectionPool) -> None:
    new_case(db_pool)
    assert read_session(db_pool, web_key(), today=date(2026, 11, 13)) is None


def test_events_keep_their_role(db_pool: ConnectionPool) -> None:
    # Guard against a column mix-up in the insert: role and event_type are distinct.
    problem_id = new_case(db_pool)
    snapshot = load_snapshot(db_pool, problem_id, message_limit=12)
    changes = TurnChanges(
        new_events=[Event("assistant", "hypothesis", "H", "understand")],
        new_actions=[Action("d", "o", date(2026, 1, 1))],
    )
    commit_turn(db_pool, turn(snapshot, changes))
    assert fetch(db_pool, "select role, event_type from problem_events order by id") == [
        ("user", "message"),
        ("assistant", "hypothesis"),
        ("assistant", "message"),
    ]
