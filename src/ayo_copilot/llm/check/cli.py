"""`ayo-llm-check`: check how reliably models call tools, through OpenRouter.

    ayo-llm-check models [--model ID ...]
    ayo-llm-check run --models A,B [--runs 3] [--out eval/llm/] [--max-calls 200] [--yes]
                      [--scenarios ID,ID] [--reasoning-effort EFFORT] [--include-raw]

`run` makes real, billed calls: it prints the plan and stops above `--max-calls` unless
`--yes`. The scenarios are drafts (see scenarios.py). Output and reports never hold the
key; reports hold no model output unless `--include-raw`.
"""

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, TextIO, get_args

from ayo_copilot.config import LLMSettings, ReasoningEffort
from ayo_copilot.llm.build import build_llm_provider
from ayo_copilot.llm.check.catalog import CatalogError, ModelInfo, catalog_client, fetch_catalog
from ayo_copilot.llm.check.report import build_report
from ayo_copilot.llm.check.runner import (
    ModelSummary,
    Rate,
    RunResult,
    planned_calls,
    run_check,
    summarize,
)
from ayo_copilot.llm.check.scenarios import build_scenarios
from ayo_copilot.llm.provider import LLMProvider

DEFAULT_OUT = Path("eval/llm")
DEFAULT_MAX_CALLS = 200
EXIT_OK, EXIT_FAILED, EXIT_ABORTED = 0, 1, 2


def _default_catalog(settings: LLMSettings) -> dict[str, ModelInfo]:
    with catalog_client(settings.openrouter_base_url) as client:
        return fetch_catalog(client)


@dataclass
class Deps:
    """What the command talks to; tests replace these."""

    settings: Callable[[], LLMSettings] = LLMSettings
    build_provider: Callable[[LLMSettings], LLMProvider] = build_llm_provider
    catalog: Callable[[LLMSettings], dict[str, ModelInfo]] = _default_catalog
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    stdout: TextIO = field(default_factory=lambda: sys.stdout)


def entrypoint() -> None:
    """The console script: the provider's per-call lines only show on WARNING (errors)."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())


def main(argv: Sequence[str] | None = None, *, deps: Deps | None = None) -> int:
    deps = deps or Deps()
    args = _parser().parse_args(argv)
    out = deps.stdout
    if args.command == "models":
        return _models(args, deps, out)
    return _run(args, deps, out)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ayo-llm-check",
        description="Check how reliably models call tools (OpenRouter). Draft scenarios.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    models = sub.add_parser("models", help="tool support, context, prices and ZDR per model")
    models.add_argument(
        "--model",
        action="append",
        dest="models",
        metavar="ID",
        help="repeatable; default LLM_MODEL",
    )

    run = sub.add_parser("run", help="run the scenarios against models (real, billed calls)")
    run.add_argument("--models", required=True, type=_id_list, help="comma-separated model ids")
    run.add_argument("--runs", type=_positive_int, default=3, help="runs per scenario (default 3)")
    run.add_argument("--out", type=Path, default=DEFAULT_OUT, help="report directory")
    run.add_argument(
        "--max-calls",
        type=_positive_int,
        default=DEFAULT_MAX_CALLS,
        help=f"stop before calling if more are planned (default {DEFAULT_MAX_CALLS})",
    )
    run.add_argument("--yes", action="store_true", help="run even above --max-calls")
    run.add_argument("--scenarios", type=_id_list, help="comma-separated scenario ids")
    run.add_argument(
        "--reasoning-effort",
        choices=[*get_args(ReasoningEffort), "default"],
        help="override LLM_REASONING_EFFORT for this run ('default': the model's own)",
    )
    run.add_argument(
        "--include-raw", action="store_true", help="store model text and tool arguments"
    )
    return parser


def _id_list(value: str) -> list[str]:
    ids = list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    if not ids:
        raise argparse.ArgumentTypeError("expected one or more comma-separated ids")
    return ids


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


# --- models -----------------------------------------------------------------


def _models(args: argparse.Namespace, deps: Deps, out: TextIO) -> int:
    settings = deps.settings()
    ids = list(dict.fromkeys(args.models or [settings.llm_model]))
    try:
        catalog = deps.catalog(settings)
    except CatalogError as exc:
        print(f"error: {exc}", file=out)
        return EXIT_ABORTED
    rows = []
    ok = True
    for model_id in ids:
        info = catalog.get(model_id)
        if info is None:
            ok = False
            rows.append([model_id, "NOT LISTED", "-", "-", "-", "-", "-"])
            continue
        ok = ok and info.tools
        rows.append(
            [
                model_id,
                "yes" if info.tools else "NO",
                f"{info.context_length:,}" if info.context_length else "-",
                _per_million(info.prompt_price),
                _per_million(info.completion_price),
                "yes" if info.zdr else "no",
                info.reasoning,
            ]
        )
    headers = ["model", "tools", "context", "$/M in", "$/M out", "zdr", "reasoning"]
    print(_table(headers, rows), file=out)
    if not ok:
        print("Some models are not listed or declare no tool support.", file=out)
    return EXIT_OK if ok else EXIT_FAILED


def _per_million(price: float | None) -> str:
    return "-" if price is None else f"{price * 1_000_000:.3f}"


# --- run --------------------------------------------------------------------


def _run(args: argparse.Namespace, deps: Deps, out: TextIO) -> int:
    settings = deps.settings()
    if args.reasoning_effort is not None:
        effort = None if args.reasoning_effort == "default" else args.reasoning_effort
        settings = settings.model_copy(update={"llm_reasoning_effort": effort})
    scenarios = build_scenarios()
    if args.scenarios:
        known = {s.id for s in scenarios}
        unknown = [s for s in args.scenarios if s not in known]
        if unknown:
            print(f"error: unknown scenarios {unknown}; known: {sorted(known)}", file=out)
            return EXIT_ABORTED
        scenarios = tuple(s for s in scenarios if s.id in args.scenarios)
    models: list[str] = args.models
    total = planned_calls(models, scenarios, args.runs)

    print(
        f"Plan: {len(models)} model(s) x {len(scenarios)} scenario(s) x {args.runs} run(s)"
        f" = {total} calls. Real calls, billed by OpenRouter.",
        file=out,
    )
    if total > args.max_calls and not args.yes:
        print(
            f"Stopped: {total} calls is above --max-calls {args.max_calls}."
            " Lower --runs, or pass --yes.",
            file=out,
        )
        return EXIT_ABORTED
    if settings.openrouter_api_key is None:
        print("Stopped: OPENROUTER_API_KEY is not set (environment or .env).", file=out)
        return EXIT_ABORTED

    catalog = _catalog_or_empty(deps, settings, out)
    for model in models:
        info = catalog.get(model)
        if info is None:
            print(f"warning: {model} is not in the models listing; no price estimate", file=out)
        elif not info.tools:
            print(f"warning: {model} declares no tool support", file=out)

    provider = deps.build_provider(settings)
    started = deps.now()
    done = 0

    def progress(result: RunResult) -> None:
        nonlocal done
        done += 1
        print(f"[{done}/{total}] {_progress_line(result)}", file=out, flush=True)

    try:
        results = run_check(
            provider, models=models, scenarios=scenarios, runs=args.runs, on_result=progress
        )
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            close()
    finished = deps.now()

    prices = {m: catalog[m].pricing for m in models if m in catalog and catalog[m].pricing}
    summaries = summarize(results, scenarios, prices=prices)
    print("", file=out)
    print(_model_table(summaries), file=out)
    print("", file=out)
    print(_scenario_table(summaries, [s.id for s in scenarios]), file=out)
    for line in _failure_lines(summaries):
        print(line, file=out)
    print(
        "\nDraft scenarios and prompts: these numbers compare tool-calling discipline only."
        " Read the 95% intervals; overlapping intervals cannot rank models. Approximate"
        " costs use the listed prices.",
        file=out,
    )

    config = {
        "models": models,
        "runs": args.runs,
        "scenarios": [s.id for s in scenarios],
        "planned_calls": total,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "reasoning_effort": settings.llm_reasoning_effort,
        "data_collection": settings.llm_data_collection,
        "zdr": settings.llm_zdr,
        "base_url": settings.openrouter_base_url,
        "prices_per_token": {
            m: (
                {"prompt": catalog[m].prompt_price, "completion": catalog[m].completion_price}
                if m in catalog
                else None
            )
            for m in models
        },
        "started_at": _iso(started),
        "finished_at": _iso(finished),
        "ayo_copilot_version": version("ayo-copilot"),
    }
    report = build_report(
        config=config,
        scenarios=scenarios,
        results=results,
        summaries=summaries,
        include_raw=args.include_raw,
    )
    path = _write_report(report, args.out, started)
    print(f"Report: {path}", file=out)
    return EXIT_FAILED if all(r.passed is None for r in results) else EXIT_OK


def _catalog_or_empty(deps: Deps, settings: LLMSettings, out: TextIO) -> dict[str, ModelInfo]:
    try:
        return deps.catalog(settings)
    except CatalogError as exc:
        print(f"warning: {exc}; no price estimates", file=out)
        return {}


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_report(report: dict[str, Any], directory: Path, started: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stem = started.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stem}.json"
    suffix = 1
    while path.exists():
        path = directory / f"{stem}-{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --- Output formatting ------------------------------------------------------


def _progress_line(result: RunResult) -> str:
    if result.passed is None:
        status = f"ERROR {result.error}"
    elif result.passed:
        status = "PASS"
    else:
        status = "FAIL " + ",".join(result.failures)
    latency = f" {result.latency_ms} ms" if result.latency_ms is not None else ""
    return f"{result.model} {result.scenario_id} #{result.run} {status}{latency}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(c)) for c in column) for column in zip(headers, *rows, strict=False)]

    def line(cells: list[str]) -> str:
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths, strict=True)).rstrip()

    return "\n".join([line(headers), line(["-" * w for w in widths]), *map(line, rows)])


def _rate(r: Rate) -> str:
    if r.value is None or r.low is None or r.high is None:
        return "-"
    return f"{r.value:.0%} ({r.low:.0%}-{r.high:.0%}) {r.successes}/{r.total}"


def _number(value: float | None, digits: int = 0) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _usd(value: float | None) -> str:
    return "-" if value is None else f"${value:.6f}"


def _model_table(summaries: Sequence[ModelSummary]) -> str:
    headers = [
        "model",
        "pass (95% CI)",
        "bad args (95% CI)",
        "errors",
        "truncated",
        "p50/p95 ms",
        "tokens in/out/reasoning",
        "cost/call",
        "approx/call",
    ]
    rows = [
        [
            s.model,
            _rate(s.pass_rate),
            _rate(s.bad_argument_rate),
            str(s.errors),
            str(s.truncated),
            f"{_number(s.latency_p50_ms)}/{_number(s.latency_p95_ms)}",
            "/".join(
                _number(v)
                for v in (s.avg_prompt_tokens, s.avg_completion_tokens, s.avg_reasoning_tokens)
            ),
            _usd(s.avg_cost_reported),
            _usd(s.avg_cost_estimated),
        ]
        for s in summaries
    ]
    return _table(headers, rows)


def _scenario_table(summaries: Sequence[ModelSummary], scenario_ids: Sequence[str]) -> str:
    rows = []
    for scenario_id in scenario_ids:
        row = [scenario_id]
        for summary in summaries:
            s = next(x for x in summary.scenarios if x.scenario_id == scenario_id)
            cell = f"{s.pass_rate.successes}/{s.pass_rate.total}"
            if s.errors:
                cell += f" ({s.errors} err)"
            row.append(cell)
        rows.append(row)
    return _table(["scenario", *[s.model for s in summaries]], rows)


def _failure_lines(summaries: Sequence[ModelSummary]) -> list[str]:
    lines = []
    for summary in summaries:
        for s in summary.scenarios:
            if s.failures:
                reasons = ", ".join(f"{reason} x{count}" for reason, count in s.failures.items())
                lines.append(f"  {summary.model} {s.scenario_id}: {reasons}")
    return ["\nFailures:", *lines] if lines else []
