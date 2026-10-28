"""The committed OpenAPI contract, `docs/openapi.json`.

`scripts/export_openapi.py` writes it and a snapshot test checks it matches the app, so
API changes show up as reviewable diffs. Rendering needs no database and no `.env`.
"""

import json
from pathlib import Path

from ayo_copilot.app import create_app

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
EXPORT_COMMAND = "uv run python scripts/export_openapi.py"


def render_openapi() -> str:
    """The app's spec as stable JSON: indented, sorted keys, trailing newline."""
    spec = create_app(docs_enabled=True).openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
