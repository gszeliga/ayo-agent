# 0003: Language model access through OpenRouter

- Status: accepted (2026-11-12)
- Date: 2026-11-12

## Context

The conversation engine moves a case between phases only through tool calls that our code
validates (for example `propose_transition`), so the model client must preserve tool calls
exactly, never lose a malformed one, and route only to upstream providers that really
honour `tools`. Prompts will hold customer content. The first provider is OpenRouter
(milestone plan and decisions: `plans/llm-progress.md`); the `LLMProvider` protocol keeps
others possible.

## Facts relied on (OpenRouter documentation, read 2026-11-12)

- **Endpoint and auth.** `POST https://openrouter.ai/api/v1/chat/completions`, header
  `Authorization: Bearer <key>`. Optional attribution headers: `HTTP-Referer` and
  `X-OpenRouter-Title` (the older `X-Title` is still accepted).
  <https://openrouter.ai/docs/api-reference/overview>, <https://openrouter.ai/docs/app-attribution>
- **Tools (OpenAI-compatible).** `tools: [{"type": "function", "function": {name,
  description, parameters}}]`; `tool_choice` is `"none"`, `"auto"` (default) or
  `{"type": "function", "function": {"name": ...}}`. `"required"` is **not documented**.
  `parallel_tool_calls` defaults to true for most models. An assistant turn carries
  `tool_calls: [{id, type: "function", function: {name, arguments: <JSON string>}}]` with
  `content` possibly null; a result is `{"role": "tool", "tool_call_id", "content"}`
  (`name` optional). `tools` must be sent again on every follow-up request.
  <https://openrouter.ai/docs/features/tool-calling>
- **Provider routing** (the `provider` object). `require_parameters` (default false): only
  providers that support every parameter in the request. `data_collection` (`"allow"`
  default, or `"deny"`): `deny` excludes providers that store data and may train on it.
  `zdr: true`: only Zero Data Retention endpoints. Also `order` and `allow_fallbacks`
  (default true), not used here. With no provider meeting the requirements, the answer is
  `503`. <https://openrouter.ai/docs/features/provider-routing>
- **Usage.** Always returned now (`usage: {include: true}` is deprecated):
  `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost` (credits),
  `completion_tokens_details.reasoning_tokens`, `prompt_tokens_details.cached_tokens`.
  The top-level `model` is the model actually used; the upstream provider is not in the
  documented non-streaming response, but a top-level `provider` came back in every live
  call (2026-11-12) and is read when present.
  <https://openrouter.ai/docs/use-cases/usage-accounting>
- **Errors.** Body `{"error": {"code", "message", "metadata"?}}`; `400` bad request, `401`
  bad key, `402` no credits, `403` moderation or guardrail, `408` timeout, `429` rate
  limited, `502` model down or invalid answer, `503` no provider meets the routing
  requirements. `Retry-After` comes with `429` and `503`. **Errors can arrive inside a
  `200`**: the status is committed before generation, so a provider failure can be a body
  with only `error` (or `choices[].error`, `finish_reason: "error"`).
  <https://openrouter.ai/docs/api-reference/errors>
- **Reasoning.** Returned in `message.reasoning` (alias `reasoning_content`), never in
  `content`. Reasoning tokens are billed as output tokens and count against `max_tokens`;
  a model that spends the whole budget reasoning returns `200` with `finish_reason:
  "length"` and empty content. Controlled with `reasoning: {effort | max_tokens, exclude,
  enabled}`; `effort: "none"` turns it off unless the model makes it mandatory.
  <https://openrouter.ai/docs/use-cases/reasoning-tokens>
- **Models listing.** `GET /api/v1/models`: per model `id`, `context_length`, `pricing`
  (`prompt`, `completion`: USD per token, as strings), `supported_parameters` (contains
  `tools` when supported), `reasoning` metadata; filters include `supported_parameters`
  and `zdr`. <https://openrouter.ai/docs/api-reference/list-available-models>

## Decision

- **Synchronous client on `httpx2`**, in the style of `VoyageEmbedder`: one shared client,
  connect timeout fixed at 10 s, read timeout from `LLM_TIMEOUT_SECONDS`.
- **`provider.require_parameters: true` on every request**, not only with tools: it also
  makes sure `temperature`, `max_tokens` and `reasoning` are honoured rather than
  silently dropped. Cost: possibly fewer providers per model.
- **`provider.data_collection` from `LLM_DATA_COLLECTION`, default `deny`**; `zdr: true`
  only when `LLM_ZDR=true` (default off: stricter, fewer endpoints, possibly pricier;
  `ayo-llm-check models` reports whether each candidate has a ZDR endpoint). OpenRouter's
  own prompt logging is an account setting, outside this code.
- **`temperature` always sent** (`LLM_TEMPERATURE`, default 0.2): without it the upstream
  provider's default applies (OpenRouter documents 1.0), which varies with routing.
- **`reasoning.effort` only when `LLM_REASONING_EFFORT` is set**; otherwise the model's
  default. Reasoning goes to `LLMResponse.reasoning`, never to `text`, never to logs.
- **`tool_choice: "required"` is sent as is** though undocumented; the live tests show
  Mistral Small 3.2 and Qwen3-32B honour it (2026-11-12). `parallel_tool_calls` is not sent (several calls per turn are
  wanted).
- **Tool arguments are parsed, never trusted, never raised on**: invalid JSON or a
  non-object gives `arguments=None` with a reason that never quotes them; empty arguments
  are `{}`; arguments sent as an object are accepted; a missing call id becomes
  `call_<index>`. History is sent back with each call's raw arguments verbatim.
- **Errors map to our own exceptions** by HTTP status, and an error in a `200` by its
  `code` the same way: `401` auth, `402` credits, `429` rate limit, `408`/`5xx`/timeouts/
  connection errors unavailable, other `4xx` (including `403`) bad request; an empty,
  non-JSON or choice-less body is a response error. Messages hold the status only, never
  the body.
- **Retries** (`LLM_MAX_RETRIES`, `LLM_RETRY_BUDGET_SECONDS`): rate limits and unavailability
  (`408`, `429`, `5xx`, timeouts, connection errors, and the same codes inside a `200`) are
  retried, waiting as `Retry-After` asks (seconds or an HTTP date) or with full-jitter
  exponential backoff capped at 10 s. `400`, `401`, `402` (even with `Retry-After`, which
  OpenRouter only sends for its in-flight budget), `403` and unusable bodies are not. No
  wait or attempt may end past the budget, so a long `Retry-After` fails the call at once.
- **One log line per call** (`ayo_copilot.llm.openrouter`, INFO on success, WARNING on
  failure): models requested and used, upstream provider, attempts and why each retry
  happened, latency, tokens, cost, finish reason, tool count and names (a name that is not
  a plausible tool name is logged as `<invalid>`), and the generation ids. Never content,
  arguments, reasoning, bodies or the key.
- **Generation ids** (the body's `id`, `gen-...`) are kept on `LLMResponse.generation_id`
  and, for every attempt that had one, on the final `LLMError.generation_ids` and in the
  log line, so the usage and cost of any call, failed attempts included, can be looked up
  later (`GET /api/v1/generation?id=...` or the OpenRouter activity page) without storing
  them here. A plain HTTP error carries no id in its documented body, so those attempts
  cannot be traced this way; they are normally rejected before any generation.
- **Default model `mistralai/mistral-small-3.2-24b-instruct`** (provisional): no reasoning
  by default, cheaper output than `qwen/qwen3-32b`, and Mistral itself among its
  providers. To be confirmed with `ayo-llm-check run`.

## Consequences

- A missing key does not stop the app; `complete` raises `LLMConfigError` on use.
- A model with no provider honouring every parameter (or no ZDR endpoint, when required)
  fails with `503` mapped to `LLMUnavailableError`, not with silently degraded answers.
- Reasoning models can spend `max_tokens` on reasoning and return no answer
  (`finish_reason: "length"`); the check command makes that visible per model.
- The orchestrator must resend `tools` with every turn and decide what to do with invalid
  tool arguments (for example, answer the call with an error result).
