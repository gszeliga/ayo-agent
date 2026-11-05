"""Service status for `GET /admin/health`: a database round trip, a cached check of the
embedding provider, and what the last real embedding calls did.

Error texts are fixed phrases or `EmbeddingError` messages, which never quote the
provider's answer, the key or the texts: they are safe to show in the UI.
"""

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from ayo_copilot.ingestion.embedding import Embedder, EmbeddingError

DATABASE_TIMEOUT_SECONDS = 2.0
PROBE_TIMEOUT_SECONDS = 5.0
PROBE_CACHE_SECONDS = 60.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _elapsed_ms(start: float, clock: Callable[[], float]) -> int:
    return round((clock() - start) * 1000)


@dataclass(frozen=True)
class DatabaseCheck:
    up: bool
    latency_ms: int
    error: str | None


def check_database(
    pool: ConnectionPool,
    *,
    timeout_seconds: float = DATABASE_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> DatabaseCheck:
    """`select 1` through the pool. A pool too busy to lend a connection in time counts as
    a timeout too: requests would be waiting as well. psycopg's messages are not passed
    on, since they can name the host or the user."""
    start = clock()
    try:
        with pool.connection(timeout=timeout_seconds) as conn:
            conn.execute("select 1")
    except PoolTimeout:
        return DatabaseCheck(up=False, latency_ms=_elapsed_ms(start, clock), error="timeout")
    except psycopg.Error:
        return DatabaseCheck(
            up=False, latency_ms=_elapsed_ms(start, clock), error="connection failed"
        )
    return DatabaseCheck(up=True, latency_ms=_elapsed_ms(start, clock), error=None)


class Prober(Protocol):
    def probe(self, *, timeout_seconds: float) -> None: ...


class TrackedEmbedder:
    """Wraps the app's embedder and remembers how its last real calls (uploads,
    reprocesses) went. In memory only, so empty after a restart."""

    def __init__(self, inner: Embedder, *, now: Callable[[], datetime] = _utc_now) -> None:
        self.inner = inner
        self._now = now
        self._lock = threading.Lock()
        self.last_success_at: datetime | None = None
        self.last_error_at: datetime | None = None
        self.last_error: str | None = None

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            vectors = self.inner.embed_documents(texts)
        except EmbeddingError as exc:
            with self._lock:
                self.last_error_at = self._now()
                self.last_error = str(exc)
            raise
        with self._lock:
            self.last_success_at = self._now()
        return vectors

    def close(self) -> None:
        close = getattr(self.inner, "close", None)
        if close is not None:
            close()


@dataclass(frozen=True)
class ProbeResult:
    up: bool
    checked_at: datetime
    latency_ms: int
    error: str | None


class EmbeddingMonitor:
    """Checks the provider on demand and keeps the result for a while, failures included,
    so page loads and an outage don't turn into a stream of provider calls. Callers that
    arrive during a check wait for it and share its result."""

    def __init__(
        self,
        prober: Prober,
        tracker: TrackedEmbedder,
        *,
        cache_seconds: float = PROBE_CACHE_SECONDS,
        timeout_seconds: float = PROBE_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.tracker = tracker
        self._prober = prober
        self._cache_seconds = cache_seconds
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._last: ProbeResult | None = None
        self._last_at = 0.0

    def check(self, *, refresh: bool = False) -> tuple[ProbeResult, bool]:
        """The latest result and whether it came from the cache."""
        with self._lock:
            fresh = self._last is not None and self._clock() - self._last_at < self._cache_seconds
            if fresh and not refresh:
                assert self._last is not None
                return self._last, True
            start = self._clock()
            checked_at = self._now()
            try:
                self._prober.probe(timeout_seconds=self._timeout_seconds)
                error = None
            except EmbeddingError as exc:
                error = str(exc)
            except Exception as exc:
                error = f"Embedding provider check failed ({type(exc).__name__})"
            self._last = ProbeResult(
                up=error is None,
                checked_at=checked_at,
                latency_ms=_elapsed_ms(start, self._clock),
                error=error,
            )
            self._last_at = self._clock()
            return self._last, False
