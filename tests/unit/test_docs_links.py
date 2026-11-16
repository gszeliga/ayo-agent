"""The README and the topic docs link to each other: every relative link must reach a file
that exists and, with an anchor, a heading of that file (GitHub's slugs)."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]
# [text](target) outside code; images and reference-style links are not used here.
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^(```|~~~)")


def prose_lines(path: Path) -> list[str]:
    """The file's lines outside fenced code blocks, inline code removed."""
    lines, in_code = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line.strip()):
            in_code = not in_code
            continue
        if not in_code:
            lines.append(re.sub(r"`[^`]*`", "", line))
    return lines


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    text = heading.strip().lower().replace("`", "")
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    raw = path.read_text(encoding="utf-8").splitlines()
    found, in_code = set(), False
    for line in raw:
        if FENCE.match(line.strip()):
            in_code = not in_code
        elif not in_code and line.startswith("#"):
            found.add(slug(line.lstrip("#")))
    return found


def links(path: Path) -> list[str]:
    return [m for line in prose_lines(path) for m in LINK.findall(line)]


def test_the_topic_docs_exist() -> None:
    names = {path.name for path in DOCS}
    expected = {"knowledge-base.md", "search.md", "copilot.md", "configuration.md"}
    assert expected | {"operations.md", "development.md", "README.md"} <= names


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_relative_links_resolve(path: Path) -> None:
    broken = []
    for target in links(path):
        if re.match(r"^[a-z]+:", target):  # http(s), mailto: not checked
            continue
        file_part, _, anchor = target.partition("#")
        destination = (path.parent / file_part).resolve() if file_part else path
        missing_anchor = (
            bool(anchor) and destination.is_file() and anchor not in anchors(destination)
        )
        if not destination.exists() or missing_anchor:
            broken.append(target)
    assert broken == []


def test_every_topic_doc_is_listed_in_the_readme() -> None:
    listed = set(links(REPO_ROOT / "README.md"))
    for path in DOCS[1:]:
        assert f"docs/{path.name}" in listed
