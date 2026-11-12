# LLM provider milestone: plan and progress

The first brick of the conversation engine: an `LLMProvider` interface, an
`OpenRouterProvider`, a scripted `FakeLLMProvider`, settings, and the `ayo-llm-check`
command that measures how reliably candidate models call tools. No endpoint, no
conversation logic. Spec: `plans/claude-code-prompt-llm-provider.md` (untracked, like the
earlier specs; pasted into the session on 2026-11-12). This file holds the agreed
deviations, which win over the spec, the plan and the progress log.

## Next (resume here)
L5: the brief for the check core without I/O (the nine draft scenarios, expectations,
schema validation, metrics, report structure). Before L7 the OpenRouter account needs
credits: the L4 live run got `402` (see the log).

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
- [ ] **L5** Check core without I/O: the nine draft scenarios (Spanish), expectations,
  schema validation (`jsonschema`, runtime dependency), metrics and report structure.
- [ ] **L6** `ayo-llm-check models|run` CLI (with a ZDR column in `models`), call cap,
  `eval/llm/` reports (git-ignored except an example), README.
- [ ] **L7** Manual run with the user's key; results and the final report; default model
  revisited.

## Open items
- The OpenRouter account had no credits on 2026-11-12 (live tests: `402`). The live tests
  and the L7 run need credits; whether `tool_choice: "required"` is honoured is still open.

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
