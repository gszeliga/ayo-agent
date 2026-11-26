"""What a run does with each file: scan a file or a folder, name the Markdown, skip the done.

Pure file-system logic, no docling: `plan_import` returns one `Item` per document, or raises
`PlanError` before anything is written (unsupported file, missing path, two sources that
would write the same Markdown file).
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Formats docling converts (its `InputFormat`s that make sense for documents).
CONVERTIBLE_SUFFIXES = frozenset(
    {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".html",
        ".htm",
        ".csv",
        ".adoc",
        ".asciidoc",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".webp",
    }
)
MARKDOWN_SUFFIX = ".md"


class Action(StrEnum):
    CONVERT = "convert"  # convert the source, write the Markdown
    UP_TO_DATE = "up_to_date"  # the Markdown is newer than its source: leave it
    AS_IS = "as_is"  # the source already is Markdown


@dataclass(frozen=True)
class Item:
    """One document of the run: its source, the Markdown it ends up as, and what to do."""

    source: Path
    markdown: Path
    action: Action


class PlanError(Exception):
    """The run cannot start; the message names the files, never their content."""


def plan_import(
    path: Path,
    *,
    out_dir: Path | None = None,
    recursive: bool = False,
    reconvert: bool = False,
) -> list[Item]:
    """The items for `path` (a file or a folder), sorted by source path.

    The Markdown goes next to its source, or under `out_dir`, keeping the source's folder
    relative to the scanned one. A Markdown file that is the output of a scanned source is
    that source's output, not a document of its own.
    """
    if not path.exists():
        raise PlanError(f"no such file or folder: {path}")
    if path.is_file():
        root = path.parent
        if path.suffix.lower() not in CONVERTIBLE_SUFFIXES | {MARKDOWN_SUFFIX}:
            raise PlanError(f"unsupported file type: {path}")
        files = [path]
    else:
        root = path
        files = _scan(path, recursive=recursive, skip=out_dir)

    sources = [f for f in files if f.suffix.lower() in CONVERTIBLE_SUFFIXES]
    targets: dict[Path, list[Path]] = {}
    for source in sources:
        targets.setdefault(_markdown_for(source, root, out_dir), []).append(source)
    clashes = {target: group for target, group in targets.items() if len(group) > 1}
    if clashes:
        lines = [
            f"  {target}: " + ", ".join(str(s) for s in group)
            for target, group in sorted(clashes.items())
        ]
        raise PlanError("these files would write the same Markdown file:\n" + "\n".join(lines))

    outputs = {target.resolve() for target in targets}
    items = [
        Item(source, target, _action(source, target, reconvert))
        for target, (source,) in targets.items()
    ]
    items += [
        Item(f, f, Action.AS_IS)
        for f in files
        if f.suffix.lower() == MARKDOWN_SUFFIX and f.resolve() not in outputs
    ]
    return sorted(items, key=lambda item: item.source)


def _scan(folder: Path, *, recursive: bool, skip: Path | None) -> list[Path]:
    """Regular files under `folder`, without hidden ones and without `skip`'s tree."""
    skip_resolved = skip.resolve() if skip is not None else None
    found = []
    for entry in folder.rglob("*") if recursive else folder.iterdir():
        relative = entry.relative_to(folder)
        if any(part.startswith(".") for part in relative.parts) or not entry.is_file():
            continue
        if skip_resolved is not None and entry.resolve().is_relative_to(skip_resolved):
            continue
        found.append(entry)
    return found


def _markdown_for(source: Path, root: Path, out_dir: Path | None) -> Path:
    name = source.stem + MARKDOWN_SUFFIX
    if out_dir is None:
        return source.with_name(name)
    return out_dir / source.parent.relative_to(root) / name


def _action(source: Path, markdown: Path, reconvert: bool) -> Action:
    if not reconvert and markdown.is_file() and markdown.stat().st_mtime >= source.stat().st_mtime:
        return Action.UP_TO_DATE
    return Action.CONVERT
