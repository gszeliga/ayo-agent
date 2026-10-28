"""One error format for every response: FastAPI's validation-error shape.

    {"detail": [{"type": "file_empty", "loc": ["body", "file"], "msg": "file is empty"}]}

FastAPI's own 422s already look like this (they also carry `input`). Our errors and
Starlette's (400, 404, 405, ...) are converted to it, and so are unhandled exceptions
(500), so a caller only ever parses one shape and can branch on `type`. Our items never
carry `input`: document content is never echoed back.
"""

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ayo_copilot.schemas import ErrorItem, ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An error response with a stable `type`, raised by the routers."""

    def __init__(
        self,
        status_code: int,
        type: str,
        msg: str,
        loc: Sequence[str | int] = (),
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(msg)
        self.status_code = status_code
        self.type = type
        self.msg = msg
        self.loc = list(loc)
        self.headers = dict(headers or {})


def error_response(
    status_code: int,
    type: str,
    msg: str,
    loc: Sequence[str | int] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(detail=[ErrorItem(type=type, loc=list(loc), msg=msg)])
    # exclude_unset: our items never carry `input` or `ctx`.
    return JSONResponse(
        body.model_dump(exclude_unset=True), status_code=status_code, headers=headers
    )


def _status_type(status_code: int) -> str:
    """`404` -> `not_found`, `405` -> `method_not_allowed`."""
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "http_error"


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.status_code, exc.type, exc.msg, exc.loc, exc.headers)


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    msg = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return error_response(exc.status_code, _status_type(exc.status_code), msg, (), exc.headers)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Starlette re-raises the exception after this response, so the server logs it.
    return error_response(500, "internal_error", "internal server error")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(Exception, _unhandled)
