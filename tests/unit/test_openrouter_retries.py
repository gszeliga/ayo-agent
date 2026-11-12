"""Retries, the per-call log line, generation ids and privacy of OpenRouterProvider."""

import json
import logging
import traceback
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any

import httpx2
import pytest

from ayo_copilot.llm import (
    LLMAuthError,
    LLMBadRequestError,
    LLMError,
    LLMInsufficientCreditsError,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
    Message,
    ToolSpec,
)
from ayo_copilot.llm.fake import tool_call
from ayo_copilot.llm.openrouter import MAX_BACKOFF_SECONDS, OpenRouterProvider, parse_retry_after

API_KEY = "sk-or-v1-secret-test-key"
BASE_URL = "https://openrouter.test/api/v1"
SECRET = "Contenido confidencial: presión de sellado 4,2 bar en la línea 3"
LOGGER = "ayo_copilot.llm.openrouter"

TOOL = ToolSpec(
    name="record_field",
    description=f"Registra un dato. {SECRET}",
    parameters={"type": "object", "properties": {"value": {"type": "string"}}},
)

Step = httpx2.Response | Exception


class FakeTime:
    """A clock that only moves when the provider sleeps or a request takes time."""

    def __init__(self, request_seconds: float = 0.0) -> None:
        self.now = 1000.0
        self.request_seconds = request_seconds
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Script:
    """A MockTransport handler that plays one step per request, then repeats the last."""

    def __init__(self, time: FakeTime, *steps: Step) -> None:
        self.time = time
        self.steps = list(steps)
        self.requests = 0

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        step = self.steps[min(self.requests, len(self.steps) - 1)]
        self.requests += 1
        self.time.now += self.time.request_seconds
        if isinstance(step, Exception):
            raise step
        return step


def ok(generation_id: str = "gen-ok", **message: Any) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": generation_id,
            "model": "mistralai/mistral-small-3.2-24b-instruct",
            "provider": "Mistral",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Entendido.", **message},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "completion_tokens_details": {"reasoning_tokens": 5},
                "cost": 0.0000231,
            },
        },
    )


def failure(status: int, retry_after: str | None = None) -> httpx2.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    body = {"error": {"code": status, "message": f"Echo: {SECRET} {API_KEY}"}}
    return httpx2.Response(status, json=body, headers=headers)


def error_in_200(code: int, generation_id: str | None = "gen-failed") -> httpx2.Response:
    body: dict[str, Any] = {"error": {"code": code, "message": f"Upstream said: {SECRET}"}}
    if generation_id:
        body["id"] = generation_id
    return httpx2.Response(200, json=body)


def make(
    time: FakeTime, *steps: Step, max_retries: int = 2, budget: float = 90.0
) -> tuple[OpenRouterProvider, Script]:
    script = Script(time, *steps)
    provider = OpenRouterProvider(
        api_key=API_KEY,
        model="mistralai/mistral-small-3.2-24b-instruct",
        max_retries=max_retries,
        retry_budget_seconds=budget,
        base_url=BASE_URL,
        client=httpx2.Client(base_url=BASE_URL, transport=httpx2.MockTransport(script)),
        clock=time.clock,
        sleep=time.sleep,
        wall_clock=lambda: 1_700_000_000.0,
    )
    return provider, script


def call(provider: OpenRouterProvider) -> Any:
    return provider.complete(
        system=f"Eres el copiloto. {SECRET}",
        messages=[
            Message(role="user", content=SECRET),
            Message(role="assistant", tool_calls=(tool_call("record_field", {"value": SECRET}),)),
            Message(role="tool", tool_call_id="call_record_field", content=SECRET),
        ],
        tools=[TOOL],
    )


# --- Retries ----------------------------------------------------------------


@pytest.mark.parametrize(
    "step",
    [
        failure(429),
        failure(408),
        failure(500),
        failure(502),
        failure(503),
        error_in_200(502),
        error_in_200(429),
        httpx2.ReadTimeout("timed out"),
        httpx2.ConnectError("refused"),
    ],
)
def test_retryable_failures_are_retried_until_success(step: Step) -> None:
    time = FakeTime()
    provider, script = make(time, step, step, ok())

    response = call(provider)

    assert script.requests == 3
    assert response.attempts == 3
    assert response.text == "Entendido."
    assert len(time.sleeps) == 2


@pytest.mark.parametrize(
    ("step", "error"),
    [
        (failure(429), LLMRateLimitError),
        (failure(503), LLMUnavailableError),
        (httpx2.ReadTimeout("timed out"), LLMUnavailableError),
    ],
)
def test_attempts_are_bounded(step: Step, error: type[LLMError]) -> None:
    time = FakeTime()
    provider, script = make(time, step, max_retries=2)

    with pytest.raises(error, match="after 3 attempts") as excinfo:
        call(provider)
    assert script.requests == 3
    assert excinfo.value.attempts == 3


def test_no_retries_when_max_retries_is_zero() -> None:
    time = FakeTime()
    provider, script = make(time, failure(503), max_retries=0)

    with pytest.raises(LLMUnavailableError) as excinfo:
        call(provider)
    assert script.requests == 1
    assert excinfo.value.attempts == 1
    assert "attempts" not in str(excinfo.value)
    assert time.sleeps == []


@pytest.mark.parametrize(
    ("step", "error"),
    [
        (failure(400), LLMBadRequestError),
        (failure(401), LLMAuthError),
        (failure(402), LLMInsufficientCreditsError),
        (failure(402, retry_after="1"), LLMInsufficientCreditsError),
        (failure(403), LLMBadRequestError),
        (error_in_200(401), LLMAuthError),
        (httpx2.Response(200, content=b"{not json"), LLMResponseError),
        (httpx2.Response(200, json={"choices": []}), LLMResponseError),
    ],
)
def test_never_retried(step: Step, error: type[LLMError]) -> None:
    time = FakeTime()
    provider, script = make(time, step, ok())

    with pytest.raises(error):
        call(provider)
    assert script.requests == 1
    assert time.sleeps == []


def test_retry_after_seconds_is_honoured() -> None:
    time = FakeTime()
    provider, _ = make(time, failure(429, retry_after="7"), failure(503, retry_after="3"), ok())

    call(provider)

    assert time.sleeps == [7.0, 3.0]


def test_retry_after_date_is_honoured() -> None:
    time = FakeTime()
    at = format_datetime(datetime.fromtimestamp(1_700_000_012, tz=UTC), usegmt=True)
    provider, _ = make(time, failure(429, retry_after=at), ok())

    call(provider)

    assert time.sleeps == [12.0]


def test_backoff_without_retry_after_grows_with_jitter_and_a_cap() -> None:
    time = FakeTime()
    provider, _ = make(time, failure(502), max_retries=8, budget=1000.0)

    with pytest.raises(LLMUnavailableError):
        call(provider)

    assert len(time.sleeps) == 8
    for attempt, slept in enumerate(time.sleeps, start=1):
        assert 0 <= slept <= min(MAX_BACKOFF_SECONDS, 2.0 ** (attempt - 1))


def test_a_wait_past_the_budget_gives_up_at_once() -> None:
    time = FakeTime()
    provider, script = make(time, failure(429, retry_after="120"), ok(), budget=90.0)

    with pytest.raises(LLMRateLimitError) as excinfo:
        call(provider)
    assert script.requests == 1
    assert time.sleeps == []
    assert excinfo.value.attempts == 1


def test_the_budget_counts_time_spent_in_requests() -> None:
    # Each request takes 40 s; after two, a third would start past the 90 s budget.
    time = FakeTime(request_seconds=40.0)
    provider, script = make(time, failure(503, retry_after="5"), max_retries=5, budget=90.0)

    with pytest.raises(LLMUnavailableError) as excinfo:
        call(provider)
    assert script.requests == 2
    assert time.sleeps == [5.0]
    assert excinfo.value.attempts == 2


def test_latency_covers_retries_and_waits() -> None:
    time = FakeTime(request_seconds=0.5)
    provider, _ = make(time, failure(429, retry_after="2"), ok())

    response = call(provider)

    assert response.latency_ms == 3000  # two requests of 0.5 s and a 2 s wait


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("5", 5.0),
        ("1.5", 1.5),
        ("-3", 0.0),
        ("soon", None),
        ("nan", None),
        ("Tue, 14 Nov 2023 22:13:30 GMT", 10.0),  # 1_700_000_010
        ("Tue, 14 Nov 2023 22:13:00 GMT", 0.0),  # in the past
    ],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    assert parse_retry_after(value, now=1_700_000_000.0) == expected


# --- Generation ids ---------------------------------------------------------


def test_generation_ids_of_failed_and_successful_attempts() -> None:
    time = FakeTime()
    provider, _ = make(
        time,
        error_in_200(502, "gen-1"),
        failure(503),
        error_in_200(502, "gen-3"),
        ok("gen-4"),
        max_retries=3,
    )

    response = call(provider)

    assert response.generation_id == "gen-4"
    assert response.attempts == 4


def test_the_final_error_lists_every_generation_id() -> None:
    time = FakeTime()
    provider, _ = make(time, error_in_200(502, "gen-1"), failure(503), error_in_200(502, "gen-3"))

    with pytest.raises(LLMUnavailableError) as excinfo:
        call(provider)
    assert excinfo.value.generation_ids == ("gen-1", "gen-3")


# --- The log line -----------------------------------------------------------


def log_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == LOGGER]


def test_one_info_line_per_successful_call(caplog: pytest.LogCaptureFixture) -> None:
    time = FakeTime()
    response = ok(
        "gen-ok",
        content=None,
        tool_calls=[
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "record_field", "arguments": "{}"},
            },
            {"id": "c2", "type": "function", "function": {"name": "log_event", "arguments": "{}"}},
        ],
    )
    provider, _ = make(time, failure(429, retry_after="1"), error_in_200(502, "gen-1"), response)

    with caplog.at_level(logging.DEBUG):
        call(provider)

    (record,) = log_lines(caplog)
    assert record.levelno == logging.INFO
    message = record.getMessage()
    for expected in [
        "outcome=ok",
        "status=200",
        "model_requested=mistralai/mistral-small-3.2-24b-instruct",
        "model_used=mistralai/mistral-small-3.2-24b-instruct",
        "provider=Mistral",
        "attempts=3",
        "retried=http_429,body_502",
        "latency_ms=",  # the second wait is random backoff
        "prompt_tokens=100",
        "completion_tokens=20",
        "reasoning_tokens=5",
        "cost=0.000023",
        "finish_reason=stop",
        "tool_calls=2",
        "tools=record_field,log_event",
        "generation_ids=gen-1,gen-ok",
    ]:
        assert expected in message


def test_one_warning_line_per_failed_call(caplog: pytest.LogCaptureFixture) -> None:
    time = FakeTime()
    provider, _ = make(time, error_in_200(502, "gen-1"), failure(429))

    with caplog.at_level(logging.DEBUG), pytest.raises(LLMRateLimitError):
        call(provider)

    (record,) = log_lines(caplog)
    assert record.levelno == logging.WARNING
    message = record.getMessage()
    for expected in [
        "outcome=error",
        "error=LLMRateLimitError",
        "reason=http_429",
        "status=429",
        "attempts=3",
        "retried=body_502,http_429",
        "generation_ids=gen-1",
    ]:
        assert expected in message


def test_unknown_values_are_logged_as_dashes(caplog: pytest.LogCaptureFixture) -> None:
    time = FakeTime()
    bare = httpx2.Response(200, json={"choices": [{"message": {"content": "Hola"}}]})
    provider, _ = make(time, bare)

    with caplog.at_level(logging.INFO):
        call(provider)

    message = log_lines(caplog)[0].getMessage()
    for expected in ["model_used=-", "provider=-", "cost=-", "tools=-", "generation_ids=-"]:
        assert expected in message


def test_invented_tool_names_are_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    time = FakeTime()
    response = ok(
        content=None,
        tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": SECRET, "arguments": "{}"}}
        ],
    )
    provider, _ = make(time, response)

    with caplog.at_level(logging.INFO):
        result = call(provider)

    assert result.tool_calls[0].name == SECRET  # the caller still sees it
    assert "tools=<invalid>" in log_lines(caplog)[0].getMessage()


# --- Privacy on every path --------------------------------------------------

PATHS: list[tuple[str, list[Step]]] = [
    (
        "success with secret text, reasoning and arguments",
        [
            ok(
                content=SECRET,
                reasoning=SECRET,
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "record_field",
                            "arguments": json.dumps({"value": SECRET}),
                        },
                    }
                ],
            )
        ],
    ),
    (
        "invalid arguments",
        [
            ok(
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "record_field", "arguments": SECRET},
                    }
                ]
            )
        ],
    ),
    ("retries then success", [failure(429, "1"), error_in_200(502), ok(content=SECRET)]),
    ("401", [failure(401)]),
    ("402", [failure(402)]),
    ("400", [failure(400)]),
    ("403", [failure(403)]),
    ("429 exhausted", [failure(429)]),
    ("503 exhausted", [failure(503)]),
    ("error in 200", [error_in_200(429)]),
    ("timeout", [httpx2.ReadTimeout(f"timed out sending {SECRET} with {API_KEY}")]),
    ("connection", [httpx2.ConnectError(f"refused: {SECRET} {API_KEY}")]),
    ("not JSON", [httpx2.Response(200, content=f"<html>{SECRET} {API_KEY}".encode())]),
    (
        "malformed",
        [httpx2.Response(200, json={"choices": [{"message": {"content": 42}}], "x": SECRET})],
    ),
]


@pytest.mark.parametrize("steps", [steps for _, steps in PATHS], ids=[name for name, _ in PATHS])
def test_no_key_or_content_in_logs_or_errors(
    steps: list[Step], caplog: pytest.LogCaptureFixture
) -> None:
    time = FakeTime()
    provider, _ = make(time, *steps)

    texts: list[str] = []
    with caplog.at_level(logging.DEBUG):  # every logger, httpx2's included
        try:
            response = call(provider)
        except LLMError as exc:
            texts += [str(exc), repr(exc), "".join(traceback.format_exception(exc))]
        else:
            texts.append(repr(response))

    texts += [record.getMessage() for record in caplog.records]
    texts += [repr(record.args) for record in caplog.records]
    assert log_lines(caplog), "the call must log its line"
    for text in texts:
        assert SECRET not in text
        assert API_KEY not in text
