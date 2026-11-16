"""Keep query strings out of uvicorn's access log.

A query string can carry customer content (`GET /admin/cases?q=...` searches case text),
so the access log keeps the method, path, status and client but drops everything after
`?`. `main()` installs the filter on uvicorn's access handler through `log_config`.
"""

import copy
import logging
from typing import Any

from uvicorn.config import LOGGING_CONFIG

# uvicorn logs each request as `(client_addr, method, path_with_query, http_version,
# status_code)`; its AccessFormatter builds the request line from these.
_ACCESS_ARGS = 5
_PATH = 2


class DropQueryString(logging.Filter):
    """Cut the path of an access record at `?`. A record of any other shape passes
    unchanged, so a uvicorn upgrade cannot break logging."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == _ACCESS_ARGS and isinstance(args[_PATH], str):
            path = args[_PATH].split("?", 1)[0]
            record.args = (*args[:_PATH], path, *args[_PATH + 1 :])
        return True


def uvicorn_log_config() -> dict[str, Any]:
    """uvicorn's default logging config, with `DropQueryString` on the access handler."""
    config = copy.deepcopy(LOGGING_CONFIG)
    config.setdefault("filters", {})["drop_query_string"] = {
        "()": "ayo_copilot.access_log.DropQueryString"
    }
    config["handlers"]["access"].setdefault("filters", []).append("drop_query_string")
    return config
