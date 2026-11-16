# Development

Tests, the API contract and the tool-calling check. Working conventions are in
[CLAUDE.md](../CLAUDE.md).

## Tests

```sh
uv run pytest                        # everything except `live`; integration tests need Docker
uv run pytest -m "not integration"   # no Docker, no database
uv run pytest -m live                # real calls: Voyage (VOYAGE_API_KEY) and OpenRouter
                                     # (OPENROUTER_API_KEY, LLM_MODEL; 3 tiny requests)
uv run ruff check . && uv run ruff format --check .
```

Integration tests start their own Postgres container (testcontainers), separate from the
dev database, and are skipped with a clear message when Docker is not available. To use
an existing server instead, set `TEST_DATABASE_URL` (a pgvector-enabled Postgres; each
test run creates and drops its own databases). Neon URLs are refused. Tests never read
`.env`, except the `live` ones, which take the API keys (and `LLM_MODEL`) from it. Why this setup: [ADR 0001](decisions/0001-test-database.md).

## API contract

`docs/openapi.json` is the OpenAPI spec, generated from the code and committed, so API
changes show up in review. After changing the API, regenerate it (a test fails until you
do):

```sh
uv run python scripts/export_openapi.py          # --check only verifies
```

The admin UI's API types are generated from `docs/openapi.json`, so an API change also
runs `pnpm gen:api` in `ui/` ([ui/README.md](../ui/README.md)).

## Checking models' tool calling (`ayo-llm-check`)

The copilot will move a case between phases only through tool calls that our code
validates, so a model must call tools reliably: valid JSON, allowed enum values, no
invented tools, no tool call when it should ask instead. `ayo-llm-check` measures that for
candidate models through OpenRouter. Its nine scenarios (`src/ayo_copilot/llm/check/scenarios.py`,
in Spanish) and their system prompts and tools are **drafts that only exercise the
machinery; they are not the production prompts**, which will be written with AYO
consultants. The numbers compare tool-calling discipline, not the quality of the copilot.

**Key.** Create one at <https://openrouter.ai/settings/keys>, add credit (a run costs cents;
free `:free` models are rate limited and usually excluded by `LLM_DATA_COLLECTION=deny`),
and set `OPENROUTER_API_KEY` in `.env`. Check your account's privacy settings for
OpenRouter's own logging of prompts.

```sh
# Free, no key needed: tool support, context, USD per million tokens, ZDR, reasoning.
# Exits 1 if a model is not listed or declares no tool support.
uv run ayo-llm-check models --model mistralai/mistral-small-3.2-24b-instruct --model qwen/qwen3-32b

# Real, billed calls: models x 9 scenarios x runs. Stops before calling if that is above
# --max-calls (default 200) unless --yes. About USD 0.01 for this example.
uv run ayo-llm-check run --models mistralai/mistral-small-3.2-24b-instruct,qwen/qwen3-32b --runs 3

# Options: --scenarios greeting,enum_skip_ahead   --reasoning-effort none|low|...|default
#          --out eval/llm/   --include-raw (also store model text and tool arguments)
```

Other settings come from `LLM_*` as usual (temperature, `max_tokens`, data policy, ZDR);
`--reasoning-effort` overrides `LLM_REASONING_EFFORT` for one run, to compare a reasoning
model with and without it.

**Reading the output.** One progress line per call (`PASS`, `FAIL` with reasons, or `ERROR`
with the exception), then a table per model and a scenario x model table of passes:

- **pass (95% CI)**: runs that met every expectation, out of the runs without a provider
  error, with a 95% Wilson interval. Samples are small: if two models' intervals overlap,
  the check cannot rank them; rerun with more `--runs` if it matters.
- **bad args**: tool calls with invalid JSON or arguments that break the tool's schema
  (enums included), out of all tool calls.
- **errors**: calls that failed at the provider (rate limits, outages, `402`), counted
  apart, not as model failures. **truncated**: answers cut at `LLM_MAX_TOKENS`
  (`finish_reason=length`), typically a reasoning model that spent the budget thinking.
- **p50/p95 ms**, **tokens in/out/reasoning** (averages per call), **cost/call** (what
  OpenRouter reported) and **approx/call** (tokens x listed prices: approximate, the
  serving endpoint may price differently).
- Failure reasons: `invalid_json`, `schema_violation`, `unexpected_tool` (not offered),
  `wrong_tool` (forbidden here, or any tool when none was expected), `missing_tool`,
  `wrong_arguments` (valid, but not what the scenario expects), `missing_text` (no
  question in the text: a crude "?" check).

Each run writes `eval/llm/<UTC timestamp>.json` (git-ignored): the config (models, runs,
scenarios, settings, prices used, times), the scenarios and their expectations, the
summaries, and every run (verdict, failure reasons, tool names, finish reason, latency,
tokens, cost, upstream provider, OpenRouter generation id). It holds no model text or
tool arguments unless `--include-raw`. `eval/llm/example-report.json` shows the format
(from a scripted run, not real models). No pass threshold is enforced anywhere: there is
no validated number yet.
