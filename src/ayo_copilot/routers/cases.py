"""The cases endpoints (`/admin/cases`): inspect the copilot's cases, whatever channel
opened them. Behind the admin key, like the rest of `/admin`.

A case is the problem being solved; a session (`/copilot`) is the web channel's thread
that leads to one. Logs never carry case content or the search text.
"""

import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from psycopg_pool import ConnectionPool

from ayo_copilot.cases import delete_case, read_case_detail, read_case_page, read_case_turns
from ayo_copilot.conversation.case import Phase
from ayo_copilot.dependencies import get_pool, get_today
from ayo_copilot.errors import ApiError
from ayo_copilot.ingestion.storage import TENANT_PATTERN
from ayo_copilot.routers.admin import UNAUTHORIZED_RESPONSE, require_admin_key
from ayo_copilot.schemas import (
    CASE_ID_EXAMPLE,
    TURN_PAGE_MAX,
    CaseDetail,
    CaseListItem,
    CasePage,
    CaseTurnPage,
    ErrorResponse,
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


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/cases",
    tags=["cases"],
    dependencies=[Depends(require_admin_key)],
    responses={401: UNAUTHORIZED_RESPONSE},
)

LIST_DESCRIPTION = """List the copilot's cases, from every channel, one page at a time,
newest update first.

Filter by `tenant`, `phase`, `closed` (`true` only closed cases, `false` only open ones)
and `q`, a case-insensitive substring of what happens (`what`; `%` and `_` match
themselves). `total` counts every match and the order is stable across pages, even on
ties. A case opened by a first message that failed is listed too, with no turns.

`web_session_id` is the web session to keep talking in; a case from another channel has
none.

| Status | Meaning |
|---|---|
| `200` | A page, possibly empty. |
| `401` | `X-API-Key` missing or wrong. |
| `422` | A query parameter is out of range or not allowed (FastAPI validation). |
"""


@router.get(
    "",
    operation_id="list_cases",
    summary="List cases",
    description=LIST_DESCRIPTION,
    responses={
        # The 200 sample comes from the field examples (see `schemas.CaseListItem`).
        200: {"description": "A page of cases."},
        422: {
            "model": ErrorResponse,
            "description": "A query parameter is not acceptable. `type` is a FastAPI validation"
            " code such as `literal_error` (unknown `phase`), `bool_parsing` (`closed`),"
            " `greater_than_equal` or `less_than_equal` (`limit`, `offset`),"
            " `string_too_long` (`q`) or `string_pattern_mismatch` (`tenant`).",
            "content": _examples(
                literal_error=(
                    "Unknown phase",
                    _error(
                        "literal_error",
                        ["query", "phase"],
                        "Input should be 'understand', 'challenge', 'analyse', 'action',"
                        " 'followup' or 'closed'",
                        input="done",
                        ctx={
                            "expected": "'understand', 'challenge', 'analyse', 'action',"
                            " 'followup' or 'closed'"
                        },
                    ),
                ),
                less_than_equal=(
                    "Page too large",
                    _error(
                        "less_than_equal",
                        ["query", "limit"],
                        "Input should be less than or equal to 100",
                        input="500",
                        ctx={"le": 100},
                    ),
                ),
            ),
        },
    },
)
def list_cases(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    today: Annotated[date, Depends(get_today)],
    tenant: Annotated[
        str | None,
        Query(pattern=TENANT_PATTERN, description="Only this tenant's cases.", examples=["acme"]),
    ] = None,
    phase: Annotated[
        Phase | None, Query(description="Only cases in this phase.", examples=["analyse"])
    ] = None,
    closed: Annotated[
        bool | None,
        Query(
            description="`true`: only closed cases; `false`: only open ones; absent: both.",
            examples=[False],
        ),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            max_length=200,
            description="Case-insensitive substring of what happens (`what`). Never logged"
            " (the access log drops query strings).",
            examples=["merma"],
        ),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Page size, 1 to 100.", examples=[25])
    ] = 25,
    offset: Annotated[
        int, Query(ge=0, description="Number of matching cases to skip.", examples=[0])
    ] = 0,
) -> CasePage:
    rows, total = read_case_page(
        pool,
        today=today,
        tenant=tenant,
        phase=phase,
        closed=closed,
        q=q or None,
        limit=limit,
        offset=offset,
    )
    return CasePage(
        items=[CaseListItem.from_row(row) for row in rows], total=total, limit=limit, offset=offset
    )


GET_DESCRIPTION = """One case, from any channel: its header (tenant, title, phase,
version, turn count, times, `web_session_id`), the four facts, the annotations (evidence,
hypotheses, discarded hypotheses, the validated cause), the actions, with `overdue`
computed in `APP_TIMEZONE`, and the AI summary: null until one is generated, `stale` once
a turn has been committed after it.

The conversation and the turn traces are not part of it: page through them with
`GET /admin/cases/{case_id}/turns`.

| Status | Meaning |
|---|---|
| `200` | The case. |
| `401` | `X-API-Key` missing or wrong. |
| `404` | No case with that id (`case_not_found`). |
| `422` | `case_id` is not a UUID (FastAPI validation). |
"""

CASE_ID_PARAM = "The case id (a UUID), as `case_id` in the listing or the copilot's replies."
CASE_NOT_FOUND = _error("case_not_found", ["path", "case_id"], "case not found")
CASE_NOT_FOUND_RESPONSE: dict[str, object] = {
    "model": ErrorResponse,
    "description": "No case with that id: `type` is `case_not_found`.",
    "content": _examples(case_not_found=("Unknown case", CASE_NOT_FOUND)),
}
MALFORMED_CASE_ID = _error(
    "uuid_parsing",
    ["path", "case_id"],
    "Input should be a valid UUID, invalid character: expected an optional"
    " prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `c` at 1",
    input="case-1",
    ctx={
        "error": "invalid character: expected an optional prefix of"
        " `urn:uuid:` followed by [0-9a-fA-F-], found `c` at 1"
    },
)


@router.get(
    "/{case_id}",
    operation_id="get_case",
    summary="Get a case",
    description=GET_DESCRIPTION,
    responses={
        # The 200 sample comes from the field examples (see `schemas.CaseDetail`).
        200: {"description": "The case."},
        404: CASE_NOT_FOUND_RESPONSE,
        422: {
            "model": ErrorResponse,
            "description": "`case_id` is not a UUID: `type` is `uuid_parsing`.",
            "content": _examples(uuid_parsing=("Malformed id", MALFORMED_CASE_ID)),
        },
    },
)
def get_case(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    today: Annotated[date, Depends(get_today)],
    case_id: Annotated[UUID, PathParam(description=CASE_ID_PARAM, examples=[CASE_ID_EXAMPLE])],
) -> CaseDetail:
    detail = read_case_detail(pool, case_id, today=today)
    if detail is None:
        raise _case_not_found()
    return CaseDetail.from_detail(detail)


def _case_not_found() -> ApiError:
    return ApiError(404, "case_not_found", "case not found", ["path", "case_id"])


TURNS_DESCRIPTION = f"""A case's turns, oldest first, one page at a time: for each, the
user's message, the copilot's reply and the turn's trace (phases, tool calls with their
outcome, the knowledge retrieved, model, tokens, cost, latency).

`total` is the case's turn count (`turns` in `get_case`) and turn n is item `n - 1`
counting from `offset` 0, so the latest page starts at `offset = max(0, total - limit)`.
Turns are only ever added at the end: a new one never moves the earlier pages.

The trace has no prompts, tool arguments or retrieved text. A retrieved chunk carries its
document's current title, and `document_deleted` once the document is gone.

| Status | Meaning |
|---|---|
| `200` | A page, possibly empty (no turns yet, or `offset` past the last turn). |
| `401` | `X-API-Key` missing or wrong. |
| `404` | No case with that id (`case_not_found`). |
| `422` | `case_id` is not a UUID, or `limit` (1 to {TURN_PAGE_MAX}) or `offset` is out of range. |
"""


@router.get(
    "/{case_id}/turns",
    operation_id="list_case_turns",
    summary="List a case's turns",
    description=TURNS_DESCRIPTION,
    responses={
        # The 200 sample comes from the field examples (see `schemas.CaseTurn`).
        200: {"description": "A page of turns."},
        404: CASE_NOT_FOUND_RESPONSE,
        422: {
            "model": ErrorResponse,
            "description": "`case_id` is not a UUID (`uuid_parsing`), or `limit` or `offset` is"
            " out of range (`greater_than_equal`, `less_than_equal`).",
            "content": _examples(
                uuid_parsing=("Malformed id", MALFORMED_CASE_ID),
                less_than_equal=(
                    "Page too large",
                    _error(
                        "less_than_equal",
                        ["query", "limit"],
                        f"Input should be less than or equal to {TURN_PAGE_MAX}",
                        input="500",
                        ctx={"le": TURN_PAGE_MAX},
                    ),
                ),
            ),
        },
    },
)
def list_case_turns(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    case_id: Annotated[UUID, PathParam(description=CASE_ID_PARAM, examples=[CASE_ID_EXAMPLE])],
    limit: Annotated[
        int,
        Query(
            ge=1, le=TURN_PAGE_MAX, description=f"Page size, 1 to {TURN_PAGE_MAX}.", examples=[20]
        ),
    ] = 20,
    offset: Annotated[
        int, Query(ge=0, description="Number of turns to skip, oldest first.", examples=[0])
    ] = 0,
) -> CaseTurnPage:
    turns = read_case_turns(pool, case_id, limit=limit, offset=offset)
    if turns is None:
        raise _case_not_found()
    return CaseTurnPage.from_turns(turns, limit=limit, offset=offset)


DELETE_DESCRIPTION = """Delete a case for good, whatever channel opened it, with its
messages, annotations, actions, channel links and turn traces. There is no undo.

A turn still running on the case stores nothing and answers `409 case_changed`. The
deleted case's web session is unlinked: a later message with the same `session_id` opens
a new, empty case.

| Status | Meaning |
|---|---|
| `204` | Deleted. |
| `401` | `X-API-Key` missing or wrong. |
| `404` | No case with that id (or it was already deleted). |
| `422` | `case_id` is not a UUID (FastAPI validation). |
"""


@router.delete(
    "/{case_id}",
    operation_id="delete_case",
    summary="Delete a case",
    description=DELETE_DESCRIPTION,
    status_code=204,
    response_class=Response,
    responses={
        204: {"description": "Deleted, with everything it owned."},
        404: CASE_NOT_FOUND_RESPONSE,
        422: {
            "model": ErrorResponse,
            "description": "`case_id` is not a UUID: `type` is `uuid_parsing`.",
            "content": _examples(uuid_parsing=("Malformed id", MALFORMED_CASE_ID)),
        },
    },
)
def delete(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    case_id: Annotated[UUID, PathParam(description=CASE_ID_PARAM, examples=[CASE_ID_EXAMPLE])],
) -> Response:
    deleted = delete_case(pool, case_id)
    if deleted is None:
        raise _case_not_found()
    tenant, turns = deleted
    # The only trace of the deletion (no audit table yet); ids and counts, no content.
    logger.info("case deleted case_id=%s tenant=%s turns=%d", case_id, tenant, turns)
    return Response(status_code=204)
