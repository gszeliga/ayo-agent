"""`docling-import-files PATH [--out DIR] [--recursive] [--reconvert] [--dry-run]`.

Converts a document, or the documents in a folder, to Markdown with docling. The Markdown
goes next to each source, or under `--out` (keeping subfolders). A Markdown file newer than
its source is left alone unless `--reconvert`; `.md` files found in the scan are taken as
they are. One line per file, then a summary; a failed file does not stop the run.

Prints paths, actions and error types only, never document content. Exit status: 0 all
done, 1 some file failed, 2 the run could not start.
"""

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from ayo_copilot.docling_import.converter import (
    Converter,
    ConverterUnavailableError,
    DoclingConverter,
    write_markdown,
)
from ayo_copilot.docling_import.plan import Action, Item, PlanError, plan_import

PROG = "docling-import-files"
MAX_ERROR_CHARS = 200


class EmptyMarkdownError(Exception):
    """docling returned no text (a scanned image without OCR text, an empty file)."""


def entrypoint() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())


def main(
    argv: Sequence[str] | None = None,
    *,
    make_converter: Callable[[], Converter] = DoclingConverter,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out, err = stdout or sys.stdout, stderr or sys.stderr
    args = _parser().parse_args(argv)
    try:
        items = plan_import(
            args.path, out_dir=args.out, recursive=args.recursive, reconvert=args.reconvert
        )
    except PlanError as error:
        print(f"{PROG}: {error}", file=err)
        return 2
    if not items:
        print(f"{PROG}: no documents found in {args.path}", file=err)
        return 2

    if args.dry_run:
        for item in items:
            print(_describe(item, dry_run=True), file=out)
        return 0

    converter: Converter | None = None
    if any(item.action is Action.CONVERT for item in items):
        try:
            converter = make_converter()
        except ConverterUnavailableError as error:
            print(f"{PROG}: {error}", file=err)
            return 2

    counts: Counter[str] = Counter()
    for item in items:
        if item.action is Action.CONVERT:
            assert converter is not None
            try:
                _convert(converter, item)
            except Exception as error:
                counts["failed"] += 1
                print(f"failed      {item.source} ({_safe_error(error)})", file=out)
                continue
            counts["converted"] += 1
        else:
            counts[item.action.value.replace("_", " ")] += 1
        print(_describe(item, dry_run=False), file=out)

    summary = ", ".join(
        f"{counts[key]} {key}"
        for key in ("converted", "up to date", "as is", "failed")
        if counts[key]
    )
    print(f"{len(items)} documents: {summary}", file=out)
    return 1 if counts["failed"] else 0


def _convert(converter: Converter, item: Item) -> None:
    text = converter.to_markdown(item.source)
    if not text.strip():
        raise EmptyMarkdownError("no text extracted")
    write_markdown(item.markdown, text)


def _describe(item: Item, *, dry_run: bool) -> str:
    match item.action:
        case Action.CONVERT:
            verb = "would convert" if dry_run else "converted"
            return f"{verb:<11} {item.source} -> {item.markdown}"
        case Action.UP_TO_DATE:
            return f"{'up to date':<11} {item.markdown}"
        case Action.AS_IS:
            return f"{'as is':<11} {item.markdown}"


def _safe_error(error: Exception) -> str:
    """The error's type and the first line of its message, capped: no content dump."""
    message = str(error).strip().splitlines()[0] if str(error).strip() else ""
    if len(message) > MAX_ERROR_CHARS:
        message = message[:MAX_ERROR_CHARS] + "…"
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Convert documents (PDF, DOCX, PPTX, XLSX, HTML, images, ...) to Markdown"
        " with docling, for the knowledge base.",
    )
    parser.add_argument("path", type=Path, help="a document, or a folder of documents")
    parser.add_argument(
        "--out",
        type=Path,
        help="folder for the Markdown files, keeping subfolders (default: next to each source)",
    )
    parser.add_argument(
        "--recursive", "-r", action="store_true", help="also scan the folder's subfolders"
    )
    parser.add_argument(
        "--reconvert",
        action="store_true",
        help="convert again even when the Markdown is newer than its source",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would be done, write nothing"
    )
    return parser
