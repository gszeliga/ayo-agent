"""`ayo-transcript SESSION_ID [--out DIR]`: write a session's transcript to a local file.

Reads the session from `DATABASE_URL` (the shell, then `.env`), with the app's guard: a
remote database needs `ALLOW_REMOTE_DATABASE=true`. It only reads, in read-only
transactions. The file holds the conversation's content: it goes to the git-ignored
`eval/conversations/` by default, and nothing of it is printed except its path.
"""

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from uuid import UUID

from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from ayo_copilot.config import ConversationSettings, DatabaseSettings
from ayo_copilot.conversation.channels import web_key
from ayo_copilot.conversation.store import read_session, read_traces
from ayo_copilot.conversation.transcript import DEFAULT_OUT, render_transcript, write_transcript
from ayo_copilot.db.pool import open_pool


def entrypoint() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())


def main(
    argv: Sequence[str] | None = None,
    *,
    load_settings: Callable[[], tuple[DatabaseSettings, ConversationSettings]] | None = None,
    open_db: Callable[[str], ConnectionPool] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out, err = stdout or sys.stdout, stderr or sys.stderr
    args = _parser().parse_args(argv)
    try:
        database, conversation = (load_settings or _load_settings)()
    except ValidationError as error:
        messages = "; ".join(e["msg"].removeprefix("Value error, ") for e in error.errors())
        print(f"ayo-transcript: invalid settings: {messages}", file=err)
        return 2
    pool = (open_db or _open)(database.database_url.get_secret_value())
    try:
        moment = now()
        today = moment.astimezone(conversation.timezone()).date()
        view = read_session(pool, web_key(str(args.session_id)), today=today)
        if view is None:
            print(f"ayo-transcript: no session {args.session_id}", file=err)
            return 1
        text = render_transcript(
            args.session_id, view, read_traces(pool, view.problem_id), written_at=moment
        )
    finally:
        pool.close()
    path = write_transcript(text, session_id=args.session_id, out_dir=args.out, now=moment)
    print(path, file=out)
    return 0


def _load_settings() -> tuple[DatabaseSettings, ConversationSettings]:
    return DatabaseSettings(), ConversationSettings()


def _open(url: str) -> ConnectionPool:
    return open_pool(url, min_size=1, max_size=1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ayo-transcript",
        description="Write a copilot session's transcript (messages, phases, tools, metrics)"
        " to a local Markdown file.",
    )
    parser.add_argument("session_id", type=UUID, help="the session id used with /copilot")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"directory for the file (default: {DEFAULT_OUT}/, git-ignored)",
    )
    return parser
