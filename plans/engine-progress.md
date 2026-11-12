# Conversation engine milestone: plan and progress

The conversation engine core: persistent case state, the phase machine with its guardrail,
the per-turn loop (context, retrieval, LLM, tools, atomic commit), draft prompt files, and
a web channel (`POST /web/messages`, `GET /web/sessions/{session_id}`). Spec:
`plans/claude-code-prompt-conversation-engine.md` (untracked, like the earlier specs;
pasted into the session on 2026-11-12). This file holds the agreed deviations, which win
over the spec, the plan and the progress log.

## Next (resume here)
**E5 done (2026-11-12, commit "Add the conversation storage (E5)"; E1-E5 pushed).** Next is
**E6**: write its brief and wait for approval before coding. The brief must settle
retrieval around a phase change (proposed: once per phase per turn, at the start and after
a hop into a retrieving phase; knowledge dropped on a hop into a phase that does not).
Pending OK, not part of E6: applying migration 0003 to the Neon dev branch.

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
14. **Prompt files** (agreed 2026-11-12): HTML comments (`<!-- -->`) anywhere in a prompt
    file are removed before rendering, so the DRAFT note and editors' notes never reach
    the model. Placeholders come only from code (`$phase`, `$exit_conditions` from
    `TRANSITIONS`; none in `base.md`); everything dynamic (date, case record, knowledge)
    is a separate part added by the context assembly, never substituted into a template.
    Files are rendered once at startup.
15. **`FIELD_MAX_CHARS` is applied when rendering** the case record (E4); the
    `record_field` schema keeps its fixed 500 so the tool specs stay settings-free (the
    check imports them).
16. **Phase glossary is a prompt file** (agreed 2026-11-12): `glossary.md`, no
    placeholders, the last part of every system prompt; the startup log says `files=7`.
17. **Hypotheses in the case record** (agreed 2026-11-12): the data model does not link a
    discarded hypothesis to the one it discards, so the record lists "Hipótesis
    registradas" and "Hipótesis descartadas" (one line each) and the model compares them;
    no schema change.
18. **Retrieval query order** (agreed 2026-11-12): `what`, `where`, the latest user
    message, evidence and hypotheses (newest first), cut at 2000 characters, so the oldest
    annotations are lost first (the spec lists the user message last).
19. **Messages after a phase change** (agreed 2026-11-12): the next call gets the new
    phase's stored messages (none yet) plus the current user message, and a line in the
    system prompt saying the phase just changed; E6 drops the turn's earlier tool exchange
    on a hop, so no call carries tool calls for tools it does not offer.
20. **Message window = the current visit to the phase** (agreed 2026-11-12): a turn's user
    message is stored with the phase the turn started in, its reply with the phase it
    ended in. `build_messages` takes the trailing run of stored messages in the current
    phase (so a reopened phase does not replay its earlier visit), plus the user message
    just before it when the run opens with a reply (the turn that changed phase), then
    caps and trims to a leading user message. `load_snapshot` loads the last
    `CONTEXT_MAX_MESSAGES + 1` messages for that extra one.

## Order of work (one commit per step, brief first, stop after each)
- [x] **E1** Migration 0003 (five tables), migration and constraint tests, `db_pool`
  truncates the new tables; this file; the spec saved untracked.
- [x] **E2** Case snapshot, phase machine (transitions, exit criteria, missing items), tools
  module (specs, exposure per phase, generated `propose_transition` enum, schema and
  semantic validation, handlers on the snapshot); unit tests.
- [x] **E3** `ConversationSettings`, `.env.example`; draft prompt files (Spanish); the
  `string.Template` loader failing at startup; unit tests.
- [x] **E4** Context assembly (system prompt parts, delimited data, field hygiene, message
  window), query builder, reply composition; unit tests.
- [x] **E5** Repository: load snapshot, `resolve_case` (race-safe), commit a turn with the
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
- `APP_TIMEZONE` relies on the system time zone database; a slim container image may lack
  it. Add the `tzdata` package when deployment (D1) resumes, if the image needs it.

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
- **E3 (2026-11-12).** `config.py`: `ConversationSettings` (mixed into `Settings`; all
  defaults; `RETRIEVAL_PHASES` comma-separated and limited to non-closed phases, top_k
  1-50, similarity 0-1, `COMMON_TENANT` by the tenant pattern, `APP_TIMEZONE` loaded with
  `zoneinfo`, `LLM_MODEL_BY_PHASE` JSON with non-closed phases and non-empty models,
  `PROMPTS_VERSION` 1-64 non-space characters). `MAX_SEARCH_TOP_K` moved from `schemas`
  to `config` (schemas imports config; still importable from `schemas`).
  `conversation/prompt_files.py`: `load_prompts` -> `PromptSet` (rendered base and phase
  prompts, `sha256` of the files), `PromptError` naming the file only. Six Spanish draft
  files in `conversation/prompts/`, each opening with the DRAFT note in a comment; phase
  files end with `$exit_conditions`. `phases.describe_targets` shared with the
  `propose_transition` description. App lifespan loads the prompts first (before the
  pool), fails with `StartupError("prompts: ...")`, logs
  `prompts: version=... files=6 sha256=<12 hex>`; `get_prompts` dependency. Wheel checked:
  the `.md` files ship. `.env.example`, README (settings table, "Editing the prompt files"),
  CLAUDE.md layout. Tests: settings defaults, parsing and each refusal; real files load
  with nothing left unresolved and no comment; missing, empty, comment-only, non-UTF-8,
  unclosed comment, stray `$`, unknown placeholder (exact message), `$$`, braces; no
  content in errors or reprs; startup loads and logs, and fails on a broken directory.
  Full suite green (1208 passed).
- **E4 (2026-11-12).** `conversation/context.py`: `build_system_prompt` (base, phase
  prompt plus a phase-changed line, Spanish date line from a fixed table, case record in
  `<registro_caso>`, knowledge in `<referencia>` or the empty / failed notice only when a
  `Knowledge` is passed, glossary), `case_record` (four facts always, "(sin registrar)",
  cut to `field_max_chars`; evidence verbatim with indented continuation lines; recorded
  and discarded hypotheses, the latter one line of at most 160; validated causes; actions
  with id or "nueva", owner, due date, status, overdue from `today`), `knowledge_block`
  (`[n] «title» (source_key) · sección: heading`), `neutralize` (cleaned, block tags inside
  values get `TAG_GUARD` instead of `<`), `build_messages` (current phase's stored messages
  plus the user message, capped, first message `user`). `conversation/query.py`:
  `build_query`. `conversation/reply.py`: `compose_reply`, `FALLBACK_REPLY`. `clean_text`
  moved to `case.py`. `prompts/glossary.md` and `PromptSet.glossary` (loader, tests,
  README updated). Tests: `test_conversation_context.py`, `_query.py`, `_reply.py`
  (part order, sections, cut and cleaning, injection only inside the reference block,
  tags in user text neutralized, message window, query order and cut, fallback). Full
  suite green (1239 passed).
- **E5 (2026-11-12).** `db/conversations.py` (SQL; `TraceRecord`, `ToolCallTrace` with the
  name cut to 64, `RetrievedTrace`: content cannot fit in a trace) and
  `conversation/store.py`: `resolve_case` (lookup, then problem + link in a savepoint
  with `on conflict do nothing`; the loser rolls back and reads the winner's link;
  `CaseTenantMismatch` creates nothing), `load_snapshot` (repeatable read, read only; all
  annotations, last N+1 messages, actions; `CaseNotFound`), `commit_turn` (problem update
  first with `version = expected`, else `CaseChanged`; events user message / annotations /
  reply; new actions; status updates scoped to the case; trace with `max(turn_no) + 1`
  under the row lock; `closed_at` on closing), `read_session` (`SessionView` with
  `SessionAction(action, overdue)`). `context.build_messages`: decision 20. Tests:
  `tests/integration/test_conversation_store.py` (create and reuse, other keys, tenant
  mismatch, a 4-thread race and a deterministic forced race, snapshots, write order,
  version only on commit, actions and `closed_at`, another case's action untouched, turn
  numbers, trace JSON without content, stale version and a 2-thread commit race with no
  partial writes, session view); unit tests for the window after a hop and a reopening.
  Full suite green (1260 passed).
