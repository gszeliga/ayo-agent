# Conversation engine milestone: plan and progress

The conversation engine core: persistent case state, the phase machine with its guardrail,
the per-turn loop (context, retrieval, LLM, tools, atomic commit), draft prompt files, and
a web channel (`POST /web/messages`, `GET /web/sessions/{session_id}`). Spec:
`plans/claude-code-prompt-conversation-engine.md` (untracked, like the earlier specs;
pasted into the session on 2026-11-12). This file holds the agreed deviations, which win
over the spec, the plan and the progress log.

## Next (resume here)
**E2 done (2026-11-12, commit "Add the case snapshot, phase machine and tools (E2)", not
pushed).** Next is **E3**: write its brief and wait for approval before coding.
Pending OK, not part of E3: applying migration 0003 to the Neon dev branch.

## Decisions (agreed 2026-11-12)
1. **One commit per step**, brief first, stop after each (the repo's rule), not the spec's
   "small commits".
2. **Phase names follow the spec**: `followup`, not the check's `follow_up`; the check
   scenarios switch to the engine's names when they import the real tools (E9).
3. **Embeddings are Voyage (remote), not local.** "Embedding service stopped" means Voyage
   unreachable: a failing fake in tests, a dead `VOYAGE_BASE_URL` in the manual try.
4. **Web link key**: `channel_type='web'`, `external_channel_id='web'` (constant),
   `external_thread_id=<session_id>`. Using the tenant as the channel id would open a new
   case on a tenant mismatch instead of the `422` the spec asks for.
5. **Sync endpoints** (thread pool), like the provider and the embedder.
   `TURN_TIMEOUT_SECONDS` is checked between calls; a call in flight is bounded by the
   provider's own timeout and retry budget.
6. **Trace `model`**: the distinct models the provider reported, comma-joined in call order
   (a turn can span two phases with different models under `LLM_MODEL_BY_PHASE`).
7. **Error mapping**: every `LLMError` but `LLMConfigError` -> `502` with a stable type per
   class (`llm_unavailable`, `llm_rate_limited`, `llm_credits`, `llm_auth`, `llm_error`);
   `LLMConfigError` -> `503 llm_not_configured`; `409` is `case_closed` or `case_changed`.
8. **Search and LLM layers reused as they are** (`search.search()` already takes `tenants`
   and `min_similarity`; `jsonschema` is already a dependency). Any change to them is
   announced first.
9. **`/web` routes get their own parametrized `401` test**, next to the `/admin` one;
   `/web` does not clash with a UI route.
10. **L7 of the LLM milestone is superseded** (agreed 2026-11-12): it would measure the
    draft tools. The billed check runs once, in E11, against the real tool specs, and the
    default model is revisited then.
11. **Migration 0003 is exactly the spec's schema**, with explicit constraint and index
    names; no extra constraints (e.g. none tying `closed_at` to `state`).
12. **`add_action` accepts past due dates** (agreed 2026-11-12): only a real date is
    required, so the handlers need no clock.
13. **Actions added in a turn have no id until commit** (agreed 2026-11-12): `add_action`
    returns no id and `update_action` only reaches stored actions (the ids in the case
    record); no provisional ids that would change after the commit.

## Order of work (one commit per step, brief first, stop after each)
- [x] **E1** Migration 0003 (five tables), migration and constraint tests, `db_pool`
  truncates the new tables; this file; the spec saved untracked.
- [x] **E2** Case snapshot, phase machine (transitions, exit criteria, missing items), tools
  module (specs, exposure per phase, generated `propose_transition` enum, schema and
  semantic validation, handlers on the snapshot); unit tests.
- [ ] **E3** `ConversationSettings`, `.env.example`; draft prompt files (Spanish); the
  `string.Template` loader failing at startup; unit tests.
- [ ] **E4** Context assembly (system prompt parts, delimited data, field hygiene, message
  window), query builder, reply composition; unit tests.
- [ ] **E5** Repository: load snapshot, `resolve_case` (race-safe), commit a turn with the
  optimistic version check, read a session; integration tests.
- [ ] **E6** Turn engine: model loop, phase hops, caps and timeout, retrieval and its
  failure path, trace, per-phase model; engine tests 1-13.
- [ ] **E7** Channel protocol, web adapter, `/web` router and its key dependency, OpenAPI,
  contract and auth tests, `docs/openapi.json`, `ui/src/api/schema.d.ts`.
- [ ] **E8** Scripted golden path through all five phases; README sections.
- [ ] **E9** `ayo-llm-check` imports the real tool specs; `update_action` scenario (no calls).
- [ ] **E10** Live conversation test and `eval/conversations/` transcript writer (code only).
- [ ] **E11** **Billed**: live test, the three manual conversations, check rerun for both
  models, final report. Call counts and a cost estimate first; wait for the user's OK.

## Open items
- Applying migration 0003 to the Neon dev branch: not done; needs the user's OK.

## Progress log
- **E1 (2026-11-12).** `migrations/versions/0003_conversation_engine.py`: `problems`,
  `problem_events`, `actions`, `conversation_links`, `turn_traces` as in the spec; `text` +
  named `CHECK`s instead of enums (justified in the docstring); named indexes and unique
  keys; downgrade drops in reverse order. `tests/conftest.py`: `db_pool` truncates the new
  tables. `tests/integration/test_migrations.py`: defaults and indexes, each `CHECK`
  rejecting an unknown value, foreign keys per child table, the unique link (another
  channel type allowed), unique turn numbers, cascade delete (other cases untouched),
  downgrade to 0002 keeping documents and upgrading again. "`version` only changes on
  commit" waits for E5. Full suite green (1043 passed).
- **E2 (2026-11-12).** `src/ayo_copilot/conversation/`: `case.py` (`Case`, `Event`,
  `Action` with `is_overdue`, `CaseSnapshot`, `TurnChanges` for the commit; content out of
  every repr; `where` <-> `where_` in `FIELD_COLUMNS`), `phases.py` (`TRANSITIONS` with a
  Spanish condition per target, `missing_for` returning facts by model name or
  `evidence` / `validated_cause` / `action` / `incomplete_actions` / `pending_actions`,
  `describe_missing`), `tools.py` (the five specs with the spec's length limits,
  `tools_for_phase`, `log_event` enum per phase, `propose_transition` enum and description
  generated from the table; `execute_tool`: `unknown_tool`, `tool_not_offered`,
  `invalid_json`, `invalid_arguments` (Draft 2020-12, details capped at 200 chars each and
  sent only to the model), control characters stripped and text trimmed, `invalid_date`,
  `action_not_found`, `criteria_not_met` with `missing`, `phase_hop_limit` when the engine
  passes `allow_transition=False`). Tool descriptions in Spanish, error codes and details
  in English. `update_action` with the same status is `ok` with `changed: false`.
  Tests: `tests/unit/test_conversation_phases.py` and `test_conversation_tools.py` (flat,
  like the rest of `tests/unit/`, not a subfolder as the brief said). Full suite green
  (1154 passed).
- **E2 follow-up (2026-11-12, asked by the user).** `tools.py`: the per-tool dicts
  (`TOOL_NAMES`, `_PHASES_BY_TOOL`, `_TEXT_ARGUMENTS`, the builders in `tools_for_phase`,
  `_HANDLERS`) merged into one table, `TOOLS: tuple[ToolDef, ...]` (name, phases, spec
  builder, handler, text arguments); `TOOL_NAMES` is derived from it. No behaviour change.
  New tests: each entry builds its own spec in every phase it lists, and every free-text
  argument (string without enum or pattern) is in `text_arguments`, so a new one cannot
  skip cleaning.
