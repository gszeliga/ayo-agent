# The copilot

How to talk to the copilot and how it behaves: the turn, the phase rules, the tools, the
trace, and how to edit the prompts. Its settings are in
[configuration.md](configuration.md#conversation-engine). Every route here needs the `X-API-Key` header (see [Endpoints](../README.md#endpoints));
`/docs` has every field, status and error `type`.

## Talking to the copilot

The copilot guides a plant team through five phases: **understand** the problem (what,
where, since when, the standard), **challenge** it with evidence, **analyse** the cause,
agree **actions**, then **follow up** until the case is closed. Code checks each phase's
exit criteria; the model proposes the change. Needs `OPENROUTER_API_KEY` (else `503
llm_not_configured`). Every message is a billed model call (one to `MAX_TOOL_ROUNDS`).

```sh
SESSION=$(uuidgen)   # the client generates the session id; keep it for the conversation
curl -s -X POST http://127.0.0.1:8000/copilot/messages \
  -H "X-API-Key: $ADMIN_API_KEY" -H 'Content-Type: application/json' \
  -d "{\"session_id\": \"$SESSION\", \"tenant\": \"cliente-acme\",
       \"text\": \"Tenemos un 4 % de merma en la llenadora de la línea 2\"}"
curl -s http://127.0.0.1:8000/copilot/sessions/$SESSION -H "X-API-Key: $ADMIN_API_KEY"
```

- The first message of a `session_id` opens a case for its `tenant`; later ones continue
  it. Another tenant on the same session is `422 tenant_mismatch`.
- The answer has the `reply`, the `phase` after the turn, `phase_changed` and the
  `tools_used` (names and whether they were accepted, never their values), plus the
  `case_id` behind the session. A session is the web channel's thread; the case is the
  problem it leads to, which other channels (Slack, Google Chat) will reach through
  their own threads. The session view carries the same `case_id`.
- A turn is atomic: on `409` (`case_closed`, or `case_changed` when another message of the
  session was committed meanwhile), `502` (the model failed) or `503`, nothing of the turn
  is stored and the message can be sent again. A failed first message still leaves its
  empty case and link, so the retry continues it.
- A knowledge-base failure does not fail the turn: the copilot says it could not
  consult it. Retrieval runs in `RETRIEVAL_PHASES` (default `analyse`) over the case's
  tenant plus `COMMON_TENANT` (default `ayo`); see [search.md](search.md).
- A turn that closes the case ends there, with no further model call; if the model said
  nothing, the reply is a fixed closing message. A closed case takes no more messages
  (`409 case_closed`): a new problem needs a new `session_id`.
- The session view is for inspection while testing: no prompts, traces or retrieved text.
  `overdue` compares due dates with today in `APP_TIMEZONE`.
- The channel stored for these conversations is `web`; Slack or Google Chat will be other
  channels behind the same engine.

## Inspecting cases

`GET /admin/cases` lists the copilot's cases from every channel, newest update first,
behind the admin key:

```sh
curl -s "http://127.0.0.1:8000/admin/cases?tenant=cliente-acme&closed=false" \
  -H "X-API-Key: $ADMIN_API_KEY"
```

- Filters: `tenant`, `phase`, `closed` (`true` or `false`) and `q`, a case-insensitive
  substring of `what` (`%` and `_` match themselves). Pages with `limit` (1-100, default
  25) and `offset`; `total` counts every match.
- A case has no title of its own: `title` is `what` on one line, cut to 80 characters, and
  null until the copilot records it.
- Each row has the turn count, the pending and overdue action counts (overdue as in the
  session view), the open, last-update and closing times, and `web_session_id`: the web
  session to keep talking in, null for a case opened from another channel.
- A case left by a failed first message is listed too, with no turns.
- `q` is never logged: the access log drops query strings (see
  [Logs](operations.md#logs)).

`GET /admin/cases/{case_id}` returns one case from any channel: the header (tenant,
title, phase, version, turn count, times, `web_session_id`), the four facts, the
annotations, the actions, with `overdue` computed as in the session view, and the AI
summary. An unknown id is `404 case_not_found`, a malformed one `422`.

`summary` is null until one is generated (on request only, never by a turn). It carries
the text, the model, `generated_at`, `source_version` (the case `version` it was made
from) and `stale`, true once a turn has been committed after it. Summaries live in their
own table (`case_summaries`, one per case): storing one never changes the case's `version`
or `updated_at`, so it cannot cause `409 case_changed` or reorder the listing. Of two
generations racing, the one that read the later case version is kept.

`POST /admin/cases/{case_id}/summary` generates it. **Each call is one billed model
call**:

```sh
curl -s -X POST "http://127.0.0.1:8000/admin/cases/$CASE_ID/summary" \
  -H "X-API-Key: $ADMIN_API_KEY"
```

- The model (`SUMMARY_MODEL`, else `LLM_MODEL`) gets `summary.md`, today's date, the
  phase, the case record (the same block a turn sees) and the latest
  `SUMMARY_MAX_MESSAGES` messages in a `<conversacion>` block (both marked as data, never
  instructions), with a fixed request as the only user message and no tools; the answer
  is capped at `SUMMARY_MAX_TOKENS`.
- `200` returns the summary now stored (as in `get_case`); it records the model,
  `SUMMARY_PROMPTS_VERSION`, tokens and cost.
- `409 case_empty`: the case has no turns, and no call is made. `404 case_not_found`
  also when the case is deleted during the call (nothing is stored).
- Model failures answer as in `/copilot` (`502 llm_*`, `503 llm_not_configured`); an
  empty answer is `502 llm_error`. A failure leaves the previous summary in place.
- The log has one line (`case summary case_id=... tenant=... source_version=...
  stored=...`) and the provider's metadata line; never the prompt or the summary. The conversation and the turn traces
are not part of it: they come in pages of turns, so a long case never loads at once. The
admin view is cross-tenant: there is no tenant parameter.

`GET /admin/cases/{case_id}/turns` pages through a case's turns, oldest first (`limit`
1-50, default 20; `offset`; `total` is the turn count):

- Each item is one committed turn: `turn`, `phase_before`, `phase_after`, the user's
  message, the reply and the trace (model, prompts version, calls, tokens, cost, duration,
  `capped`, `retrieval_error`, the tool calls with outcome, `target` and `missing`, and
  the retrieved chunks with `chunk_id`, `doc_id`, the document's current title,
  `document_deleted` and similarity). No prompts, tool arguments or chunk text.
- Each turn stores exactly one user message and one reply, so the n-th of each is turn n.
- To show the latest turns first, ask for `offset = max(0, total - limit)` and step back
  by `limit`; after a new turn, fetch `offset = total` and append. Turns are only added at
  the end, so earlier pages never move.
- A document deleted since (or not in the case's tenant) shows `document_deleted: true`
  and a null title.

`DELETE /admin/cases/{case_id}` deletes a case for good (`204`; `404 case_not_found` if
there is none, or it was already deleted): its messages, annotations, actions, channel
links and traces go with it, and there is no undo. The log keeps one line with the case
id, tenant and turn count, never content.

- A turn still running on the case stores nothing and answers `409 case_changed`.
- The web session is unlinked: a later message with the same `session_id` opens a new,
  empty case. The test chat starts a new session after a delete.

## The flow of a turn

1. The channel finds the session's case (or opens one with its link) and loads a
   snapshot: the four facts, the annotations, the actions and the latest messages.
   A closed case stops here with `409 case_closed`.
2. In a phase of `RETRIEVAL_PHASES`, the knowledge base is searched once with a query
   built from the case (what, where, the message, the latest evidence and hypotheses).
3. The model is called with the system prompt (base, phase prompt, today's date, the case
   record, the knowledge found, the glossary), the messages of the current visit to the
   phase (at most `CONTEXT_MAX_MESSAGES`) and the phase's tools.
4. Each tool call is checked and applied to the snapshot in memory, and its result goes
   back to the model, which is called again until it answers without tools. If a
   transition is accepted, the next call runs under the new phase's prompt and tools
   (searching again if that phase retrieves). Closing the case ends the turn.
5. `MAX_TOOL_ROUNDS` calls and `TURN_TIMEOUT_SECONDS` cap the turn: the reply then ends
   with a fallback message, and what was accepted is kept.
6. One transaction stores the user message, the annotations, the actions, the new phase,
   the reply and the trace, if the case's version has not changed since the snapshot
   (else `409 case_changed`, nothing stored). A model failure stores nothing either.

## The phase rules

The model proposes a phase change with `propose_transition`; the code accepts it only if
the exit criteria hold, and otherwise answers with what is missing.

| From | To | When |
|---|---|---|
| `understand` | `challenge` | the four facts are recorded: what, where, since, standard |
| `challenge` | `analyse` | at least one evidence is recorded |
| `analyse` | `action` | a validated cause is recorded |
| `action` | `followup` | at least one action, each with an owner and a due date |
| `followup` | `action` | always (to reopen the plan) |
| `followup` | `closed` | at least one action and none pending; sets `closed_at` |

Only the targets of the current phase are offered (the tool's enum is generated from this
table), so the model cannot even name a skip. At most `MAX_PHASE_HOPS` (default 1) change
is accepted per turn; a second one gets `phase_hop_limit`.

## The tools

| Tool | Phases | What it does |
|---|---|---|
| `record_field` | understand, challenge | Records or corrects one of the four facts. |
| `log_event` | challenge, analyse | Records evidence, a hypothesis or a discarded hypothesis; in `analyse` also a validated cause. |
| `add_action` | action, followup | Adds an action with its owner and due date (`YYYY-MM-DD`); it gets its id when the turn is committed. |
| `update_action` | action, followup | Sets a stored action to `pending` or `done`, by the id in the case record. |
| `propose_transition` | every phase but closed | Proposes the next phase, with a reason. |

A call that cannot be applied is not executed; the model gets
`{"ok": false, "error": "<code>", "detail": "..."}` and can correct itself. The codes:
`unknown_tool`, `tool_not_offered`, `invalid_json`, `invalid_arguments` (the JSON
Schema), `invalid_date`, `action_not_found`, `criteria_not_met` (with `missing`) and
`phase_hop_limit`. The response's `tools_used` lists each call with `ok`.

## The turn trace

Every committed turn writes one row to `turn_traces`: turn number, phase before and
after, the models used, `PROMPTS_VERSION`, the number of model calls, token and cost sums
(empty when the provider did not report them), each tool call's name, outcome and error
code (for `propose_transition` also the proposed phase, and on `criteria_not_met` the
missing items as codes such as `evidence` or `since`; traces written before 2026-11-16
lack both), the retrieved chunk ids with their similarity and document, the retrieval error
(`embedding_failed`) if any, whether a cap stopped the turn, and the duration. It never
holds content: no prompts, messages, tool arguments, results or retrieved text. The logs
follow the same rule (one line per turn with the same metadata).

To read a whole conversation with its traces, write its transcript:
`uv run ayo-transcript <session_id>` (see
[Conversation transcripts](development.md#conversation-transcripts)).

## Editing the prompt files

The conversation prompts are Markdown files in `src/ayo_copilot/conversation/prompts/`:
`base.md` (sent in every phase), one per phase (`understand.md`, `challenge.md`,
`analyse.md`, `action.md`, `followup.md`), `glossary.md` (what each phase is for, sent
in every phase so the model understands references to other phases) and `summary.md`
(the case summary, see [Inspecting cases](#inspecting-cases)). The current ones are
**drafts** to make the engine work, to be replaced with AYO's real method.

- Text inside HTML comments (`<!-- ... -->`) is a note for editors: it is removed before
  the prompt reaches the model.
- Phase files may use two placeholders, filled in by the code: `$phase` (the phase name)
  and `$exit_conditions` (where the case can go from that phase and when, generated from
  the rules the code enforces). `base.md`, `glossary.md` and `summary.md` take none.
  Write a literal dollar sign as `$$`.
- The files are read once, at startup: restart the app after editing. A missing or empty
  file, a stray `$` or an unknown placeholder stops the app with an error naming the file.
- Bump `PROMPTS_VERSION` after any change to the turn prompts, and
  `SUMMARY_PROMPTS_VERSION` after a change to `summary.md` (stored with each summary); the
  startup log prints the version and a hash of all the files
  (`prompts: version=draft-1 files=8 sha256=...`), so an edit without a bump shows.
