import logging

import uvicorn


def main() -> None:
    from ayo_copilot.access_log import uvicorn_log_config

    # A root handler for the app's own logs and psycopg's; uvicorn configures its own,
    # with query strings kept out of the access log (they can carry case content).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    uvicorn.run(
        "ayo_copilot.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        log_config=uvicorn_log_config(),
    )
