"""Turning one document into Markdown: the `Converter` protocol and its docling version.

docling is an optional dependency group (`uv sync --group convert`): it brings torch and
its layout models, which the API never needs. It is imported only when a run converts.
"""

import os
import stat
import tempfile
from pathlib import Path
from typing import Protocol

INSTALL_HINT = "docling is not installed: run `uv sync --group convert`"


class Converter(Protocol):
    def to_markdown(self, source: Path) -> str:
        """The document's Markdown; raises on a document it cannot convert."""
        ...


class ConverterUnavailableError(Exception):
    """docling is missing; the message says how to install it."""


class DoclingConverter:
    """docling with its defaults: images as `<!-- image -->` placeholders, no picture export.

    One `DocumentConverter` for the whole run, so its models load once.
    """

    def __init__(self) -> None:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as error:
            raise ConverterUnavailableError(INSTALL_HINT) from error
        self._converter = DocumentConverter()

    def to_markdown(self, source: Path) -> str:
        return self._converter.convert(source).document.export_to_markdown()


def write_markdown(path: Path, text: str) -> None:
    """Write `text` as UTF-8 with a final newline, atomically (a failure keeps the old file).

    The file keeps the mode of the one it replaces, else gets the mode `open()` would give
    (0666 minus the umask), not `mkstemp`'s 0600.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = _existing_mode(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
        os.chmod(tmp, mode if mode is not None else 0o666 & ~_umask())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _existing_mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None


def _umask() -> int:
    """The process umask. Reading it means setting it: fine in this single-threaded CLI."""
    current = os.umask(0o022)
    os.umask(current)
    return current
