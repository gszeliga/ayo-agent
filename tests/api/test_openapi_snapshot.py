import difflib

from ayo_copilot.openapi import EXPORT_COMMAND, OPENAPI_PATH, render_openapi

MAX_DIFF_LINES = 20


def test_committed_openapi_matches_the_app() -> None:
    assert OPENAPI_PATH.exists(), f"{OPENAPI_PATH} is missing: run `{EXPORT_COMMAND}`"
    committed = OPENAPI_PATH.read_text(encoding="utf-8")
    rendered = render_openapi()

    if committed != rendered:
        diff = difflib.unified_diff(
            committed.splitlines(),
            rendered.splitlines(),
            "docs/openapi.json (committed)",
            "app (generated)",
            lineterm="",
        )
        excerpt = "\n".join(list(diff)[:MAX_DIFF_LINES])
        raise AssertionError(
            f"docs/openapi.json is out of date: run `{EXPORT_COMMAND}` and commit it.\n{excerpt}"
        )
