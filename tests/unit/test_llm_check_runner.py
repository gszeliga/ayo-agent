import json
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from ayo_copilot.llm import LLMRateLimitError, LLMResponse, Message, ToolSpec, Usage
from ayo_copilot.llm.check.report import DRAFT_NOTICE, build_report
from ayo_copilot.llm.check.runner import (
    Pricing,
    RunResult,
    percentile,
    planned_calls,
    rate,
    run_check,
    summarize,
    wilson_interval,
)
from ayo_copilot.llm.check.scenarios import build_scenarios
from ayo_copilot.llm.fake import invalid_tool_call, text_response, tool_call, tool_calls_response

SCENARIOS = build_scenarios()
S = {s.id: s for s in SCENARIOS}
SUBSET = [S["greeting"], S["understand_confirmed"]]
SECRET = "texto confidencial del modelo: presión 4,2 bar"
MODEL_A = "mistralai/mistral-small-3.2-24b-instruct"
MODEL_B = "qwen/qwen3-32b"


class ScriptedProvider:
    """Like FakeLLMProvider, but a scripted item can be an exception to raise."""

    def __init__(self, items: Sequence[LLMResponse | Exception]) -> None:
        self.items = list(items)
        self.models: list[str | None] = []

    def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: str = "auto",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.models.append(model)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def with_usage(response: LLMResponse, **fields: Any) -> LLMResponse:
    usage = Usage(**{k: fields.pop(k) for k in list(fields) if k in Usage.__dataclass_fields__})
    return replace(response, usage=usage, **fields)


def transition() -> LLMResponse:
    return tool_calls_response(
        tool_call("propose_transition", {"target_state": "challenge", "reasoning": SECRET})
    )


def rate_limited() -> LLMRateLimitError:
    error = LLMRateLimitError("OpenRouter returned HTTP 429 (rate limited)", status=429)
    error.attempts = 3
    error.generation_ids = ("gen-x",)
    return error


def script_a() -> list[LLMResponse | Exception]:
    """Model A: greeting pass (truncated) + fail (invalid JSON, wrong tool); confirmed pass +
    error."""
    return [
        with_usage(
            text_response(f"¡Hola! {SECRET}"),
            prompt_tokens=100,
            completion_tokens=10,
            cost=0.001,
            latency_ms=100,
            finish_reason="length",
            upstream_provider="Mistral",
        ),
        with_usage(
            tool_calls_response(invalid_tool_call("record_field", f'{{"value": "{SECRET}"')),
            prompt_tokens=200,
            completion_tokens=20,
            latency_ms=300,
            upstream_provider="Mistral",
        ),
        with_usage(
            transition(),
            prompt_tokens=300,
            completion_tokens=30,
            reasoning_tokens=6,
            cost=0.003,
            latency_ms=200,
            upstream_provider="DeepInfra",
            generation_id="gen-a4",
        ),
        rate_limited(),
    ]


def script_b() -> list[LLMResponse | Exception]:
    return [text_response("Hola"), text_response("Hola"), transition(), transition()]


def run_both() -> tuple[ScriptedProvider, list[RunResult]]:
    provider = ScriptedProvider(script_a() + script_b())
    results = run_check(provider, models=[MODEL_A, MODEL_B], scenarios=SUBSET, runs=2)
    return provider, results


# --- Running ----------------------------------------------------------------


def test_planned_calls() -> None:
    assert planned_calls([MODEL_A, MODEL_B], SCENARIOS, 3) == 54


def test_runs_every_model_scenario_and_run_in_order() -> None:
    seen: list[tuple[str, str, int]] = []
    provider = ScriptedProvider(script_a() + script_b())

    results = run_check(
        provider,
        models=[MODEL_A, MODEL_B],
        scenarios=SUBSET,
        runs=2,
        on_result=lambda r: seen.append((r.model, r.scenario_id, r.run)),
    )

    expected = [(m, s.id, run) for m in (MODEL_A, MODEL_B) for s in SUBSET for run in (1, 2)]
    assert seen == expected
    assert [(r.model, r.scenario_id, r.run) for r in results] == expected
    assert provider.models == [MODEL_A] * 4 + [MODEL_B] * 4


def test_run_results() -> None:
    _, results = run_both()

    first, second, third, fourth = results[:4]
    assert first.passed is True
    assert first.finish_reason == "length"
    assert second.passed is False
    assert second.failures == ("invalid_json", "wrong_tool")
    assert third.passed is True
    assert third.tool_names == ("propose_transition",)
    assert third.generation_id == "gen-a4"
    assert fourth.passed is None
    assert fourth.error == "LLMRateLimitError"
    assert fourth.attempts == 3
    assert fourth.generation_id == "gen-x"


def test_runs_must_be_positive() -> None:
    with pytest.raises(ValueError, match="runs"):
        run_check(ScriptedProvider([]), models=[MODEL_A], scenarios=SUBSET, runs=0)


# --- Metrics ----------------------------------------------------------------


def test_model_metrics_are_exact() -> None:
    _, results = run_both()
    prices = {MODEL_A: Pricing(prompt=1e-6, completion=2e-6)}

    summary_a, summary_b = summarize(results, SUBSET, prices=prices)

    assert summary_a.model == MODEL_A
    assert summary_a.runs == 4
    assert summary_a.errors == 1
    assert summary_a.error_types == {"LLMRateLimitError": 1}
    assert (summary_a.pass_rate.successes, summary_a.pass_rate.total) == (2, 3)
    assert summary_a.pass_rate.value == pytest.approx(0.6667)
    assert summary_a.tool_calls == 2
    assert (summary_a.bad_argument_rate.successes, summary_a.bad_argument_rate.total) == (1, 2)
    assert summary_a.truncated == 1
    assert summary_a.latency_p50_ms == 200
    assert summary_a.latency_p95_ms == 300
    assert summary_a.avg_prompt_tokens == 200
    assert summary_a.avg_completion_tokens == 20
    assert summary_a.avg_reasoning_tokens == 6
    assert summary_a.avg_cost_reported == pytest.approx(0.002)
    # (100e-6 + 20e-6, 200e-6 + 40e-6, 300e-6 + 60e-6) / 3
    assert summary_a.avg_cost_estimated == pytest.approx(2.4e-4)
    assert summary_a.upstream_providers == {"Mistral": 2, "DeepInfra": 1}

    assert summary_b.pass_rate.value == 1.0
    assert summary_b.errors == 0
    assert summary_b.avg_cost_estimated is None  # no prices for it
    assert summary_b.bad_argument_rate.value == 0.0


def test_scenario_metrics() -> None:
    _, results = run_both()

    (summary_a, _) = summarize(results, SUBSET)
    greeting, confirmed = summary_a.scenarios

    assert greeting.scenario_id == "greeting"
    assert (greeting.runs, greeting.errors) == (2, 0)
    assert (greeting.pass_rate.successes, greeting.pass_rate.total) == (1, 2)
    assert greeting.failures == {"invalid_json": 1, "wrong_tool": 1}
    assert (confirmed.runs, confirmed.errors) == (2, 1)
    assert (confirmed.pass_rate.successes, confirmed.pass_rate.total) == (1, 1)
    assert confirmed.failures == {}


def test_only_errors_give_no_rate() -> None:
    provider = ScriptedProvider([rate_limited()])
    results = run_check(provider, models=[MODEL_A], scenarios=[S["greeting"]], runs=1)

    (summary,) = summarize(results, [S["greeting"]])

    assert summary.pass_rate.value is None
    assert summary.pass_rate.low is None
    assert summary.bad_argument_rate.value is None
    assert summary.latency_p50_ms is None
    assert summary.avg_prompt_tokens is None


@pytest.mark.parametrize(
    ("successes", "total", "low", "high"),
    [
        (0, 3, 0.0, 0.5615),
        (3, 3, 0.4385, 1.0),
        (22, 27, 0.6330, 0.9182),
        (25, 27, 0.7663, 0.9794),
        (5, 10, 0.2366, 0.7634),
    ],
)
def test_wilson_interval(successes: int, total: int, low: float, high: float) -> None:
    r = rate(successes, total)

    assert r.low == pytest.approx(low, abs=1e-4)
    assert r.high == pytest.approx(high, abs=1e-4)
    assert r.low <= r.value <= r.high


def test_wilson_interval_is_symmetric_and_rejects_bad_input() -> None:
    low, high = wilson_interval(4, 9)
    other_low, other_high = wilson_interval(5, 9)
    assert low == pytest.approx(1 - other_high)
    assert high == pytest.approx(1 - other_low)
    with pytest.raises(ValueError):
        wilson_interval(1, 0)
    with pytest.raises(ValueError):
        wilson_interval(4, 3)


@pytest.mark.parametrize(
    ("values", "pct", "expected"),
    [
        ([], 50, None),
        ([7.0], 95, 7.0),
        ([3.0, 1.0, 2.0], 50, 2.0),
        ([float(v) for v in range(1, 21)], 95, 19.0),
        ([float(v) for v in range(1, 21)], 50, 10.0),
        ([1.0, 2.0], 0, 1.0),
    ],
)
def test_percentile_nearest_rank(values: list[float], pct: float, expected: float | None) -> None:
    assert percentile(values, pct) == expected


# --- Report -----------------------------------------------------------------

CONFIG = {
    "models": [MODEL_A, MODEL_B],
    "runs": 2,
    "temperature": 0.2,
    "max_tokens": 1024,
    "reasoning_effort": None,
    "data_collection": "deny",
    "zdr": False,
    "started_at": "2026-11-12T10:00:00Z",
    "finished_at": "2026-11-12T10:01:00Z",
}


def report(include_raw: bool = False) -> dict[str, Any]:
    _, results = run_both()
    return build_report(
        config=CONFIG,
        scenarios=SUBSET,
        results=results,
        summaries=summarize(results, SUBSET),
        include_raw=include_raw,
    )


def test_report_structure() -> None:
    data = json.loads(json.dumps(report()))  # JSON-serializable, round-trips

    assert data["report_version"] == 1
    assert data["notice"] == DRAFT_NOTICE
    assert data["config"] == {**CONFIG, "include_raw": False}
    assert [s["id"] for s in data["scenarios"]] == ["greeting", "understand_confirmed"]
    assert data["scenarios"][0]["expectations"]["must_call_none"] is True
    assert data["scenarios"][1]["expectations"]["required_values"] == [
        {"tool": "propose_transition", "field": "target_state", "values": ["challenge"]}
    ]
    model_a = data["models"][0]
    assert model_a["model"] == MODEL_A
    assert model_a["runs_total"] == 4
    assert model_a["pass_rate"] == {
        "successes": 2,
        "total": 3,
        "value": 0.6667,
        "low": 0.2077,
        "high": 0.9385,
    }
    assert model_a["scenarios"][0]["failures"] == {"invalid_json": 1, "wrong_tool": 1}
    runs = model_a["runs_detail"]
    assert len(runs) == 4
    assert runs[1]["failures"] == ["invalid_json", "wrong_tool"]
    assert runs[3]["error"] == "LLMRateLimitError"
    assert "text" not in runs[0]
    assert "raw_arguments" not in runs[1]


def test_report_holds_no_raw_output_by_default() -> None:
    assert SECRET not in json.dumps(report(), ensure_ascii=False)


def test_report_includes_raw_output_when_asked() -> None:
    data = report(include_raw=True)
    runs = data["models"][0]["runs_detail"]

    assert data["config"]["include_raw"] is True
    assert SECRET in runs[0]["text"]
    assert SECRET in runs[1]["raw_arguments"][0]
