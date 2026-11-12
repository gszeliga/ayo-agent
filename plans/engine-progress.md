# Conversation engine milestone: plan and progress

The conversation engine core: persistent case state, the phase machine with its guardrail,
the per-turn loop (context, retrieval, LLM, tools, atomic commit), draft prompt files, and
a web channel (`POST /web/messages`, `GET /web/sessions/{session_id}`). Spec:
`plans/claude-code-prompt-conversation-engine.md` (untracked, like the earlier specs;
pasted into the session on 2026-11-12). This file holds the agreed deviations, which win
over the spec, the plan and the progress log.

## Next (resume here)
**E1 done (2026-11-12, commit "Add the conversation engine schema (E1)", not pushed).**
Next is **E2**: write its brief and wait for approval before coding. What the brief should
cover (proposed in the plan, not yet approved in detail):
- New package `src/ayo_copilot/conversation/` (the prompts will live in its `prompts/`
  in E3). Pure code, no database, no LLM calls.
- A case snapshot (dataclasses): the case (id, tenant, state, the four fields, version),
  events, actions, plus the changes accepted during the turn (so E5 can commit them).
- Phase machine: the transitions table and exit criteria from the spec, each rejection
  naming what is missing (`missing: ["where", "standard"]`, "no evidence recorded yet").
- Tools module (the single source the check imports in E9): `record_field`, `log_event`,
  `add_action`, `update_action`, `propose_transition`, built as `llm.types.ToolSpec`;
  which tools each phase gets, with `log_event`'s enum restricted per phase and
  `propose_transition`'s enum and description generated from the transitions table;
  `jsonschema` validation, then semantic checks (action belongs to the case, real date);
  results `{"ok": true, ...}` / `{"ok": false, "error", "detail"}`; unknown or not-offered
  tool and `arguments is None` -> error result, not executed; the hop cap
  (`MAX_PHASE_HOPS`) is the engine's job (E6), but the handler should make it easy.
- `field` enum is `where` for the model, stored as `where_`.
- Unit tests per the spec's "Unit" list (transitions, criteria, tools, handlers on a
  snapshot, criteria seeing earlier changes in the same turn, error shapes).
Pending OK, not part of E2: applying migration 0003 to the Neon dev branch.

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

## Order of work (one commit per step, brief first, stop after each)
- [x] **E1** Migration 0003 (five tables), migration and constraint tests, `db_pool`
  truncates the new tables; this file; the spec saved untracked.
- [ ] **E2** Case snapshot, phase machine (transitions, exit criteria, missing items), tools
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
