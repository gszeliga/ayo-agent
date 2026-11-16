"""The cases endpoints (`/admin/cases`): inspect the copilot's cases, whatever channel
opened them. Behind the admin key, like the rest of `/admin`.

A case is the problem being solved; a session (`/copilot`) is the web channel's thread
that leads to one. Logs never carry case content or the search text.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from psycopg_pool import ConnectionPool

from ayo_copilot.cases import read_case_page
from ayo_copilot.conversation.case import Phase
from ayo_copilot.dependencies import get_pool, get_today
from ayo_copilot.ingestion.storage import TENANT_PATTERN
from ayo_copilot.routers.admin import UNAUTHORIZED_RESPONSE, require_admin_key
from ayo_copilot.schemas import CaseListItem, CasePage, ErrorResponse


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
