# Development

Tests, the API contract and the tool-calling check. Working conventions are in
[CLAUDE.md](../CLAUDE.md).

## Tests

```sh
uv run pytest                        # everything except `live`; integration tests need Docker
uv run pytest -m "not integration"   # no Docker, no database
uv run pytest -m live                # real, billed calls: Voyage (VOYAGE_API_KEY) and OpenRouter
                                     # (OPENROUTER_API_KEY, LLM_MODEL): see "Live tests"
uv run ruff check . && uv run ruff format --check .
```

Integration tests start their own Postgres container (testcontainers), separate from the
dev database, and are skipped with a clear message when Docker is not available. To use
an existing server instead, set `TEST_DATABASE_URL` (a pgvector-enabled Postgres; each
test run creates and drops its own databases). Neon URLs are refused. Tests never read
`.env`, except the `live` ones, which take the API keys (and `LLM_MODEL`) from it. Why
this setup: [ADR 0001](decisions/0001-test-database.md).

### Live tests

`-m live` runs every live test; pick one file to spend less. Each skips without its keys.

| File | What it calls | Cost |
|---|---|---|
| `tests/live/test_voyage_live.py` | Voyage: a few tiny embeddings | negligible |
| `tests/live/test_openrouter_live.py` | OpenRouter: 3 tiny requests | well under USD 0.001 |
| `tests/live/test_conversation_live.py` | A real conversation: 8 fixed messages over HTTP, `LLM_MODEL`, Voyage, a test container database (needs Docker) | 8 to 48 model calls (usually 16 to 20) and a few embeddings |

The conversation test asserts structure only: every message answered, a legal phase at
every step, one trace per turn, only real tool names. A refused tool call is not a
failure (the engine handles it); how well the model follows the phases is for a person to
read in its transcript, written to `eval/conversations/` even when the test fails (the
path is printed with `-s`).

## Converting documents

```sh
uv sync --group convert                     # docling (torch, layout models): not in plain `uv sync`
uv run docling-import-files PATH --tenant T [--out DIR] [-r] [--reconvert] [--dry-run] [-v]
uv run docling-import-files PATH --no-upload  # convert only
```

Details in [knowledge-base.md](knowledge-base.md#converting-and-uploading-documents-with-docling).
Its tests use a fake converter (docling is never imported) and an `httpx2.MockTransport`
for the API (no request leaves the process). A real run uploads through the API, and the
server embeds each new or changed document: billed Voyage calls.

## Conversation transcripts

```sh
uv run ayo-transcript <session_id>             # -> eval/conversations/<UTC time>-<id prefix>.md
uv run ayo-transcript <session_id> --out DIR
```

A readable Markdown file of one copilot session, built from the database (the session in
`DATABASE_URL`, with the same remote guard as the app; it only reads): a header with the
models, prompts version, phase path and totals; per turn the user message, the reply, the
phases, each tool call with its outcome, the annotations recorded, calls, tokens, cost,
duration, retrieval and caps; the final facts, annotations and actions. It holds the
conversation's content, so it is only written to the git-ignored `eval/conversations/`
(never logged or printed: the command prints the file's path). An existing file is never
overwritten.

## Demo cases

```sh
uv run python scripts/seed_demo_cases.py               # local database (DATABASE_URL)
uv run python scripts/seed_demo_cases.py --host HOST   # a remote one: the Neon dev branch only
uv run python scripts/seed_demo_cases.py --embedder voyage  # searchable documents (BILLED)
uv run python scripts/seed_demo_cases.py --reset       # says what it would delete
uv run python scripts/seed_demo_cases.py --reset --yes # deletes it
```

Five Spanish cases for trying the test chat and its inspector without a model call or any
cost: an Analyse case with hypotheses, a discarded one, evidence, refused and accepted
transitions, a retrieval failure and retrieved chunks (one from a deleted document); an
Action case with a done, a pending and an overdue action and a stale AI summary; a closed
case with a current summary; a case from another channel (read-only, a capped turn); an
untitled first turn. They are written through the engine's own path (`resolve_case`,
`commit_turn`), with made-up metrics, then their times are moved back over a few days.

Everything lives in the `demo-acme`, `demo-norte` and `demo-sur` tenants: the cases
(`created_by = demo-seed`) and two fixture documents in `demo-acme`, embedded with the
fake embedder and labelled `fake/document/1024`. Their vectors mean nothing, so a search
under Voyage skips them (`skipped.embedder_mismatch`) and the documents list shows them as
`outdated` (`embedder_changed`); reprocessing one re-embeds it with Voyage (billed).
`--embedder voyage` embeds them with Voyage instead, so search finds them: three billed
calls (the two documents and the one deleted afterwards, about 13 chunks and a few
thousand tokens, well under a tenth of a cent); it needs `VOYAGE_API_KEY`. It
refuses to run twice (reset first). `--reset` deletes the demo cases and every document in
those tenants, nothing else. A host other than localhost is refused unless passed exactly as
`--host` (and the app's `ALLOW_REMOTE_DATABASE` guard still applies); only the host is
printed. Sending a message on a demo case is a real, billed model call.

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

The copilot moves a case between phases only through tool calls that our code
validates, so a model must call tools reliably: valid JSON, allowed enum values, no
invented tools, no tool call when it should ask instead. `ayo-llm-check` measures that for
candidate models through OpenRouter. Its ten scenarios
(`src/ayo_copilot/llm/check/scenarios.py`, in Spanish) offer **the engine's real tools**:
in each scenario's phase, exactly the tools, schemas and enums the copilot offers there,
and a rejected transition comes back with the engine's result. Their system prompts and
texts are **drafts that only exercise the machinery; they are not the production
prompts** (the engine's prompt files, to be written with AYO consultants). The numbers
compare tool-calling discipline, not the quality of the copilot.

**Key.** Create one at <https://openrouter.ai/settings/keys>, add credit (a run costs cents;
free `:free` models are rate limited and usually excluded by `LLM_DATA_COLLECTION=deny`),
and set `OPENROUTER_API_KEY` in `.env`. Check your account's privacy settings for
OpenRouter's own logging of prompts.

```sh
# Free, no key needed: tool support, context, USD per million tokens, ZDR, reasoning.
# Exits 1 if a model is not listed or declares no tool support.
uv run ayo-llm-check models --model mistralai/mistral-small-3.2-24b-instruct --model qwen/qwen3-32b

# Real, billed calls: models x 10 scenarios x runs (60 here). Stops before calling if
# that is above --max-calls (default 200) unless --yes. Cents for this example.
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
