import json
import math
from collections.abc import Callable

import httpx2
import pytest

from ayo_copilot.ingestion.embedding import (
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
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


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
            voyage_base_url="https://voyage.test/v1",
        )
    )

    assert isinstance(embedder, VoyageEmbedder)
    assert embedder.model == "voyage-4-lite"
    assert embedder.dimensions == 512
    assert embedder.batch_size == 64
    assert embedder.timeout_seconds == 12.5
    embedder.close()
