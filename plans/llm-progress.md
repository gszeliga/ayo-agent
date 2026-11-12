# LLM provider milestone: plan and progress

The first brick of the conversation engine: an `LLMProvider` interface, an
`OpenRouterProvider`, a scripted `FakeLLMProvider`, settings, and the `ayo-llm-check`
command that measures how reliably candidate models call tools. No endpoint, no
conversation logic. Spec: `plans/claude-code-prompt-llm-provider.md` (untracked, like the
earlier specs; pasted into the session on 2026-11-12). This file holds the agreed
deviations, which win over the spec, the plan and the progress log.

## Next (resume here)
L2: the brief for `OpenRouterProvider` (request building, response parsing, multi-turn
serialization, single-attempt error mapping) and ADR 0003.

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

## Order of work (one commit per step, brief first, stop after each)
- [x] **L1** Types, errors, `LLMProvider` protocol, `check_request`, `FakeLLMProvider`,
  `LLMSettings`, `.env.example` (and a test that it lists every setting), README.
- [ ] **L2** `OpenRouterProvider`: request building (tools, routing preferences, data
  policy, reasoning effort, per-call model), response parsing (invalid arguments never
  raise, reasoning apart), multi-turn serialization, single-attempt error mapping; ADR 0003.
- [ ] **L3** Retries (backoff with jitter, `Retry-After`, total budget, errors in a 200),
  one structured log line per call, privacy tests on every error path.
- [ ] **L4** Lazy wiring into the app (lifespan, `get_llm_provider`), lazy-config tests,
  two live tests, `live` marker wording.
- [ ] **L5** Check core without I/O: the nine draft scenarios (Spanish), expectations,
  schema validation (`jsonschema`, runtime dependency), metrics and report structure.
- [ ] **L6** `ayo-llm-check models|run` CLI, call cap, `eval/llm/` reports (git-ignored
  except an example), README.
- [ ] **L7** Manual run with the user's key; results and the final report; default model
  revisited.

## Open items
- None yet.

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
