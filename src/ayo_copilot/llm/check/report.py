"""The check's JSON report, as a plain dict (the command writes it to a file).

By default it holds no raw model output (text, reasoning or tool arguments): only tool
names, verdicts, failure reasons and their safe details, timings and tokens. Raw outputs
could echo customer-like content once the prompts are real; `include_raw` adds text and
raw arguments for debugging.
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from ayo_copilot.llm.check.runner import ModelSummary, RunResult
from ayo_copilot.llm.check.scenarios import Expectations, Scenario, ValueRule

REPORT_VERSION = 1
DRAFT_NOTICE = (
    "Draft scenarios and prompts: they compare models on tool-calling discipline only and"
    " are not the production prompts. Small samples: read the 95% intervals, not only the"
    " rates. Estimated costs are approximate (tokens x listed prices)."
)

_RUN_FIELDS = (
    "scenario_id",
    "run",
    "passed",
    "failures",
    "details",
    "error",
    "tool_names",
    "tool_calls",
    "bad_argument_calls",
    "finish_reason",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cost",
    "model_used",
    "upstream_provider",
    "generation_id",
    "attempts",
)


def build_report(
    *,
    config: Mapping[str, Any],
    scenarios: Sequence[Scenario],
    results: Sequence[RunResult],
    summaries: Sequence[ModelSummary],
    include_raw: bool = False,
) -> dict[str, Any]:
    """`config` is whatever the command ran with (models, runs, temperature, max_tokens,
    reasoning effort, data policy, zdr, timestamps); it must be JSON-serializable."""
    return {
        "report_version": REPORT_VERSION,
        "notice": DRAFT_NOTICE,
        "config": {**config, "include_raw": include_raw},
        "scenarios": [_scenario(s) for s in scenarios],
        "models": [
            {
                **_summary(summary),
                "runs_detail": [
                    _run(r, include_raw=include_raw) for r in results if r.model == summary.model
                ],
            }
            for summary in summaries
        ],
    }


def _scenario(scenario: Scenario) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "title": scenario.title,
        "phase": scenario.phase,
        "tools": scenario.tool_names,
        "expectations": _expectations(scenario.expectations),
    }


def _rule(rule: ValueRule) -> dict[str, Any]:
    return {"tool": rule.tool, "field": rule.field, "values": sorted(rule.values)}


def _expectations(exp: Expectations) -> dict[str, Any]:
    return {
        "must_call_any": sorted(exp.must_call_any),
        "must_call_none": exp.must_call_none,
        "forbidden_tools": sorted(exp.forbidden_tools),
        "forbidden_values": [_rule(r) for r in exp.forbidden_values],
        "required_values": [_rule(r) for r in exp.required_values],
        "must_cover": _rule(exp.must_cover) if exp.must_cover is not None else None,
        "needs_question": exp.needs_question,
    }


def _summary(summary: ModelSummary) -> dict[str, Any]:
    data = asdict(summary)  # nested dataclasses (Rate, ScenarioSummary) become dicts
    data["runs_total"] = data.pop("runs")
    return data


def _run(result: RunResult, *, include_raw: bool) -> dict[str, Any]:
    data = {name: getattr(result, name) for name in _RUN_FIELDS}
    data["failures"] = list(result.failures)
    data["details"] = list(result.details)
    data["tool_names"] = list(result.tool_names)
    if include_raw:
        data["text"] = result.text
        data["raw_arguments"] = list(result.raw_arguments)
    return data
