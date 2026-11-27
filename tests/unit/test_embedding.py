import json
import logging
import math
from collections.abc import Callable

import httpx2
import pytest

from ayo_copilot.ingestion.embedding import (
    MAX_BACKOFF_SECONDS,
    QUERY_RETRY_BUDGET_SECONDS,
    Embedder,
    EmbeddingError,
    FakeEmbedder,
    VoyageEmbedder,
    build_embedder,
)
from tests.unit.test_config import make_settings

API_KEY = "sk-secret-voyage-key"
SECRET_TEXT = "Contenido confidencial del cliente: presión de sellado 4,2 bar"

Handler = Callable[[httpx2.Request], httpx2.Response]


def vectors_response(request: httpx2.Request, dimensions: int = 4) -> httpx2.Response:
    """Answers like Voyage: one vector per input, with its index, in reverse order."""
    inputs = json.loads(request.content)["input"]
    data = [
        {"object": "embedding", "index": i, "embedding": [float(i)] * dimensions}
        for i in range(len(inputs))
    ]
    return httpx2.Response(
        200, json={"object": "list", "data": data[::-1], "model": "voyage-4", "usage": {}}
    )


def make_voyage(
    handler: Handler,
    *,
    batch_size: int = 128,
    max_retries: int = 3,
    dimensions: int = 4,
    sleeps: list[float] | None = None,
    clock: "FakeClock | None" = None,
    retry_budget_seconds: float = 60.0,
) -> VoyageEmbedder:
    client = httpx2.Client(
        transport=httpx2.MockTransport(handler), base_url="https://voyage.test/v1"
    )
    return VoyageEmbedder(
        api_key=API_KEY,
        model="voyage-4",
        dimensions=dimensions,
        batch_size=batch_size,
        max_retries=max_retries,
        client=client,
        retry_budget_seconds=retry_budget_seconds,
        sleep=clock.sleep if clock else (sleeps.append if sleeps is not None else lambda _: None),
        clock=clock.monotonic if clock else lambda: 0.0,
        wall_clock=clock.time if clock else lambda: WALL_START,
    )


WALL_START = 1_700_000_000.0


class FakeClock:
    """Time that moves only when the embedder sleeps; records every wait."""

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.elapsed += seconds

    def monotonic(self) -> float:
        return self.elapsed

    def time(self) -> float:
        return WALL_START + self.elapsed


def rate_limited(retry_after: str | None = None) -> httpx2.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx2.Response(429, headers=headers, json={"detail": SECRET_TEXT})


def scripted(*failures: httpx2.Response) -> Handler:
    """Answers the failures in order, then vectors."""
    remaining = iter(failures)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return next(remaining, None) or vectors_response(request)

    return handler


# --- FakeEmbedder -------------------------------------------------------------


def test_fake_is_deterministic_and_has_the_configured_dimension() -> None:
    first = FakeEmbedder(dimensions=16).embed_documents(["uno", "dos"])
    second = FakeEmbedder(dimensions=16).embed_documents(["uno", "dos"])

    assert first == second
    assert [len(v) for v in first] == [16, 16]
    assert first[0] != first[1]


def test_fake_vectors_are_unit_length() -> None:
    (vector,) = FakeEmbedder(dimensions=1024).embed_documents(["Guía de inspección"])

    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0)


def test_fake_records_calls() -> None:
    fake = FakeEmbedder(dimensions=8)
    fake.embed_documents(["a", "b"])
    fake.embed_documents(["c"])

    assert fake.calls == [["a", "b"], ["c"]]


def test_fake_returns_empty_list_without_recording_a_call() -> None:
    fake = FakeEmbedder(dimensions=8)

    assert fake.embed_documents([]) == []
    assert fake.calls == []


def test_fake_query_matches_the_same_text_as_a_document_and_is_recorded_apart() -> None:
    fake = FakeEmbedder(dimensions=8)
    (as_document,) = FakeEmbedder(dimensions=8).embed_documents(["¿Cómo se sella?"])

    assert fake.embed_query("¿Cómo se sella?") == as_document
    assert (fake.query_calls, fake.calls) == (["¿Cómo se sella?"], [])


def test_both_implementations_satisfy_the_protocol() -> None:
    assert isinstance(FakeEmbedder(dimensions=8), Embedder)
    assert isinstance(make_voyage(vectors_response), Embedder)


# --- VoyageEmbedder: request shape and batching -------------------------------


def test_request_shape() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return vectors_response(request)

    make_voyage(handler).embed_documents(["uno", "dos"])

    (request,) = requests
    assert request.method == "POST"
    assert str(request.url) == "https://voyage.test/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {
        "input": ["uno", "dos"],
        "model": "voyage-4",
        "input_type": "document",
        "output_dimension": 4,
        "output_dtype": "float",
        "truncation": False,
    }


def test_vectors_are_returned_in_input_order() -> None:
    vectors = make_voyage(vectors_response).embed_documents(["a", "b", "c"])

    assert vectors == [[0.0] * 4, [1.0] * 4, [2.0] * 4]


def test_splits_inputs_into_batches() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        batches.append(json.loads(request.content)["input"])
        return vectors_response(request)

    texts = [f"t{i}" for i in range(5)]
    vectors = make_voyage(handler, batch_size=2).embed_documents(texts)

    assert batches == [["t0", "t1"], ["t2", "t3"], ["t4"]]
    assert len(vectors) == 5
    # Indexes restart in each batch; the result is still in input order.
    assert vectors[2] == [0.0] * 4


def test_empty_input_makes_no_request() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request expected")

    assert make_voyage(handler).embed_documents([]) == []


def test_query_is_sent_as_one_input_of_type_query() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return vectors_response(request)

    vector = make_voyage(handler).embed_query("¿Qué hago si el sellado falla?")

    (request,) = requests
    assert vector == [0.0] * 4
    assert json.loads(request.content) == {
        "input": ["¿Qué hago si el sellado falla?"],
        "model": "voyage-4",
        "input_type": "query",
        "output_dimension": 4,
        "output_dtype": "float",
        "truncation": False,
    }


def test_query_retries_like_documents_and_maps_failures() -> None:
    responses = iter([httpx2.Response(503)])
    sleeps: list[float] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        return next(responses, None) or vectors_response(request)

    assert make_voyage(handler, sleeps=sleeps).embed_query("a") == [0.0] * 4
    assert len(sleeps) == 1

    def failing(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"detail": SECRET_TEXT})

    with pytest.raises(EmbeddingError, match="HTTP 401") as raised:
        make_voyage(failing).embed_query(SECRET_TEXT)
    assert SECRET_TEXT not in str(raised.value)


def test_query_rejects_a_malformed_answer() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"data": []})

    with pytest.raises(EmbeddingError, match="malformed"):
        make_voyage(handler).embed_query("a")


# --- VoyageEmbedder: retries ---------------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_rate_limits_and_server_errors(status: int) -> None:
    responses = iter([httpx2.Response(status, json={"detail": "busy"})] * 2)
    sleeps: list[float] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        return next(responses, None) or vectors_response(request)

    vectors = make_voyage(handler, sleeps=sleeps).embed_documents(["a"])

    assert vectors == [[0.0] * 4]
    assert len(sleeps) == 2
    assert all(s > 0 for s in sleeps)


def test_retries_timeouts_and_connection_errors() -> None:
    errors = iter([httpx2.ReadTimeout("slow"), httpx2.ConnectError("refused")])

    def handler(request: httpx2.Request) -> httpx2.Response:
        error = next(errors, None)
        if error is not None:
            raise error
        return vectors_response(request)

    assert make_voyage(handler).embed_documents(["a"]) == [[0.0] * 4]


def test_backoff_grows_exponentially() -> None:
    sleeps: list[float] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503)

    with pytest.raises(EmbeddingError):
        make_voyage(handler, max_retries=3, sleeps=sleeps).embed_documents(["a"])

    # Full jitter: each wait is at most 1, 2, 4 seconds.
    assert len(sleeps) == 3
    assert [s <= cap for s, cap in zip(sleeps, [1, 2, 4], strict=True)] == [True] * 3


def test_gives_up_after_max_retries() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(429)

    with pytest.raises(EmbeddingError, match="429"):
        make_voyage(handler, max_retries=2).embed_documents(["a"])

    assert calls == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_does_not_retry_client_errors(status: int) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(status, json={"detail": "bad"})

    with pytest.raises(EmbeddingError, match=str(status)):
        make_voyage(handler).embed_documents(["a"])

    assert calls == 1


# --- VoyageEmbedder: malformed responses ---------------------------------------


@pytest.mark.parametrize(
    ("body", "texts"),
    [
        ({"data": []}, ["a"]),
        ({"data": [{"index": 0, "embedding": [1.0, 2.0]}]}, ["a"]),
        (
            {"data": [{"index": 0, "embedding": [1.0] * 4}, {"index": 0, "embedding": [1.0] * 4}]},
            ["a", "b"],
        ),
        ({"data": [{"index": 0, "embedding": "nope"}]}, ["a"]),
        ({"unexpected": True}, ["a"]),
    ],
    ids=["missing-vector", "wrong-dimension", "duplicate-index", "not-a-list", "no-data"],
)
def test_rejects_malformed_responses(body: dict[str, object], texts: list[str]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=body)

    with pytest.raises(EmbeddingError):
        make_voyage(handler).embed_documents(texts)


def test_rejects_non_json_response() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text="<html>gateway</html>")

    with pytest.raises(EmbeddingError):
        make_voyage(handler).embed_documents(["a"])


# --- VoyageEmbedder: no leaks --------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        lambda r: httpx2.Response(400, json={"detail": f"bad input: {SECRET_TEXT} {API_KEY}"}),
        lambda r: httpx2.Response(503, text=SECRET_TEXT),
        lambda r: httpx2.Response(200, json={"data": [], "echo": SECRET_TEXT}),
    ],
    ids=["client-error", "server-error", "malformed"],
)
def test_errors_leak_neither_key_nor_content(failure: Handler) -> None:
    with pytest.raises(EmbeddingError) as excinfo:
        make_voyage(failure, max_retries=1).embed_documents([SECRET_TEXT])

    error = excinfo.value
    for text in (str(error), repr(error)):
        assert API_KEY not in text
        assert SECRET_TEXT not in text
    # No chained exception would be printed in a traceback.
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__


def test_transport_error_leaks_nothing() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"refused {API_KEY}")

    with pytest.raises(EmbeddingError) as excinfo:
        make_voyage(handler, max_retries=0).embed_documents([SECRET_TEXT])

    assert API_KEY not in str(excinfo.value)
    assert excinfo.value.__suppress_context__


def test_waits_for_retry_after_in_seconds() -> None:
    clock = FakeClock()

    vectors = make_voyage(scripted(rate_limited("7")), clock=clock).embed_documents(["a"])

    assert vectors == [[0.0] * 4]
    assert clock.sleeps == [7.0]


def test_waits_for_retry_after_as_an_http_date() -> None:
    clock = FakeClock()
    # WALL_START is 2023-11-14 22:13:20 UTC: 12 seconds later.
    handler = scripted(rate_limited("Tue, 14 Nov 2023 22:13:32 GMT"))

    make_voyage(handler, clock=clock).embed_documents(["a"])

    assert clock.sleeps == [12.0]


def test_unreadable_retry_after_falls_back_to_backoff() -> None:
    clock = FakeClock()

    make_voyage(scripted(rate_limited("soon")), clock=clock).embed_documents(["a"])

    assert len(clock.sleeps) == 1
    assert 0 < clock.sleeps[0] <= 1


def test_backoff_is_capped() -> None:
    clock = FakeClock()

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503)

    with pytest.raises(EmbeddingError):
        make_voyage(
            handler, max_retries=8, clock=clock, retry_budget_seconds=1000.0
        ).embed_documents(["a"])

    assert len(clock.sleeps) == 8
    assert max(clock.sleeps) <= MAX_BACKOFF_SECONDS


def test_gives_up_when_the_next_wait_would_end_past_the_budget() -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return rate_limited("40")

    with pytest.raises(EmbeddingError, match=r"^Embedding provider returned HTTP 429, after 2 "):
        make_voyage(handler, max_retries=6, clock=clock).embed_documents(["a"])

    # 40 s fits in the 60 s budget; a second 40 s wait would end at 80 s.
    assert (calls, clock.sleeps) == (2, [40.0])


def test_a_retry_after_longer_than_the_budget_fails_at_once() -> None:
    clock = FakeClock()

    with pytest.raises(EmbeddingError, match=r"^Embedding provider returned HTTP 429$"):
        make_voyage(scripted(rate_limited("120")), clock=clock).embed_documents(["a"])

    assert clock.sleeps == []


def test_queries_have_a_shorter_budget_than_documents() -> None:
    wait = str(QUERY_RETRY_BUDGET_SECONDS + 5)
    clock = FakeClock()

    with pytest.raises(EmbeddingError, match="HTTP 429"):
        make_voyage(scripted(rate_limited(wait)), clock=clock).embed_query("a")
    assert clock.sleeps == []

    make_voyage(scripted(rate_limited(wait)), clock=clock).embed_documents(["a"])
    assert clock.sleeps == [float(wait)]


def test_each_retry_logs_one_warning_without_key_or_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = scripted(rate_limited("3"), httpx2.Response(503))

    with caplog.at_level(logging.DEBUG, logger="ayo_copilot.ingestion.embedding"):
        make_voyage(handler, clock=FakeClock()).embed_documents([SECRET_TEXT])

    records = [r for r in caplog.records if r.name == "ayo_copilot.ingestion.embedding"]
    assert [r.levelno for r in records] == [logging.WARNING] * 2
    first, second = (r.getMessage() for r in records)
    assert (
        first == "Embedding request failed (returned HTTP 429); retry 1 of 3 in 3.0 s (Retry-After)"
    )
    assert second.startswith("Embedding request failed (returned HTTP 503); retry 2 of 3 in ")
    for message in (first, second):
        assert SECRET_TEXT not in message and API_KEY not in message


def test_transport_errors_log_only_the_exception_type(caplog: pytest.LogCaptureFixture) -> None:
    errors = iter([httpx2.ConnectError(f"refused {SECRET_TEXT}")])

    def handler(request: httpx2.Request) -> httpx2.Response:
        error = next(errors, None)
        if error is not None:
            raise error
        return vectors_response(request)

    with caplog.at_level(logging.WARNING, logger="ayo_copilot.ingestion.embedding"):
        make_voyage(handler, clock=FakeClock()).embed_documents(["a"])

    (record,) = [r for r in caplog.records if r.name == "ayo_copilot.ingestion.embedding"]
    assert record.getMessage().startswith("Embedding request failed (unreachable (ConnectError))")
    assert SECRET_TEXT not in record.getMessage()


# --- build_embedder ------------------------------------------------------------


def test_build_fake_embedder() -> None:
    embedder = build_embedder(make_settings(embedding_provider="fake", embedding_dimensions=32))

    assert isinstance(embedder, FakeEmbedder)
    assert len(embedder.embed_documents(["x"])[0]) == 32


def test_build_voyage_embedder_uses_settings() -> None:
    embedder = build_embedder(
        make_settings(
            embedding_model="voyage-4-lite",
            embedding_dimensions=512,
            embedding_batch_size=64,
            embedding_timeout_seconds=12.5,
            embedding_max_retries=4,
            embedding_retry_budget_seconds=45.0,
            voyage_base_url="https://voyage.test/v1",
        )
    )

    assert isinstance(embedder, VoyageEmbedder)
    assert embedder.model == "voyage-4-lite"
    assert embedder.dimensions == 512
    assert embedder.batch_size == 64
    assert embedder.timeout_seconds == 12.5
    assert (embedder.max_retries, embedder.retry_budget_seconds) == (4, 45.0)
    embedder.close()


# --- probe ----------------------------------------------------------------------


def test_probe_sends_one_request_for_one_word_with_its_own_timeout() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return vectors_response(request)

    make_voyage(handler).probe(timeout_seconds=5.0)

    (request,) = requests
    assert json.loads(request.content)["input"] == ["ping"]
    assert request.extensions["timeout"] == {
        "connect": 5.0,
        "read": 5.0,
        "write": 5.0,
        "pool": 5.0,
    }


def test_probe_fails_at_once_without_retrying() -> None:
    calls: list[httpx2.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(503, json={"detail": SECRET_TEXT})

    with pytest.raises(EmbeddingError) as raised:
        make_voyage(handler, max_retries=3, sleeps=sleeps).probe(timeout_seconds=5.0)

    assert (len(calls), sleeps) == (1, [])
    assert str(raised.value) == "Embedding provider returned HTTP 503"


def test_probe_reports_a_timeout_without_the_exception_text() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout(f"slow {API_KEY}")

    with pytest.raises(EmbeddingError) as raised:
        make_voyage(handler).probe(timeout_seconds=5.0)

    assert str(raised.value) == "Embedding provider unreachable (ReadTimeout)"


def test_probe_rejects_a_malformed_answer() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return vectors_response(request, dimensions=3)

    with pytest.raises(EmbeddingError, match="malformed"):
        make_voyage(handler, dimensions=4).probe(timeout_seconds=5.0)


def test_normal_calls_keep_the_client_timeout() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return vectors_response(request)

    client = httpx2.Client(
        transport=httpx2.MockTransport(handler), base_url="https://voyage.test/v1", timeout=30.0
    )
    embedder = VoyageEmbedder(
        api_key=API_KEY, model="voyage-4", dimensions=4, batch_size=8, max_retries=0, client=client
    )
    embedder.embed_documents(["a"])

    assert requests[0].extensions["timeout"]["read"] == 30.0


def test_fake_probe_always_succeeds() -> None:
    FakeEmbedder(dimensions=4).probe(timeout_seconds=0.001)
