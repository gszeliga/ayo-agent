import io
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest

from ayo_copilot.config import LLMSettings
from ayo_copilot.llm import LLMProvider, LLMRateLimitError, LLMResponse
from ayo_copilot.llm.check.catalog import CatalogError, ModelInfo, fetch_catalog
from ayo_copilot.llm.check.cli import Deps, main
from ayo_copilot.llm.check.report import REPORT_VERSION, build_report
from ayo_copilot.llm.check.runner import run_check, summarize
from ayo_copilot.llm.check.scenarios import build_scenarios
from ayo_copilot.llm.fake import FakeLLMProvider, text_response, tool_call, tool_calls_response

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KEY = "sk-or-v1-cli-test-key"
MISTRAL = "mistralai/mistral-small-3.2-24b-instruct"
QWEN = "qwen/qwen3-32b"
SECRET = "salida confidencial del modelo"
SCENARIO_COUNT = len(build_scenarios())

CATALOG = {
    MISTRAL: ModelInfo(MISTRAL, True, 256000, 1e-7, 3e-7, True, "-"),
    QWEN: ModelInfo(QWEN, True, 131072, 8e-8, 2.8e-7, True, "optional"),
    "old/no-tools": ModelInfo("old/no-tools", False, 4096, 1e-6, 1e-6, False, "-"),
}


class Recording:
    """Builds providers for the command and remembers the settings it was given."""

    def __init__(self, make: Callable[[], LLMProvider]) -> None:
        self.make = make
        self.settings: list[LLMSettings] = []
        self.providers: list[LLMProvider] = []

    def __call__(self, settings: LLMSettings) -> LLMProvider:
        self.settings.append(settings)
        provider = self.make()
        self.providers.append(provider)
        return provider


class AlwaysRateLimited:
    def complete(self, **kwargs: Any) -> LLMResponse:
        raise LLMRateLimitError("OpenRouter returned HTTP 429 (rate limited)", status=429)


def answers(count: int) -> FakeLLMProvider:
    """Text with a question every time: passes the no-tool scenarios, fails the others."""
    return FakeLLMProvider([text_response(f"¿Puedes darme más datos? {SECRET}")] * count)


def make_deps(
    *,
    key: str | None = KEY,
    builder: Recording | None = None,
    catalog: dict[str, ModelInfo] | Exception = CATALOG,
) -> tuple[Deps, io.StringIO, Recording]:
    out = io.StringIO()
    recording = builder or Recording(lambda: answers(500))

    def settings() -> LLMSettings:
        return LLMSettings(_env_file=None, openrouter_api_key=key)

    def get_catalog(_: LLMSettings) -> dict[str, ModelInfo]:
        if isinstance(catalog, Exception):
            raise catalog
        return catalog

    deps = Deps(
        settings=settings,
        build_provider=recording,
        catalog=get_catalog,
        now=lambda: datetime(2026, 11, 12, 10, 30, 0, tzinfo=UTC),
        stdout=out,
    )
    return deps, out, recording


@pytest.fixture(autouse=True)
def no_key_in_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# --- models -----------------------------------------------------------------


def test_models_lists_tools_context_prices_and_zdr() -> None:
    deps, out, _ = make_deps()

    code = main(["models", "--model", MISTRAL, "--model", QWEN], deps=deps)

    assert code == 0
    text = out.getvalue()
    assert MISTRAL in text
    assert "256,000" in text
    assert "0.100" in text  # USD per million prompt tokens
    assert "0.280" in text
    assert "optional" in text


def test_models_defaults_to_llm_model() -> None:
    deps, out, _ = make_deps()

    assert main(["models"], deps=deps) == 0
    assert MISTRAL in out.getvalue()


@pytest.mark.parametrize("model", ["old/no-tools", "made/up"])
def test_models_fails_without_tools_or_listing(model: str) -> None:
    deps, out, _ = make_deps()

    assert main(["models", "--model", MISTRAL, "--model", model], deps=deps) == 1
    assert "not listed or declare no tool support" in out.getvalue()


def test_models_reports_a_listing_failure() -> None:
    deps, out, _ = make_deps(catalog=CatalogError("OpenRouter models listing returned HTTP 503"))

    assert main(["models"], deps=deps) == 2
    assert "HTTP 503" in out.getvalue()


# --- catalog ----------------------------------------------------------------


def listing(models: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": models}


def test_fetch_catalog_parses_the_listing_without_a_key() -> None:
    requests: list[httpx2.Request] = []
    full = listing(
        [
            {
                "id": QWEN,
                "context_length": 131072,
                "pricing": {"prompt": "0.00000008", "completion": "0.00000028"},
                "supported_parameters": ["tools", "tool_choice", "reasoning"],
                "reasoning": {"mandatory": False},
            },
            {
                "id": "x/mandatory",
                "context_length": None,
                "pricing": {"prompt": "nope"},
                "supported_parameters": ["temperature"],
                "reasoning": {"mandatory": True, "default_enabled": True},
            },
            {"id": "x/default-on", "reasoning": {"default_enabled": True}},
            {"no": "id"},
        ]
    )
    zdr_only = listing([{"id": QWEN}])

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        zdr = request.url.params.get("zdr") == "true"
        return httpx2.Response(200, json=zdr_only if zdr else full)

    client = httpx2.Client(
        base_url="https://or.test/api/v1", transport=httpx2.MockTransport(handler)
    )
    catalog = fetch_catalog(client)

    qwen = catalog[QWEN]
    assert qwen.tools is True
    assert qwen.context_length == 131072
    assert qwen.prompt_price == pytest.approx(8e-8)
    assert qwen.completion_price == pytest.approx(2.8e-7)
    assert qwen.pricing is not None
    assert qwen.zdr is True
    assert qwen.reasoning == "optional"
    other = catalog["x/mandatory"]
    assert (other.tools, other.zdr, other.reasoning) == (False, False, "mandatory")
    assert other.context_length is None
    assert other.pricing is None
    assert catalog["x/default-on"].reasoning == "default on"
    assert len(catalog) == 3
    assert all("authorization" not in r.headers for r in requests)
    assert {str(r.url) for r in requests} == {
        "https://or.test/api/v1/models",
        "https://or.test/api/v1/models?zdr=true",
    }


@pytest.mark.parametrize(
    "response",
    [httpx2.Response(500), httpx2.Response(200, content=b"<html>"), httpx2.Response(200, json=[])],
)
def test_fetch_catalog_errors(response: httpx2.Response) -> None:
    client = httpx2.Client(
        base_url="https://or.test/api/v1", transport=httpx2.MockTransport(lambda r: response)
    )
    with pytest.raises(CatalogError):
        fetch_catalog(client)


# --- run --------------------------------------------------------------------


def test_run_stops_above_max_calls_without_calling(tmp_path: Path) -> None:
    deps, out, recording = make_deps()

    code = main(
        ["run", "--models", f"{MISTRAL},{QWEN}", "--runs", "20", "--out", str(tmp_path)],
        deps=deps,
    )

    planned = 2 * SCENARIO_COUNT * 20
    assert code == 2
    assert f"= {planned} calls" in out.getvalue()
    assert "above --max-calls 200" in out.getvalue()
    assert recording.providers == []
    assert list(tmp_path.iterdir()) == []


def test_run_stops_without_a_key(tmp_path: Path) -> None:
    deps, out, recording = make_deps(key=None)

    code = main(["run", "--models", MISTRAL, "--runs", "1", "--out", str(tmp_path)], deps=deps)

    assert code == 2
    assert "OPENROUTER_API_KEY is not set" in out.getvalue()
    assert recording.providers == []


def test_yes_lifts_the_cap(tmp_path: Path) -> None:
    deps, _, recording = make_deps()

    code = main(
        [
            "run",
            "--models",
            MISTRAL,
            "--runs",
            "2",
            "--max-calls",
            "3",
            "--yes",
            "--out",
            str(tmp_path),
        ],
        deps=deps,
    )

    assert code == 0
    (provider,) = recording.providers
    assert isinstance(provider, FakeLLMProvider)
    assert len(provider.calls) == 2 * SCENARIO_COUNT


def test_unknown_scenarios_are_refused(tmp_path: Path) -> None:
    deps, out, recording = make_deps()

    code = main(["run", "--models", MISTRAL, "--scenarios", "greeting,nope"], deps=deps)

    assert code == 2
    assert "unknown scenarios ['nope']" in out.getvalue()
    assert recording.providers == []


def run_small(
    tmp_path: Path, *extra: str, builder: Recording | None = None
) -> tuple[int, str, Recording]:
    deps, out, recording = make_deps(builder=builder)
    code = main(
        [
            "run",
            "--models",
            f"{MISTRAL},{QWEN}",
            "--runs",
            "2",
            "--scenarios",
            "greeting,understand_vague,understand_confirmed",
            "--out",
            str(tmp_path),
            *extra,
        ],
        deps=deps,
    )
    return code, out.getvalue(), recording


def test_run_writes_the_report_and_prints_the_tables(tmp_path: Path) -> None:
    code, text, recording = run_small(tmp_path)

    assert code == 0
    (provider,) = recording.providers
    assert isinstance(provider, FakeLLMProvider)
    assert [c.model for c in provider.calls] == [MISTRAL] * 6 + [QWEN] * 6
    assert "Plan: 2 model(s) x 3 scenario(s) x 2 run(s) = 12 calls" in text
    assert f"[1/12] {MISTRAL} understand_vague #1 PASS" in text
    assert f"[3/12] {MISTRAL} understand_confirmed #1 FAIL missing_tool" in text
    assert "67% (" in text  # 4 of 6 runs pass per model
    assert "understand_confirmed  0/2" in text
    assert "Failures:" in text
    assert "Draft scenarios" in text
    (path,) = tmp_path.iterdir()
    assert path.name == "20261112T103000Z.json"
    assert f"Report: {path}" in text

    report = json.loads(path.read_text())
    config = report["config"]
    assert config["models"] == [MISTRAL, QWEN]
    assert config["runs"] == 2
    # The scenarios keep their fixed order, whatever the order of --scenarios.
    assert config["scenarios"] == ["understand_vague", "understand_confirmed", "greeting"]
    assert config["planned_calls"] == 12
    assert config["data_collection"] == "deny"
    assert config["reasoning_effort"] is None
    assert config["prices_per_token"][MISTRAL] == {"prompt": 1e-7, "completion": 3e-7}
    assert config["started_at"] == "2026-11-12T10:30:00Z"
    assert config["include_raw"] is False
    assert [m["model"] for m in report["models"]] == [MISTRAL, QWEN]
    assert report["models"][0]["pass_rate"]["successes"] == 4
    assert SECRET not in path.read_text()
    assert KEY not in path.read_text()
    assert KEY not in text


def test_include_raw_stores_model_output(tmp_path: Path) -> None:
    run_small(tmp_path, "--include-raw")

    (path,) = tmp_path.iterdir()
    assert SECRET in path.read_text()


def test_a_second_report_in_the_same_second_gets_a_suffix(tmp_path: Path) -> None:
    run_small(tmp_path)
    run_small(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "20261112T103000Z-1.json",
        "20261112T103000Z.json",
    ]


@pytest.mark.parametrize(("flag", "expected"), [("none", "none"), ("default", None)])
def test_reasoning_effort_override(tmp_path: Path, flag: str, expected: str | None) -> None:
    _, _, recording = run_small(tmp_path, "--reasoning-effort", flag)

    (settings,) = recording.settings
    assert settings.llm_reasoning_effort == expected


def test_all_errors_exit_one(tmp_path: Path) -> None:
    code, text, _ = run_small(tmp_path, builder=Recording(AlwaysRateLimited))

    assert code == 1
    assert "ERROR LLMRateLimitError" in text
    (path,) = tmp_path.iterdir()
    report = json.loads(path.read_text())
    assert report["models"][0]["errors"] == 6


def test_run_continues_without_the_listing(tmp_path: Path) -> None:
    deps, out, _ = make_deps(catalog=CatalogError("OpenRouter models listing unreachable"))

    code = main(
        [
            "run",
            "--models",
            MISTRAL,
            "--runs",
            "1",
            "--scenarios",
            "greeting",
            "--out",
            str(tmp_path),
        ],
        deps=deps,
    )

    assert code == 0
    assert "no price estimates" in out.getvalue()


def test_run_warns_about_unlisted_or_toolless_models(tmp_path: Path) -> None:
    deps, out, _ = make_deps()

    main(
        [
            "run",
            "--models",
            "made/up,old/no-tools",
            "--runs",
            "1",
            "--scenarios",
            "greeting",
            "--out",
            str(tmp_path),
        ],
        deps=deps,
    )

    text = out.getvalue()
    assert "made/up is not in the models listing" in text
    assert "old/no-tools declares no tool support" in text


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--models", ","],
        ["run", "--models", MISTRAL, "--runs", "0"],
        ["run", "--models", MISTRAL, "--reasoning-effort", "extreme"],
        ["run"],
    ],
)
def test_bad_arguments_exit_two(argv: list[str]) -> None:
    deps, _, _ = make_deps()

    with pytest.raises(SystemExit) as excinfo:
        main(argv, deps=deps)
    assert excinfo.value.code == 2


# --- The committed example report -------------------------------------------


def keys(report: dict[str, Any]) -> dict[str, Any]:
    model = report["models"][0]
    return {
        "top": sorted(report),
        "config": sorted(report["config"]),
        "model": sorted(model),
        "scenario_summary": sorted(model["scenarios"][0]),
        "run": sorted(model["runs_detail"][0]),
    }


def test_the_example_report_matches_the_current_structure(tmp_path: Path) -> None:
    example = json.loads((PROJECT_ROOT / "eval/llm/example-report.json").read_text())
    run_small(tmp_path)
    (path,) = tmp_path.iterdir()
    current = json.loads(path.read_text())

    assert example["report_version"] == REPORT_VERSION
    assert keys(example) == keys(current)


def test_build_report_is_reachable_from_a_fake_run() -> None:
    """Guards the helpers the example report was generated with."""
    scenarios = build_scenarios()[:1]
    provider = FakeLLMProvider([tool_calls_response(tool_call("record_field", {}))])
    results = run_check(provider, models=[MISTRAL], scenarios=scenarios, runs=1)

    report = build_report(
        config={}, scenarios=scenarios, results=results, summaries=summarize(results, scenarios)
    )

    assert report["models"][0]["runs_detail"][0]["failures"] == [
        "schema_violation",
        "wrong_arguments",
    ]
