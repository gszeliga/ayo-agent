"""health.py without a database: the embedding monitor, the tracker, the database check
against stub pools."""

import threading
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from ayo_copilot.health import (
    DATABASE_CHECK_SQL,
    EmbeddingMonitor,
    TrackedEmbedder,
    check_database,
    classify_database_location,
)
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder

T0 = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


class Clock:
    """Both clocks the monitor reads: monotonic seconds and the wall clock."""

    def __init__(self) -> None:
        self.seconds = 1000.0

    def monotonic(self) -> float:
        return self.seconds

    def now(self) -> datetime:
        return T0 + timedelta(seconds=self.seconds - 1000.0)


class Prober:
    def __init__(self, clock: Clock, *, error: Exception | None = None, takes: float = 0.0):
        self.clock = clock
        self.error = error
        self.takes = takes
        self.timeouts: list[float] = []

    def probe(self, *, timeout_seconds: float) -> None:
        self.timeouts.append(timeout_seconds)
        self.clock.seconds += self.takes
        if self.error is not None:
            raise self.error


def make_monitor(prober: Prober, clock: Clock) -> EmbeddingMonitor:
    return EmbeddingMonitor(
        prober,
        TrackedEmbedder(FakeEmbedder(dimensions=4)),
        clock=clock.monotonic,
        now=clock.now,
    )


def test_a_check_reports_up_with_its_time_and_latency() -> None:
    clock = Clock()
    prober = Prober(clock, takes=0.18)

    result, cached = make_monitor(prober, clock).check()

    assert (result.up, result.error, result.latency_ms, cached) == (True, None, 180, False)
    assert result.checked_at == T0
    assert prober.timeouts == [5.0]


def test_the_result_is_cached_for_60_seconds() -> None:
    clock = Clock()
    prober = Prober(clock)
    monitor = make_monitor(prober, clock)
    first, _ = monitor.check()

    clock.seconds += 59
    again, cached = monitor.check()
    clock.seconds += 2
    later, cached_later = monitor.check()

    assert (again, cached) == (first, True)
    assert (cached_later, len(prober.timeouts)) == (False, 2)
    assert later.checked_at == T0 + timedelta(seconds=61)


def test_refresh_checks_again_within_the_cache_time() -> None:
    clock = Clock()
    prober = Prober(clock)
    monitor = make_monitor(prober, clock)
    monitor.check()

    _, cached = monitor.check(refresh=True)

    assert (cached, len(prober.timeouts)) == (False, 2)


def test_a_failure_is_reported_and_cached_too() -> None:
    clock = Clock()
    prober = Prober(clock, error=EmbeddingError("Embedding provider returned HTTP 503"))
    monitor = make_monitor(prober, clock)

    result, _ = monitor.check()
    _, cached = monitor.check()

    assert (result.up, result.error) == (False, "Embedding provider returned HTTP 503")
    assert (cached, len(prober.timeouts)) == (True, 1)


def test_an_unexpected_exception_is_a_failure_by_its_type_only() -> None:
    clock = Clock()
    prober = Prober(clock, error=ValueError("secret detail"))

    result, _ = make_monitor(prober, clock).check()

    assert (result.up, result.error) == (False, "Embedding provider check failed (ValueError)")


def test_concurrent_callers_share_one_check() -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[float] = []

    class SlowProber:
        def probe(self, *, timeout_seconds: float) -> None:
            calls.append(timeout_seconds)
            started.set()
            release.wait(5)

    monitor = EmbeddingMonitor(SlowProber(), TrackedEmbedder(FakeEmbedder(dimensions=4)))
    results: list[bool] = []
    first = threading.Thread(target=lambda: results.append(monitor.check()[1]))
    first.start()
    started.wait(5)
    second = threading.Thread(target=lambda: results.append(monitor.check()[1]))
    second.start()
    release.set()
    first.join(5)
    second.join(5)

    assert (len(calls), sorted(results)) == (1, [False, True])


class FailingEmbedder:
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError("Embedding provider returned HTTP 503")


def test_tracker_records_successes_and_failures() -> None:
    clock = Clock()
    ok = TrackedEmbedder(FakeEmbedder(dimensions=4), now=clock.now)
    failing = TrackedEmbedder(FailingEmbedder(), now=clock.now)

    assert len(ok.embed_documents(["a", "b"])) == 2
    with pytest.raises(EmbeddingError, match="HTTP 503"):
        failing.embed_documents(["a"])

    assert (ok.last_success_at, ok.last_error_at, ok.last_error) == (T0, None, None)
    assert failing.last_success_at is None
    assert (failing.last_error_at, failing.last_error) == (
        T0,
        "Embedding provider returned HTTP 503",
    )


def test_tracker_starts_empty() -> None:
    tracker = TrackedEmbedder(FakeEmbedder(dimensions=4))

    assert (tracker.last_success_at, tracker.last_error_at, tracker.last_error) == (
        None,
        None,
        None,
    )


class StubCursor:
    def __init__(self, row: tuple | None) -> None:
        self.row = row

    def fetchone(self) -> tuple | None:
        return self.row


class StubConnection:
    def __init__(self, error: Exception | None, row: tuple | None) -> None:
        self.error = error
        self.row = row

    def execute(self, query: str) -> StubCursor:
        assert query == DATABASE_CHECK_SQL
        if self.error is not None:
            raise self.error
        return StubCursor(self.row)


class StubPool:
    def __init__(
        self,
        *,
        lend_error: Exception | None = None,
        query_error=None,
        row: tuple | None = ("18.1 (Debian 18.1-1.pgdg13+1)", "0.8.1"),
    ) -> None:
        self.lend_error = lend_error
        self.query_error = query_error
        self.row = row
        self.timeouts: list[float] = []

    @contextmanager
    def connection(self, timeout: float):
        self.timeouts.append(timeout)
        if self.lend_error is not None:
            raise self.lend_error
        yield StubConnection(self.query_error, self.row)


def test_database_up() -> None:
    pool = StubPool()

    check = check_database(pool)

    assert (check.up, check.error, pool.timeouts) == (True, None, [2.0])
    # The server version is reduced to its number.
    assert (check.postgres_version, check.pgvector_version) == ("18.1", "0.8.1")


def test_a_missing_vector_extension_has_no_version() -> None:
    check = check_database(StubPool(row=("18.1", None)))

    assert (check.up, check.postgres_version, check.pgvector_version) == (True, "18.1", None)


def test_database_without_a_connection_in_time_is_a_timeout() -> None:
    check = check_database(StubPool(lend_error=PoolTimeout("host db.internal user ayo")))

    assert (check.up, check.error) == (False, "timeout")


def test_a_failed_query_hides_psycopgs_message() -> None:
    error = psycopg.OperationalError('connection to server at "db.internal" failed')

    check = check_database(StubPool(query_error=error))

    assert (check.up, check.error) == (False, "connection failed")


def test_versions_are_unknown_when_the_database_is_down() -> None:
    check = check_database(StubPool(lend_error=PoolTimeout("x")))

    assert (check.postgres_version, check.pgvector_version) == (None, None)


@pytest.mark.parametrize(
    ("url", "location"),
    [
        ("postgresql://ayo:ayo@localhost:5433/ayo", "local"),
        ("postgresql://ayo:ayo@127.0.0.1/ayo", "local"),
        ("postgresql://ayo:ayo@[::1]:5432/ayo", "local"),
        ("postgresql:///ayo?host=/var/run/postgresql", "local"),
        ("postgresql://u:p@ep-cool-sun-123456.eu-central-1.aws.neon.tech/neondb", "neon"),
        ("postgresql://u:p@ep-cool-sun-123456-pooler.eu-central-1.aws.neon.tech/db", "neon"),
        ("postgresql://u:p@EP-X.EU-CENTRAL-1.AWS.NEON.TECH/db", "neon"),
        ("postgresql://u:p@db.example.com/ayo", "remote"),
        ("postgresql://u:p@neon.tech.example.com/ayo", "remote"),
        ("postgresql://u:p@notneon.tech/ayo", "remote"),
    ],
)
def test_database_location(url: str, location: str) -> None:
    assert classify_database_location(url) == location
