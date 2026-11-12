"""Run the scenarios against models and compute the metrics.

A run that raises `LLMError` is an error (rate limit, outage, ...), not a model failure:
it is reported apart and left out of the pass rate. Rates come with a 95% Wilson interval,
because the samples are small: overlapping intervals mean the check cannot tell the
models apart.
"""

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ayo_copilot.llm.check.evaluate import FAILURE_REASONS, FailureReason, evaluate
from ayo_copilot.llm.check.scenarios import Scenario
from ayo_copilot.llm.errors import LLMError
from ayo_copilot.llm.provider import LLMProvider

# Two-sided 95% normal quantile.
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class RunResult:
    """One call: a model, a scenario, a run number (from 1). `passed` is None on error.
    `text` and `raw_arguments` are kept in memory only; reports omit them by default."""

    model: str
    scenario_id: str
    run: int
    passed: bool | None
    failures: tuple[FailureReason, ...] = ()
    details: tuple[str, ...] = ()
    error: str | None = None  # the LLMError class name
    tool_names: tuple[str, ...] = ()
    tool_calls: int = 0
    bad_argument_calls: int = 0
    finish_reason: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost: float | None = None
    model_used: str | None = None
    upstream_provider: str | None = None
    generation_id: str | None = None
    attempts: int | None = None
    text: str | None = field(default=None, repr=False)
    raw_arguments: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class Pricing:
    """USD per token, from the models listing."""

    prompt: float
    completion: float


def planned_calls(models: Sequence[str], scenarios: Sequence[Scenario], runs: int) -> int:
    return len(models) * len(scenarios) * runs


def run_check(
    provider: LLMProvider,
    *,
    models: Sequence[str],
    scenarios: Sequence[Scenario],
    runs: int,
    on_result: Callable[[RunResult], None] | None = None,
) -> list[RunResult]:
    """Every model x scenario x run, in that order. `on_result` sees each result as it
    comes (for progress output)."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    results = []
    for model in models:
        for scenario in scenarios:
            for run in range(1, runs + 1):
                result = run_once(provider, model=model, scenario=scenario, run=run)
                results.append(result)
                if on_result is not None:
                    on_result(result)
    return results


def run_once(provider: LLMProvider, *, model: str, scenario: Scenario, run: int) -> RunResult:
    try:
        response = provider.complete(
            system=scenario.system,
            messages=list(scenario.messages),
            tools=list(scenario.tools),
            tool_choice="auto",
            model=model,
        )
    except LLMError as exc:
        return RunResult(
            model=model,
            scenario_id=scenario.id,
            run=run,
            passed=None,
            error=type(exc).__name__,
            attempts=exc.attempts,
            generation_id=exc.generation_ids[-1] if exc.generation_ids else None,
        )
    verdict = evaluate(scenario, response)
    usage = response.usage
    return RunResult(
        model=model,
        scenario_id=scenario.id,
        run=run,
        passed=verdict.passed,
        failures=verdict.failures,
        details=verdict.details,
        tool_names=tuple(response.tool_names),
        tool_calls=verdict.tool_calls,
        bad_argument_calls=verdict.bad_argument_calls,
        finish_reason=response.finish_reason,
        latency_ms=response.latency_ms,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cost=usage.cost,
        model_used=response.model,
        upstream_provider=response.upstream_provider,
        generation_id=response.generation_id,
        attempts=response.attempts,
        text=response.text,
        raw_arguments=tuple(c.raw_arguments for c in response.tool_calls),
    )


# --- Metrics ----------------------------------------------------------------


@dataclass(frozen=True)
class Rate:
    """`successes` of `total`, with a 95% Wilson interval; all None when total is 0."""

    successes: int
    total: int
    value: float | None
    low: float | None
    high: float | None


def rate(successes: int, total: int) -> Rate:
    if total == 0:
        return Rate(successes, total, None, None, None)
    low, high = wilson_interval(successes, total)
    return Rate(successes, total, round(successes / total, 4), round(low, 4), round(high, 4))


def wilson_interval(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval: sound for small samples and rates near 0 or 1, where the
    usual normal approximation gives impossible bounds."""
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("need 0 <= successes <= total and total > 0")
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile: always one of the values; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _average(values: Iterable[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


@dataclass(frozen=True)
class ScenarioSummary:
    scenario_id: str
    runs: int
    errors: int
    pass_rate: Rate  # over the runs without error
    failures: dict[str, int]  # runs failing for each reason (a run can count for several)


@dataclass(frozen=True)
class ModelSummary:
    model: str
    runs: int
    errors: int
    error_types: dict[str, int]
    pass_rate: Rate  # over the runs without error
    tool_calls: int
    bad_argument_rate: Rate  # calls with invalid JSON or a schema violation / tool calls
    truncated: int  # runs that stopped at the token limit (finish_reason "length")
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    avg_prompt_tokens: float | None
    avg_completion_tokens: float | None
    avg_reasoning_tokens: float | None
    avg_cost_reported: float | None  # what OpenRouter reported, per call
    avg_cost_estimated: float | None  # APPROXIMATE: tokens x listed prices, per call
    upstream_providers: dict[str, int]
    scenarios: list[ScenarioSummary]


def summarize(
    results: Sequence[RunResult],
    scenarios: Sequence[Scenario],
    *,
    prices: Mapping[str, Pricing] | None = None,
) -> list[ModelSummary]:
    """One summary per model, in the order the models first appear in `results`."""
    models = list(dict.fromkeys(r.model for r in results))
    return [
        _summarize_model(
            model, [r for r in results if r.model == model], scenarios, (prices or {}).get(model)
        )
        for model in models
    ]


def _summarize_model(
    model: str,
    results: list[RunResult],
    scenarios: Sequence[Scenario],
    pricing: Pricing | None,
) -> ModelSummary:
    done = [r for r in results if r.passed is not None]
    tool_calls = sum(r.tool_calls for r in done)
    estimated = (
        [
            r.prompt_tokens * pricing.prompt + r.completion_tokens * pricing.completion
            for r in done
            if r.prompt_tokens is not None and r.completion_tokens is not None
        ]
        if pricing is not None
        else []
    )
    latencies = [float(r.latency_ms) for r in done if r.latency_ms is not None]
    return ModelSummary(
        model=model,
        runs=len(results),
        errors=len(results) - len(done),
        error_types=dict(Counter(r.error for r in results if r.error is not None)),
        pass_rate=rate(sum(1 for r in done if r.passed), len(done)),
        tool_calls=tool_calls,
        bad_argument_rate=rate(sum(r.bad_argument_calls for r in done), tool_calls),
        truncated=sum(1 for r in done if r.finish_reason == "length"),
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        avg_prompt_tokens=_average(r.prompt_tokens for r in done),
        avg_completion_tokens=_average(r.completion_tokens for r in done),
        avg_reasoning_tokens=_average(r.reasoning_tokens for r in done),
        avg_cost_reported=_average(r.cost for r in done),
        avg_cost_estimated=_average(estimated),
        upstream_providers=dict(
            Counter(r.upstream_provider for r in done if r.upstream_provider is not None)
        ),
        scenarios=[_summarize_scenario(s.id, results) for s in scenarios],
    )


def _summarize_scenario(scenario_id: str, results: list[RunResult]) -> ScenarioSummary:
    mine = [r for r in results if r.scenario_id == scenario_id]
    done = [r for r in mine if r.passed is not None]
    failures = Counter(reason for r in done for reason in r.failures)
    return ScenarioSummary(
        scenario_id=scenario_id,
        runs=len(mine),
        errors=len(mine) - len(done),
        pass_rate=rate(sum(1 for r in done if r.passed), len(done)),
        failures={reason: failures[reason] for reason in FAILURE_REASONS if failures[reason]},
    )
