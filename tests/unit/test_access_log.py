"""Query strings stay out of uvicorn's access log: the filter, its wiring in `main()`,
and a real logging config writing an access line (in a subprocess, so the suite's own
logging is untouched)."""

import logging
import subprocess
import sys
from typing import Any

import pytest

import ayo_copilot
from ayo_copilot.access_log import DropQueryString, uvicorn_log_config

ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'


def access_record(path: str, args: Any = None) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        ACCESS_FORMAT,
        args if args is not None else ("127.0.0.1:5000", "GET", path, "1.1", 200),
        None,
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/admin/cases?q=merma%20confidencial", "/admin/cases"),
        ("/admin/documents?tenant=acme&q=sellado", "/admin/documents"),
        ("/admin/cases?", "/admin/cases"),
        ("/admin/cases", "/admin/cases"),
        ("/", "/"),
    ],
)
def test_filter_drops_the_query_string(path: str, expected: str) -> None:
    record = access_record(path)

    assert DropQueryString().filter(record) is True
    assert record.args == ("127.0.0.1:5000", "GET", expected, "1.1", 200)
    assert record.getMessage() == f'127.0.0.1:5000 - "GET {expected} HTTP/1.1" 200'


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("only", "four", "args", 1),
        ("127.0.0.1:5000", "GET", None, "1.1", 200),
        {"path": "/admin/cases?q=x"},
    ],
    ids=["no args", "four args", "path not a string", "mapping"],
)
def test_filter_leaves_other_records_alone(args: Any) -> None:
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", None, None)
    record.args = args

    assert DropQueryString().filter(record) is True
    assert record.args == args


def test_config_puts_the_filter_on_the_access_handler_only() -> None:
    config = uvicorn_log_config()

    assert config["filters"]["drop_query_string"] == {
        "()": "ayo_copilot.access_log.DropQueryString"
    }
    assert config["handlers"]["access"]["filters"] == ["drop_query_string"]
    assert "filters" not in config["handlers"]["default"]
    # uvicorn's own default is left as it was.
    assert uvicorn_log_config() == config
    from uvicorn.config import LOGGING_CONFIG

    assert "filters" not in LOGGING_CONFIG["handlers"]["access"]


def test_main_passes_the_config_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(ayo_copilot.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(ayo_copilot.logging, "basicConfig", lambda **kwargs: None)

    ayo_copilot.main()

    [kwargs] = calls
    assert kwargs["log_config"] == uvicorn_log_config()
    assert kwargs["factory"] is True


SCRIPT = f"""
import logging.config
from ayo_copilot.access_log import uvicorn_log_config

logging.config.dictConfig(uvicorn_log_config())
logging.getLogger("uvicorn.access").info(
    {ACCESS_FORMAT!r}, "127.0.0.1:5000", "GET", "/admin/cases?q=merma+confidencial", "1.1", 200
)
"""


def test_access_line_has_no_query_string() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True, timeout=60
    )

    assert '"GET /admin/cases HTTP/1.1" 200' in result.stdout
    assert "confidencial" not in result.stdout + result.stderr
    assert "q=" not in result.stdout
