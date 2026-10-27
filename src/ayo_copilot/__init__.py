import logging

import uvicorn


def main() -> None:
    # A root handler for the app's own logs and psycopg's; uvicorn configures its own.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    uvicorn.run("ayo_copilot.app:create_app", factory=True, host="127.0.0.1", port=8000)
