import re
from dataclasses import dataclass, replace

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

HEADING_LEVELS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
HEADING_SEPARATOR = " > "
# A small chunk merged backward may grow its predecessor up to this factor of CHUNK_SIZE.
BACKWARD_MERGE_TOLERANCE = 1.5
MERGE_SEPARATOR = "\n\n"
# Part of the CHUNKER signature: changing the merge rules must reprocess documents.
SMALL_CHUNK_POLICY = f"merge=fwd,back{BACKWARD_MERGE_TOLERANCE}x,keep"

_NO_LETTERS_OR_DIGITS = re.compile(r"[\W_]*")
_PAGE_NUMBER = re.compile(
    r"(?i)(?:p[áa]g(?:ina)?\.?|page|p\.)?\s*\d{1,4}(?:\s*(?:/|de|of)\s*\d{1,4})?"
)


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    heading_path: str


@dataclass(frozen=True)
class Piece:
    """A piece of splitter output, before the small-chunk policy is applied.

    `section` numbers the heading section the piece came from. `start` and `end` are
    character offsets within that section: `start` of the piece's first character, `end`
    of its last one. They let two overlapping pieces of the same section be joined without
    repeating the overlap.
    """

    path: tuple[str, ...]
    text: str
    section: int = 0
    start: int = 0
    end: int = 0
    end_section: int = 0


def normalize_markdown(text: str) -> str:
    """Strip a leading BOM and convert CRLF and lone CR line endings to LF."""
    return text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")


def chunk_markdown(text: str, *, size: int, overlap: int, min_size: int) -> list[Chunk]:
    pieces = split_markdown(text, size=size, overlap=overlap)
    merged = apply_small_chunk_policy(
        pieces, min_size=min_size, max_merged=int(size * BACKWARD_MERGE_TOLERANCE)
    )
    return [
        Chunk(index=i, text=piece.text, heading_path=HEADING_SEPARATOR.join(piece.path))
        for i, piece in enumerate(merged)
    ]


def split_markdown(text: str, *, size: int, overlap: int) -> list[Piece]:
    """Split by h1-h3 headings, then split long sections by characters (langchain)."""
    sections = MarkdownHeaderTextSplitter(HEADING_LEVELS, strip_headers=True).split_text(
        normalize_markdown(text)
    )
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap, add_start_index=True
    )
    pieces: list[Piece] = []
    for number, section in enumerate(sections):
        path = tuple(section.metadata[key] for _, key in HEADING_LEVELS if key in section.metadata)
        # MarkdownHeaderTextSplitter turns blank lines into "  \n"; without real paragraph
        # breaks the character splitter cannot prefer splitting between paragraphs.
        body = section.page_content.replace("  \n", "\n\n")
        for doc in splitter.create_documents([body]):
            start = doc.metadata["start_index"]
            pieces.append(
                Piece(
                    path=path,
                    text=doc.page_content,
                    section=number,
                    start=start,
                    end=start + len(doc.page_content),
                    end_section=number,
                )
            )
    return pieces


def has_content(text: str) -> bool:
    """False for text that carries no information: blank, separators only, or a page number."""
    stripped = text.strip()
    if _NO_LETTERS_OR_DIGITS.fullmatch(stripped):
        return False
    # Decorations around page numbers, e.g. "- 4 -", "\u2013 4 \u2013" (en dash), "(4)".
    return not _PAGE_NUMBER.fullmatch(stripped.strip(" -\u2013\u2014\u00b7|.()[]"))


def apply_small_chunk_policy(pieces: list[Piece], *, min_size: int, max_merged: int) -> list[Piece]:
    """Merge small pieces instead of discarding them; a short chunk can be the critical one.

    Rules, in order:
    1. No content at all (blank, separators, a page number): dropped.
    2. Below `min_size` and followed by a piece of the same section (same heading path or a
       subsection of it): merged forward into that piece.
    3. Below `min_size` and last in its section: merged backward into the previous piece of
       the same section, if the result is at most `max_merged` characters.
    4. Otherwise kept as its own chunk.
    Merges never cross into an unrelated section. The merged piece keeps the heading path of
    the piece it was merged into.
    """
    result: list[Piece] = []
    pending: Piece | None = None
    for piece in (p for p in pieces if has_content(p.text)):
        if pending is not None:
            if _same_section(pending, piece):
                piece = _join(pending, piece, path=piece.path)
            else:
                _merge_backward_or_keep(result, pending, max_merged)
            pending = None
        if len(piece.text) < min_size:
            pending = piece
        else:
            result.append(piece)
    if pending is not None:
        _merge_backward_or_keep(result, pending, max_merged)
    return result


def _merge_backward_or_keep(result: list[Piece], small: Piece, max_merged: int) -> None:
    if result and _same_section(result[-1], small):
        joined = _join(result[-1], small, path=result[-1].path)
        if len(joined.text) <= max_merged:
            result[-1] = joined
            return
    result.append(small)


def _same_section(a: Piece, b: Piece) -> bool:
    """True if both pieces share a heading path or one is a subsection of the other."""
    shorter = min(len(a.path), len(b.path))
    return a.path[:shorter] == b.path[:shorter]


def _join(first: Piece, second: Piece, *, path: tuple[str, ...]) -> Piece:
    overlap = first.end - second.start if first.end_section == second.section else 0
    if overlap > 0:
        text = first.text + second.text[overlap:]
    else:
        text = first.text + MERGE_SEPARATOR + second.text
    return replace(first, path=path, text=text, end=second.end, end_section=second.end_section)
