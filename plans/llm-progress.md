# LLM provider milestone: plan and progress

The first brick of the conversation engine: an `LLMProvider` interface, an
`OpenRouterProvider`, a scripted `FakeLLMProvider`, settings, and the `ayo-llm-check`
command that measures how reliably candidate models call tools. No endpoint, no
conversation logic. Spec: `plans/claude-code-prompt-llm-provider.md` (untracked, like the
earlier specs; pasted into the session on 2026-11-12). This file holds the agreed
deviations, which win over the spec, the plan and the progress log.

## Next (resume here)
L6: the brief for the `ayo-llm-check models|run` command (models listing with tools, context,
prices and a ZDR column; the call cap; report files under `eval/llm/`; a clear message for
OpenRouter's "no endpoint matches" 404; README). Credits are on the account (USD 5).

## Decisions (agreed 2026-11-12)
1. **The repo's patterns win over the spec's names.** There is no `HttpEmbedder`: the model
   is `VoyageEmbedder` (sync, shared `httpx2.Client`, injectable `sleep`, response bodies
   dropped from errors). The client is `httpx2`, not `httpx`. There is no `ayo-eval` entry
   point (that harness is parked): `ayo-llm-check` is a new `[project.scripts]` entry.
2. **One commit per step** (the repo's rule), not the spec's "small commits".
3. **`LLMSettings` is its own settings class**, inherited by `Settings` (like
   `DatabaseSettings`), so `ayo-llm-check` runs with only the OpenRouter key: no admin key,
   no database. Nothing in it is required at startup.
4. **Default model `mistralai/mistral-small-3.2-24b-instruct`** (provisional, revisit after
   the L7 run): no reasoning by default, so cheaper and faster per turn than Qwen3-32B, and
   Mistral itself is among its OpenRouter providers.
5. **`LLM_TEMPERATURE=0.2`, always sent.** Leaving it unset would not give the model
   author's recommended value but the upstream provider's default (OpenRouter documents
   1.0), which varies with routing. No way to turn it off.
6. **`LLM_REASONING_EFFORT`**, unset by default (the model's own default); `run` will get a
   `--reasoning-effort` flag to compare. Reasoning is billed as output tokens.
7. **`LLM_ZDR`** (default `false`) next to `LLM_DATA_COLLECTION=deny`: stricter routing,
   possibly fewer providers; the trade-off goes in ADR 0003.
8. **Types are immutable tuples**: `tool_calls` is `tuple[ToolCall, ...]` (lists are
   accepted and converted); the provider interface still takes lists. Two optional
   additions: `LLMResponse.reasoning` and `Usage.reasoning_tokens`. Message content, tool
   arguments, response text and reasoning are left out of `repr`.
9. **`tool_choice: "required"` is kept** though OpenRouter only documents `none`, `auto`
   and a forced function; it is sent as is and the live test shows whether it works.
10. **`FakeLLMProvider` lives in the package** (`ayo_copilot.llm.fake`), like `FakeEmbedder`.
   It rejects malformed requests with the same `check_request` the real provider will use,
   but does not check that scripted calls name offered tools (the check's tests need that).
11. **`provider.require_parameters: true` on every request**, not only when tools are
   offered: it also guarantees `temperature`, `max_tokens` and `reasoning` are honoured.
12. **`parallel_tool_calls` is not sent** (OpenRouter's default, true, is wanted: scenario 1
   expects several `record_field` calls in one turn).
13. **History carries each tool call's raw arguments verbatim**, invalid JSON included; the
   orchestrator decides what to do with invalid calls.
14. **`ayo-llm-check models` also reports whether each model has a ZDR endpoint** (agreed
   2026-11-12), and L7 tries a run with `LLM_ZDR=true`.
15. **An error in a 200 is mapped by its `code`** like an HTTP status (e.g. `502` ->
   `LLMUnavailableError`), keeping `status=200`; with no usable code it is an
   `LLMResponseError`. A missing tool call id becomes `call_<index>`; arguments sent as an
   object are accepted and re-serialized.
16. **Generation ids are logged** (agreed 2026-11-12): `LLMResponse.generation_id`, and on the
   final error `LLMError.generation_ids` for every attempt that had one, so the cost of
   failed or retried calls can be looked up at OpenRouter without storing usage here.
17. **`LLMResponse.latency_ms` is the whole call**, retries and waits included, and
   `LLMResponse.attempts` counts the attempts. The final error carries `attempts` and says
   "after N attempts" when there was more than one.
18. **Retry rules**: `LLMRateLimitError` and `LLMUnavailableError` only (so a `402` with
   `Retry-After` is still not retried); `Retry-After` wins over backoff; backoff is full
   jitter up to 1, 2, 4, ... s, capped at 10 s; no wait may end past the budget (a long
   `Retry-After` fails at once). A request in flight is not cut by the budget.
19. **The provider is built at startup, not lazily** (the spec said "built lazily"):
   building makes no request and checks no key, so only the key check is lazy, which is
   what lets the app run without one. `build_llm_provider` lives in `llm/build.py`.
20. **The live tool test runs twice**, forced by name and with `tool_choice: "required"`
   (answers decision 9): three requests in all.
21. **The check code lives in `llm/check/`** (`scenarios.py`, `evaluate.py`, `runner.py`,
   `report.py`), not `llm/scenarios.py` as the spec said, to keep it apart from the provider
   code the app uses.
22. **Rates carry a 95% Wilson interval** (agreed 2026-11-12): pass rates per model and
   scenario and the bad-argument rate, so small samples are not over-read (22/27 and 25/27
   overlap). Rounded to 4 decimals.
23. **Provider errors are not model failures**: a run that raises `LLMError` is counted as an
   error (by class name) and left out of the pass rate.
24. **"Asks a question" means the text contains "?"**, a labelled heuristic; the meaning of
   the text is not judged. Failure details name tools and schema locations, never values.
25. **Two costs per call**: the average `cost` OpenRouter reported, and an approximate one
   from tokens x listed prices (`None` without prices).

## Order of work (one commit per step, brief first, stop after each)
- [x] **L1** Types, errors, `LLMProvider` protocol, `check_request`, `FakeLLMProvider`,
  `LLMSettings`, `.env.example` (and a test that it lists every setting), README.
- [x] **L2** `OpenRouterProvider`: request building (tools, routing preferences, data
  policy, reasoning effort, per-call model), response parsing (invalid arguments never
  raise, reasoning apart), multi-turn serialization, single-attempt error mapping; ADR 0003.
- [x] **L3** Retries (backoff with jitter, `Retry-After`, total budget, errors in a 200),
  one structured log line per call, privacy tests on every error path.
- [x] **L4** Lazy wiring into the app (lifespan, `get_llm_provider`), lazy-config tests,
  two live tests, `live` marker wording.
- [x] **L5** Check core without I/O: the nine draft scenarios (Spanish), expectations,
  schema validation (`jsonschema`, runtime dependency), metrics and report structure.
- [ ] **L6** `ayo-llm-check models|run` CLI (with a ZDR column in `models`), call cap,
  `eval/llm/` reports (git-ignored except an example), README.
- [ ] **L7** Manual run with the user's key; results and the final report; default model
  revisited.

## Open items
- OpenRouter answers `404` when no endpoint matches the routing or data policy (likely what
  `nvidia/nemotron-3.5-lightning:free` returned with `data_collection=deny`). Today that is a
  generic `LLMBadRequestError` ("request rejected"), hard to diagnose; give it a clear
  message in L6 (it will happen if a model loses its last deny-compatible or ZDR endpoint).
- Qwen3-32B reasons by default and can spend all of `max_tokens` on it: a 16-token
  completion came back empty (`finish_reason=length`). The check must show this; L7 should
  run Qwen3 both with the default and with `--reasoning-effort none`.

## Progress log
- **L1 (2026-11-12).** `src/ayo_copilot/llm/`: `types.py` (`ToolSpec`, `ToolCall`,
  `Message`, `Usage`, `LLMResponse`, each validating itself; content kept out of `repr`),
  `errors.py` (`LLMError` and seven subclasses, with an optional `status`), `provider.py`
  (the sync `LLMProvider` protocol and `check_request`), `fake.py` (`FakeLLMProvider`,
  `RecordedCall`, `FakeLLMExhaustedError`, and the `tool_call` / `invalid_tool_call` /
  `text_response` / `tool_calls_response` helpers). `LLMSettings` in `config.py`;
  `.env.example` LLM section; a new test that `.env.example` lists exactly the settings'
  variables. README configuration table and layout. Tests: `test_llm_types.py`,
  `test_llm_fake.py`, LLM cases in `test_config.py`.
- **L2 (2026-11-12).** `llm/openrouter.py`: `OpenRouterProvider` (one attempt per call;
  missing key -> `LLMConfigError` after `check_request`, before any request), the
  serializers (messages, tools, `tool_choice`), `error_for_status`, `parse_completion` and
  `parse_arguments`. Request: system message first (omitted when empty), temperature and
  `max_tokens` always, `provider: {require_parameters, data_collection[, zdr]}`,
  `reasoning.effort` when set, attribution headers when set. Response: content parts
  joined, empty text -> None, reasoning (or `reasoning_content`) apart, usage with
  reasoning tokens and cost (malformed values -> None), `model` and `provider` when
  present, latency from an injectable clock. ADR `docs/decisions/0003-llm-provider.md`
  with the documentation facts and URLs. Tests: `tests/unit/test_openrouter.py` (request
  building, multi-turn payload, parsing, every error mapping, no secret or content in
  error messages).
- **L3 (2026-11-12).** `OpenRouterProvider` retries (`max_retries`, `retry_budget_seconds`,
  injectable `sleep` and `wall_clock`), `parse_retry_after` (seconds or HTTP date),
  `LLMError` gains `reason` (safe tag: `http_429`, `body_502`, `timeout`, ...),
  `retry_after`, `generation_id`, `attempts`, `generation_ids`; `LLMResponse` gains
  `generation_id` and `attempts`. One log line per call (INFO ok / WARNING error) with
  metadata only; invented tool names logged as `<invalid>`. README retry rows, ADR 0003
  retry/log/generation-id choices, CLAUDE.md convention. Tests:
  `tests/unit/test_openrouter_retries.py` (retryable vs never-retried, bounds, `Retry-After`
  seconds and date, backoff bounds, budget, latency, generation ids, both log lines, and a
  privacy sweep over 14 paths with every logger captured at DEBUG).
- **L4 (2026-11-12).** `llm/build.py`: `build_llm_provider` (every `LLM_*` setting mapped)
  and `describe_llm_provider` (startup line with `key=set|missing`, never the key). The
  lifespan builds the provider, exposes it as `llm`, logs that line and closes the client at
  shutdown; `dependencies.get_llm_provider`. `live` marker reworded. Tests:
  `tests/unit/test_llm_build.py`, two startup tests (no key: app starts, `/health` works,
  calls raise `LLMConfigError`, client closed; startup line without the key), and
  `tests/live/test_openrouter_live.py` (minimal completion; tool call forced by name and
  with `"required"`). **Live run:** the key was accepted but the account has no credits:
  all three calls got `402`, mapped to `LLMInsufficientCreditsError`, not retried, one
  WARNING line each, no content. To rerun once credits are added:
  `uv run pytest -m live tests/live/test_openrouter_live.py`.
- **Live runs (2026-11-12, after the user added USD 5 of credit).** Free models were tried
  first, at no cost: `google/gemma-4-31b-it:free` was rate limited (`429` after retries) and
  `nvidia/nemotron-3.5-lightning:free` gave `404` (probably the data policy). With credits,
  `uv run pytest -m live tests/live/test_openrouter_live.py`:
  - `mistralai/mistral-small-3.2-24b-instruct`: 3/3 passed; tool calls 11 completion tokens,
    0.8-1.3 s; served by Mistral (text) and DeepInfra (tools).
  - `qwen/qwen3-32b` (reasoning by default): tool calls passed (95-125 completion tokens, of
    which 85-111 reasoning; 7.5-15.7 s), the 16-token completion failed (all reasoning,
    `finish_reason=length`, no text).
  - `qwen/qwen3-32b` with `LLM_REASONING_EFFORT=none`: 3/3 passed, 0 reasoning tokens, tool
    calls 20 completion tokens, 2.3-4.4 s.
  - `tool_choice: "required"` is honoured by both models (decision 9 settled).
  - The top-level `provider` is returned in practice, so `upstream_provider` is filled.
  - Total spent: about USD 0.0003.
- **L5 (2026-11-12).** `llm/check/`: `scenarios.py` (draft `record_field`, `log_event`,
  `propose_transition` with a per-scenario enum, `add_action`; draft Spanish prompts per
  phase; nine scenarios with `Expectations`/`ValueRule`), `evaluate.py` (every-call checks
  with `jsonschema` Draft 2020-12, then expectations; seven failure reasons; safe details),
  `runner.py` (`run_check`, `planned_calls`, `RunResult`, `summarize`, `Rate` with
  `wilson_interval`, nearest-rank `percentile`, `Pricing`), `report.py` (`build_report`,
  no raw outputs unless `include_raw`). `jsonschema` is a runtime dependency. ADR 0003 updated
  with the live findings (provider reported, `"required"` honoured). Tests:
  `test_llm_check_scenarios.py`, `test_llm_check_evaluate.py` (a pass and a fail per
  scenario, enum violation, repeated rejected call, several reasons at once),
  `test_llm_check_runner.py` (order, errors apart, exact metrics, intervals, percentiles,
  report structure, raw outputs only on request).
