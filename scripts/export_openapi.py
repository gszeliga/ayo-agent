"""Write docs/openapi.json from the app, or with --check report whether it is up to date.

uv run python scripts/export_openapi.py
uv run python scripts/export_openapi.py --check
"""

import argparse
import sys

from ayo_copilot.openapi import EXPORT_COMMAND, OPENAPI_PATH, render_openapi


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="change nothing; exit 1 if the file is stale"
    )
    args = parser.parse_args()

    rendered = render_openapi()
    current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else None
    if args.check:
        if current != rendered:
            print(f"{OPENAPI_PATH} is out of date: run `{EXPORT_COMMAND}`", file=sys.stderr)
            return 1
        print(f"{OPENAPI_PATH} is up to date")
        return 0

    if current == rendered:
        print(f"{OPENAPI_PATH} is already up to date")
        return 0
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
