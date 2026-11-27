"""`docling-import-files PATH --tenant T [--out DIR] [-r] [--reconvert] [--dry-run] [-v] ...`.

Converts a document, or the documents in a folder, to Markdown with docling, then uploads
each Markdown file to `POST /admin/documents`. The Markdown goes next to each source, or
under `--out` (keeping subfolders). A Markdown file newer than its source is not converted
again unless `--reconvert`, but is still uploaded (the API answers `up_to_date` when nothing
changed); `.md` files found in the scan are uploaded as they are. `--no-upload` converts only.

The key is `ADMIN_API_KEY` (environment, then `.env`), never a flag and never printed. The
`source_key` is the Markdown file's name: two files with the same name in one run would
replace each other on the server, so the run refuses to start.

One line per skipped file (a type no step reads), a `converting (n/N)` line when a
conversion starts, one line per file when it is done, then a summary; every line is flushed,
so progress shows through a pipe too. A failed file does not stop the run, a failure every
file would share does (wrong key, wrong URL, API unreachable). Prints paths, actions,
statuses and error types only, never document content. `--verbose` also shows docling's
info logs (pipelines, timings). Exit status: 0 all done, 1 some
file failed, 2 the run could not start or was stopped.
"""

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import TextIO

from pydantic import SecretStr

from ayo_copilot.config import ImportSettings
from ayo_copilot.docling_import.converter import (
    Converter,
    ConverterUnavailableError,
    DoclingConverter,
    write_markdown,
)
from ayo_copilot.docling_import.plan import Action, Item, PlanError, plan_import
from ayo_copilot.docling_import.upload import (
    UploadAbortedError,
    Uploaded,
    Uploader,
    UploadRejectedError,
    api_origin,
)
from ayo_copilot.ingestion.storage import InvalidInputError, normalize_source_key, validate_tenant

PROG = "docling-import-files"
DEFAULT_API_URL = "http://127.0.0.1:8000"
MAX_ERROR_CHARS = 200
CONVERT_KEYS = ("converted", "up to date", "as is", "failed")
UPLOAD_KEYS = ("indexed", "unchanged", "failed", "not attempted")

_say = partial(print, flush=True)


class EmptyMarkdownError(Exception):
    """docling returned no text (a scanned image without OCR text, an empty file)."""


def entrypoint() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())


def main(
    argv: Sequence[str] | None = None,
    *,
    make_converter: Callable[[], Converter] = DoclingConverter,
    make_uploader: Callable[[str, SecretStr], Uploader] = Uploader,
    load_api_key: Callable[[], SecretStr | None] = lambda: ImportSettings().admin_api_key,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out, err = stdout or sys.stdout, stderr or sys.stderr
    parser = _parser()
    args = parser.parse_args(argv)
    upload = not args.no_upload
    if upload and args.tenant is None:
        parser.error("--tenant is required to upload (or pass --no-upload)")
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    try:
        plan = plan_import(
            args.path, out_dir=args.out, recursive=args.recursive, reconvert=args.reconvert
        )
        items = plan.items
        keys = _source_keys(items) if upload else {}
    except PlanError as error:
        _say(f"{PROG}: {error}", file=err)
        return 2
    for path in plan.skipped:
        _say(f"{'skipped':<11} {path} ({_unsupported(path)})", file=out)
    if not items:
        _say(f"{PROG}: no documents found in {args.path}", file=err)
        return 2

    if args.dry_run:
        for item in items:
            _say(_describe(item, dry_run=True), file=out)
            if upload:
                _say(f"{'would upload':<11} {item.markdown} as {keys[item]}", file=out)
        return 0

    uploader: Uploader | None = None
    if upload:
        api_key = load_api_key()
        if api_key is None:
            _say(f"{PROG}: ADMIN_API_KEY is not set (environment or .env)", file=err)
            return 2
        uploader = make_uploader(args.api_url, api_key)
        _say(f"uploading to {api_origin(args.api_url)}, tenant {args.tenant}", file=out)

    converter: Converter | None = None
    if any(item.action is Action.CONVERT for item in items):
        try:
            converter = make_converter()
        except ConverterUnavailableError as error:
            _say(f"{PROG}: {error}", file=err)
            return 2

    to_convert = sum(item.action is Action.CONVERT for item in items)
    started = 0
    converted: Counter[str] = Counter()
    uploaded: Counter[str] = Counter()
    aborted = False
    try:
        for index, item in enumerate(items):
            if item.action is Action.CONVERT:
                assert converter is not None
                started += 1
                _say(f"{'converting':<11} ({started}/{to_convert}) {item.source} …", file=out)
                try:
                    _convert(converter, item)
                except Exception as error:
                    converted["failed"] += 1
                    _say(f"failed      {item.source} ({_safe_error(error)})", file=out)
                    continue
                converted["converted"] += 1
            else:
                converted[_label(item.action)] += 1
            _say(_describe(item, dry_run=False), file=out)

            if uploader is None:
                continue
            try:
                result = uploader.upload(
                    item.markdown, tenant=args.tenant, source_key=keys[item], force=args.force
                )
            except UploadRejectedError as error:
                uploaded["failed"] += 1
                _say(f"upload failed {item.markdown} ({_cap(str(error))})", file=out)
                continue
            except UploadAbortedError as error:
                uploaded["failed"] += 1
                uploaded["not attempted"] += len(items) - index - 1
                _say(f"upload failed {item.markdown} ({_cap(str(error))})", file=out)
                _say(f"{PROG}: stopped: {_cap(str(error))}", file=err)
                aborted = True
                break
            uploaded["indexed" if result.status == "indexed" else "unchanged"] += 1
            _say(_describe_upload(item, result), file=out)
    finally:
        if uploader is not None:
            uploader.close()

    noun = "document" if len(items) == 1 else "documents"
    summary = f"{len(items)} {noun}: {_counts(converted, CONVERT_KEYS)}"
    if upload:
        summary += f"; uploaded: {_counts(uploaded, UPLOAD_KEYS)}"
    if plan.skipped:
        summary += f"; {len(plan.skipped)} skipped"
    _say(summary, file=out)
    if aborted:
        return 2
    return 1 if converted["failed"] or uploaded["failed"] else 0


def _source_keys(items: list[Item]) -> dict[Item, str]:
    """Each item's `source_key`, as the server will normalize it; clashes are a PlanError."""
    keys: dict[Item, str] = {}
    by_key: dict[str, list[Path]] = {}
    for item in items:
        try:
            key = normalize_source_key(item.markdown.name)
        except InvalidInputError as error:
            raise PlanError(f"{item.markdown}: {error}") from None
        keys[item] = key
        by_key.setdefault(key, []).append(item.markdown)
    clashes = {key: paths for key, paths in by_key.items() if len(paths) > 1}
    if clashes:
        lines = [
            f"  {key}: " + ", ".join(str(p) for p in paths)
            for key, paths in sorted(clashes.items())
        ]
        raise PlanError(
            "these files would replace each other in the knowledge base (same file name):\n"
            + "\n".join(lines)
        )
    return keys


def _convert(converter: Converter, item: Item) -> None:
    text = converter.to_markdown(item.source)
    if not text.strip():
        raise EmptyMarkdownError("no text extracted")
    write_markdown(item.markdown, text)


def _unsupported(path: Path) -> str:
    return f"unsupported: {path.suffix.lower()}" if path.suffix else "unsupported: no extension"


def _label(action: Action) -> str:
    return action.value.replace("_", " ")


def _describe(item: Item, *, dry_run: bool) -> str:
    if item.action is Action.CONVERT:
        verb = "would convert" if dry_run else "converted"
        return f"{verb:<11} {item.source} -> {item.markdown}"
    return f"{_label(item.action):<11} {item.markdown}"


def _describe_upload(item: Item, result: Uploaded) -> str:
    if result.status == "indexed":
        chunks = f", {result.chunk_count} chunks" if result.chunk_count is not None else ""
        return f"{'indexed':<11} {item.markdown} ({result.doc_id}{chunks})"
    return f"{'unchanged':<11} {item.markdown} ({result.doc_id}, already indexed)"


def _counts(counts: Counter[str], keys: Sequence[str]) -> str:
    return ", ".join(f"{counts[key]} {key}" for key in keys if counts[key]) or "none"


def _cap(message: str) -> str:
    return message[:MAX_ERROR_CHARS] + "…" if len(message) > MAX_ERROR_CHARS else message


def _safe_error(error: Exception) -> str:
    """The error's type and the first line of its message, capped: no content dump."""
    message = str(error).strip().splitlines()[0] if str(error).strip() else ""
    return f"{type(error).__name__}: {_cap(message)}" if message else type(error).__name__


def _tenant(value: str) -> str:
    try:
        return validate_tenant(value)
    except InvalidInputError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _api_url(value: str) -> str:
    try:
        api_origin(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Convert documents (PDF, DOCX, PPTX, XLSX, HTML, images, ...) to Markdown"
        " with docling and upload them to the knowledge base.",
    )
    parser.add_argument("path", type=Path, help="a document, or a folder of documents")
    parser.add_argument(
        "--tenant", type=_tenant, help="tenant to upload to (required unless --no-upload)"
    )
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
        "--api-url",
        type=_api_url,
        default=DEFAULT_API_URL,
        help=f"the AYO API (default: {DEFAULT_API_URL}); the key is ADMIN_API_KEY",
    )
    parser.add_argument(
        "--force", action="store_true", help="ask the API to reindex even unchanged documents"
    )
    parser.add_argument("--no-upload", action="store_true", help="convert only")
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would be done; write or send nothing"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="also show docling's info logs"
    )
    return parser
