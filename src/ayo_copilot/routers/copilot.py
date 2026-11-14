"""The copilot endpoints: talk to the problem-solving agent, and inspect a session.

These are the web channel's endpoints (`conversation.channels.WebAdapter`): the session
id is the conversation. Authentication is **provisional** and its own dependency, so the
channel and admin keys can diverge later; for now both check `ADMIN_API_KEY`.

Sync endpoints (FastAPI's thread pool): a turn makes blocking model and embedding calls.
Logs carry ids, phases and counts only (the engine's turn line); never the messages.
"""

import logging
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Security
from fastapi import Path as PathParam
from fastapi.security import APIKeyHeader
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.conversation.channels import WebAdapter, handle_message, web_key
from ayo_copilot.conversation.engine import CaseClosed, TurnEngine
from ayo_copilot.conversation.prompt_files import PromptSet
from ayo_copilot.conversation.store import CaseChanged, CaseTenantMismatch, read_session
from ayo_copilot.dependencies import (
    get_embedder,
    get_llm_provider,
    get_pool,
    get_prompts,
    get_settings,
)
from ayo_copilot.errors import ApiError
from ayo_copilot.ingestion.embedding import Embedder
from ayo_copilot.llm import LLMProvider
from ayo_copilot.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMInsufficientCreditsError,
    LLMRateLimitError,
    LLMUnavailableError,
)
from ayo_copilot.schemas import (
    SESSION_ID_EXAMPLE,
    CopilotMessageRequest,
    CopilotMessageResponse,
    CopilotSession,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="CopilotApiKey",
    description="Provisional key of the copilot endpoints (for now the same value as"
    " `ADMIN_API_KEY`).",
    auto_error=False,
)


def _error(type: str, loc: list[str | int], msg: str, **extra: object) -> dict[str, object]:
    return {"detail": [{"type": type, "loc": loc, "msg": msg, **extra}]}


def _examples(**examples: tuple[str, dict[str, object]]) -> dict[str, object]:
    """OpenAPI `content` with named JSON examples: name -> (summary, value)."""
    return {
        "application/json": {
            "examples": {
                name: {"summary": summary, "value": value}
                for name, (summary, value) in examples.items()
            }
        }
    }


def require_copilot_key(
    key: Annotated[str | None, Security(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    expected = settings.admin_api_key.get_secret_value().encode()
    # Bytes, because compare_digest refuses non-ASCII str.
    if key is None or not secrets.compare_digest(key.encode(), expected):
        raise ApiError(
            401,
            "invalid_api_key",
            "invalid or missing API key",
            ["header", "x-api-key"],
            headers={"WWW-Authenticate": "APIKey"},
        )


def get_turn_engine(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    settings: Annotated[Settings, Depends(get_settings)],
    prompts: Annotated[PromptSet, Depends(get_prompts)],
) -> TurnEngine:
    """A turn engine over the app's resources (cheap: it holds no per-turn state)."""
    return TurnEngine(pool, llm, embedder, settings, prompts)


router = APIRouter(
    prefix="/copilot",
    tags=["copilot"],
    dependencies=[Depends(require_copilot_key)],
    responses={
        401: {
            "model": ErrorResponse,
            "description": "`X-API-Key` is missing or wrong.",
            "content": _examples(
                invalid_api_key=(
                    "Missing or wrong key",
                    _error(
                        "invalid_api_key", ["header", "x-api-key"], "invalid or missing API key"
                    ),
                )
            ),
        }
    },
)

# The safe answer per model failure (decision 7): a stable type, a fixed message, never
# the provider's own. The first matching class wins (subclasses before `LLMError`).
LLM_FAILURES: tuple[tuple[type[LLMError], int, str, str], ...] = (
    (LLMConfigError, 503, "llm_not_configured", "the language model is not configured"),
    (LLMUnavailableError, 502, "llm_unavailable", "the language model is unavailable"),
    (LLMRateLimitError, 502, "llm_rate_limited", "the language model is rate limited"),
    (LLMInsufficientCreditsError, 502, "llm_credits", "the language model has no credits left"),
    (LLMAuthError, 502, "llm_auth", "the language model rejected our credentials"),
    (LLMError, 502, "llm_error", "the language model call failed"),
)

CASE_CLOSED_MSG = "the case is closed and takes no new messages"
CASE_CHANGED_MSG = "the case changed while processing, try again"
TENANT_MISMATCH_MSG = "the session belongs to another tenant"
SESSION_NOT_FOUND_MSG = "no session with this id"
SESSION_ID_PARAM = "The session id (a UUID) sent with the session's messages."


def _llm_failure(error: LLMError) -> ApiError:
    for error_class, status, type, msg in LLM_FAILURES:
        if isinstance(error, error_class):
            return ApiError(status, type, msg)
    raise AssertionError("unreachable: LLMError is the last entry")


SEND_DESCRIPTION = """Send one message of a session and get the copilot's reply.

The copilot guides a plant team through five phases: **understand** the problem (what,
where, since when, the standard), **challenge** it with evidence, **analyse** the cause,
agree **actions**, then **follow up** until the case is closed. Code checks each phase's
exit criteria; the reply opens the next phase as soon as they are met.

The first message of a `session_id` opens a case for its `tenant`; the following ones
continue it. A turn is atomic: if it fails (`409`, `502`, `503`), nothing of it is stored
and the message can simply be sent again. A knowledge-base failure does not fail the
turn: the copilot says it could not consult it.

| Status | Meaning |
|---|---|
| `200` | The reply, the phase after the turn and the tools used. |
| `401` | `X-API-Key` missing or wrong. |
| `409` | `case_closed`, or `case_changed` (another turn won; send it again). |
| `422` | Body not acceptable, text too long, or `tenant_mismatch`. |
| `502` | The language model failed (`llm_*`, see below). |
| `503` | `llm_not_configured`: no language model key. |
"""


@router.post(
    "/messages",
    operation_id="send_copilot_message",
    summary="Send a message to the copilot",
    description=SEND_DESCRIPTION,
    responses={
        200: {"description": "The copilot's reply and the case's phase after the turn."},
        409: {
            "model": ErrorResponse,
            "description": "The case is closed (`case_closed`), or another turn of the session"
            " was committed while this one ran (`case_changed`: nothing was stored, send the"
            " message again).",
            "content": _examples(
                case_closed=("Closed case", _error("case_closed", [], CASE_CLOSED_MSG)),
                case_changed=("Concurrent turn", _error("case_changed", [], CASE_CHANGED_MSG)),
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "The body is not acceptable. `type` is `tenant_mismatch` (the"
            " session belongs to another tenant; nothing was stored), `string_too_long`"
            " (`text` over `MAX_USER_MESSAGE_CHARS`, default 4000) or a FastAPI validation"
            " code: `string_too_short` (blank `text` or `user_id`), `uuid_parsing`"
            " (`session_id`), `string_pattern_mismatch` (`tenant`), `missing`,"
            " `extra_forbidden` or `json_invalid`.",
            "content": _examples(
                tenant_mismatch=(
                    "Another tenant's session",
                    _error("tenant_mismatch", ["body", "tenant"], TENANT_MISMATCH_MSG),
                ),
                string_too_long=(
                    "Text too long",
                    _error(
                        "string_too_long",
                        ["body", "text"],
                        "String should have at most 4000 characters",
                    ),
                ),
                string_too_short=(
                    "Blank text",
                    _error(
                        "string_too_short",
                        ["body", "text"],
                        "String should have at least 1 character",
                        input="  ",
                        ctx={"min_length": 1},
                    ),
                ),
            ),
        },
        502: {
            "model": ErrorResponse,
            "description": "The language model failed after retries. Nothing was stored;"
            " sending the message again later is safe. One fixed message per `type`, never"
            " the provider's details.",
            "content": _examples(
                **{
                    type: (msg[0].upper() + msg[1:], _error(type, [], msg))
                    for _, status, type, msg in LLM_FAILURES
                    if status == 502
                }
            ),
        },
        503: {
            "model": ErrorResponse,
            "description": "No language model is configured (`OPENROUTER_API_KEY` is unset)."
            " Nothing was stored.",
            "content": _examples(
                llm_not_configured=(
                    "No model key",
                    _error("llm_not_configured", [], "the language model is not configured"),
                )
            ),
        },
    },
)
def send_copilot_message(
    request: CopilotMessageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    engine: Annotated[TurnEngine, Depends(get_turn_engine)],
) -> CopilotMessageResponse:
    limit = settings.max_user_message_chars
    if len(request.text) > limit:
        # The limit is a setting, so the schema cannot carry it; same shape as FastAPI's.
        raise ApiError(
            422,
            "string_too_long",
            f"String should have at most {limit} characters",
            ["body", "text"],
        )
    adapter = WebAdapter()
    incoming = adapter.parse(request.model_dump())
    try:
        result = handle_message(engine, pool, incoming)
    except CaseTenantMismatch:
        raise ApiError(422, "tenant_mismatch", TENANT_MISMATCH_MSG, ["body", "tenant"]) from None
    except CaseClosed:
        raise ApiError(409, "case_closed", CASE_CLOSED_MSG) from None
    except CaseChanged:
        raise ApiError(409, "case_changed", CASE_CHANGED_MSG) from None
    except LLMError as error:
        failure = _llm_failure(error)
        logger.warning(
            "turn failed session=%s: %s (status=%s reason=%s)",
            incoming.external_thread_id,
            failure.type,
            error.status,
            error.reason,
        )
        raise failure from None
    return CopilotMessageResponse.model_validate(adapter.deliver(incoming, result))


GET_SESSION_DESCRIPTION = """A session's case as it is stored: phase, the four facts, the
annotations, the actions and the conversation. For inspection while testing; it never
returns system prompts, traces or retrieved text.

| Status | Meaning |
|---|---|
| `200` | The session. |
| `401` | `X-API-Key` missing or wrong. |
| `404` | No message was ever sent with this `session_id`. |
| `422` | `session_id` is not a UUID (FastAPI validation). |
"""


@router.get(
    "/sessions/{session_id}",
    operation_id="get_copilot_session",
    summary="Get a copilot session",
    description=GET_SESSION_DESCRIPTION,
    responses={
        200: {"description": "The session's case."},
        404: {
            "model": ErrorResponse,
            "description": "No session has this id.",
            "content": _examples(
                session_not_found=(
                    "Unknown session",
                    _error("session_not_found", ["path", "session_id"], SESSION_NOT_FOUND_MSG),
                )
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "`session_id` is not a UUID: `type` is `uuid_parsing`.",
            "content": _examples(
                uuid_parsing=(
                    "Malformed session id",
                    _error(
                        "uuid_parsing",
                        ["path", "session_id"],
                        "Input should be a valid UUID, invalid character: expected an optional"
                        " prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `s` at 1",
                        input="session-1",
                        ctx={
                            "error": "invalid character: expected an optional prefix of"
                            " `urn:uuid:` followed by [0-9a-fA-F-], found `s` at 1"
                        },
                    ),
                )
            ),
        },
    },
)
def get_copilot_session(
    session_id: Annotated[
        UUID, PathParam(description=SESSION_ID_PARAM, examples=[SESSION_ID_EXAMPLE])
    ],
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    engine: Annotated[TurnEngine, Depends(get_turn_engine)],
) -> CopilotSession:
    view = read_session(pool, web_key(str(session_id)), today=engine.today())
    if view is None:
        raise ApiError(404, "session_not_found", SESSION_NOT_FOUND_MSG, ["path", "session_id"])
    return CopilotSession.from_view(session_id, view)
