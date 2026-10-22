from pathlib import Path

import pytest

from ayo_copilot.ingestion.chunking import (
    Chunk,
    Piece,
    apply_small_chunk_policy,
    chunk_markdown,
    has_content,
)

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "pro-014-control-sellado.md").read_text(
    encoding="utf-8"
)
SIZE, OVERLAP, MIN_SIZE = 800, 80, 100


def chunk(text: str, *, size: int = SIZE, overlap: int = OVERLAP, min_size: int = MIN_SIZE):
    return chunk_markdown(text, size=size, overlap=overlap, min_size=min_size)


def long_paragraph(sentences: int) -> str:
    return " ".join(
        f"La frase {i} describe el ajuste de la válvula de presión." for i in range(sentences)
    )


def words(text: str) -> list[str]:
    return text.split()


def split_lines(markdown: str) -> tuple[list[str], list[str]]:
    """Return (headings, body lines): h1-h3 heading titles and the other non-empty lines.

    Lines inside fenced code blocks are always body lines.
    """
    headings: list[str] = []
    body: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith(("# ", "## ", "### ")):
            headings.append(line.lstrip("#").strip())
        elif line.strip():
            body.append(line.strip())
    return headings, body


def body_lines(markdown: str) -> list[str]:
    return split_lines(markdown)[1]


# --- structure and heading paths ---------------------------------------------------------


def test_returns_chunks_with_index_text_and_heading_path() -> None:
    chunks = chunk(FIXTURE)

    assert chunks
    assert all(isinstance(c, Chunk) for c in chunks)


def test_heading_path_joins_h1_to_h3_with_separator() -> None:
    paths = [c.heading_path for c in chunk(FIXTURE)]

    assert "PRO-014 Control de sellado > 1. Objeto" in paths
    assert "PRO-014 Control de sellado > 3. Pasos > 3.1 Preparación" in paths
    assert "PRO-014 Control de sellado > 3. Pasos > 3.2 Medición" in paths


def test_chunk_text_does_not_repeat_the_heading_lines() -> None:
    for c in chunk(FIXTURE):
        assert not c.text.lstrip().startswith("#"), c.text


def test_h4_and_deeper_stay_in_the_text() -> None:
    chunks = chunk("# Manual\n## Uso\n#### Nota interna\nNo tocar la mordaza en caliente.\n")

    assert len(chunks) == 1
    assert chunks[0].heading_path == "Manual > Uso"
    assert "Nota interna" in chunks[0].text


def test_text_without_headings_has_empty_heading_path() -> None:
    chunks = chunk("Texto suelto sin títulos, pero con contenido suficiente para un fragmento.")

    assert [c.heading_path for c in chunks] == [""]


def test_hash_lines_inside_code_blocks_are_not_headings() -> None:
    chunks = chunk(FIXTURE)
    code_chunk = next(c for c in chunks if "plc-export" in c.text)

    assert "# Exportar las lecturas del PLC" in code_chunk.text
    assert all("Exportar las lecturas" not in c.heading_path for c in chunks)


# --- small-chunk policy, end to end --------------------------------------------------------


def test_heading_only_chunk_is_merged_into_the_next_one() -> None:
    # The case observed with MarkdownHeaderTextSplitter: "# Title" + "## 1. Objeto" alone.
    chunks = chunk("# Título\n## 1. Objeto\n" + long_paragraph(3))

    assert [c.heading_path for c in chunks] == ["Título > 1. Objeto"]
    assert chunks[0].text == long_paragraph(3)


def test_lead_in_line_is_merged_forward_into_its_subsection() -> None:
    text = "# Guía\n## 3. Pasos\nLos pasos son:\n### 3.1 Preparación\n" + long_paragraph(3)

    chunks = chunk(text)

    assert len(chunks) == 1
    assert chunks[0].text.startswith("Los pasos son:\n\n")
    assert chunks[0].heading_path == "Guía > 3. Pasos > 3.1 Preparación"


@pytest.mark.parametrize("separator", ["---", "* * *", "___", "12", "Página 3", "- 4 -", "3 / 10"])
def test_separator_or_page_number_only_chunk_is_dropped(separator: str) -> None:
    text = f"# Guía\n## A\n{long_paragraph(3)}\n## B\n{separator}\n## C\n{long_paragraph(4)}\n"

    chunks = chunk(text)

    assert [c.heading_path for c in chunks] == ["Guía > A", "Guía > C"]


def test_tiny_chunk_between_unrelated_sections_is_kept() -> None:
    warning = "Temperatura máxima: 180 °C."
    text = f"# Guía\n## A\n{long_paragraph(3)}\n## B\n{warning}\n## C\n{long_paragraph(4)}\n"

    chunks = chunk(text)

    assert len(chunks) == 3
    assert (chunks[1].heading_path, chunks[1].text) == ("Guía > B", warning)


def test_tiny_tail_is_merged_backward_within_tolerance() -> None:
    first = long_paragraph(5)[:290].rstrip()
    text = f"# Manual\n## Ajustes\n{first}\n\nFin del procedimiento.\n"

    chunks = chunk(text, size=300, overlap=0)

    assert len(chunks) == 1
    assert chunks[0].text.endswith("Fin del procedimiento.")
    assert 300 < len(chunks[0].text) <= 450


def test_tiny_tail_beyond_tolerance_is_kept() -> None:
    first = long_paragraph(3)[:95].rstrip()
    tail = "Revisar el termopar y registrar la lectura en la hoja de turno."
    text = f"# Manual\n{first}\n\n{tail}\n"

    chunks = chunk(text, size=100, overlap=0, min_size=80)

    assert [c.text for c in chunks] == [first, tail]


def test_a_single_short_document_is_kept() -> None:
    chunks = chunk("# Aviso\n¡Peligro!\n")

    assert [(c.heading_path, c.text) for c in chunks] == [("Aviso", "¡Peligro!")]


def test_document_with_only_headings_has_no_chunks() -> None:
    assert chunk("# Título\n## 1. Objeto\n### 1.1 Detalle\n") == []


@pytest.mark.parametrize("text", ["", "   \n\n", "﻿", "\r\n\r\n", "---\n", "# Título\n---\n"])
def test_documents_without_content_have_no_chunks(text: str) -> None:
    assert chunk(text) == []


# --- invariant: content is only ever dropped by rule 1 -------------------------------------


def test_every_source_line_appears_in_some_chunk() -> None:
    texts = [c.text for c in chunk(FIXTURE)]

    for line in body_lines(FIXTURE):
        assert any(line in t for t in texts), line


def test_every_heading_with_content_appears_in_some_heading_path() -> None:
    paths = {part for c in chunk(FIXTURE) for part in c.heading_path.split(" > ")}

    for heading in split_lines(FIXTURE)[0]:
        assert heading in paths, heading


@pytest.mark.parametrize(("size", "min_size"), [(120, 100), (200, 50), (300, 150)])
def test_all_words_survive_in_order_without_overlap(size: int, min_size: int) -> None:
    chunks = chunk(FIXTURE, size=size, overlap=0, min_size=min_size)

    assert words(" ".join(c.text for c in chunks)) == words(" ".join(body_lines(FIXTURE)))


# --- size, overlap, index, determinism -----------------------------------------------------


def test_long_sections_are_split_within_size_and_tolerance() -> None:
    chunks = chunk("# Manual\n## Ajustes\n" + long_paragraph(40), size=300, overlap=40)

    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks[:-1])
    assert len(chunks[-1].text) <= 450
    assert {c.heading_path for c in chunks} == {"Manual > Ajustes"}


def test_consecutive_pieces_of_a_section_overlap() -> None:
    body = long_paragraph(40)
    chunks = chunk("# Manual\n" + body, size=300, overlap=80)

    assert sum(len(words(c.text)) for c in chunks) > len(words(body))


def test_without_overlap_pieces_do_not_repeat_text() -> None:
    body = long_paragraph(40)
    chunks = chunk("# Manual\n" + body, size=300, overlap=0)

    assert words(" ".join(c.text for c in chunks)) == words(body)


def test_indexes_are_consecutive_from_zero() -> None:
    chunks = chunk(FIXTURE, size=200, overlap=20)

    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_is_deterministic() -> None:
    assert chunk(FIXTURE) == chunk(FIXTURE)


def test_size_changes_the_result() -> None:
    assert chunk(FIXTURE, size=200, overlap=20) != chunk(FIXTURE, size=800, overlap=80)


# --- content preservation and encodings ----------------------------------------------------


def test_lists_tables_and_code_are_kept() -> None:
    joined = "\n".join(c.text for c in chunk(FIXTURE))

    assert "- Limpiar la mordaza con un paño sin pelusa." in joined
    assert "| Presión   | 2,5    | 3,0    | bar    |" in joined
    assert 'plc-export --linea 3 --desde "06:00"' in joined


def test_spanish_characters_are_preserved() -> None:
    joined = "\n".join(c.text for c in chunk(FIXTURE))

    for fragment in ("cómo", "¿Y las máquinas en pruebas?", "¡detener la línea!", "Señalización"):
        assert fragment in joined


def test_crlf_and_bom_give_the_same_chunks() -> None:
    windows = "﻿" + FIXTURE.replace("\n", "\r\n")

    assert chunk(windows) == chunk(FIXTURE)


def test_chunk_text_has_no_carriage_returns() -> None:
    assert all("\r" not in c.text for c in chunk(FIXTURE.replace("\n", "\r\n")))


# --- the merge step on its own ---------------------------------------------------------------


def policy(pieces: list[Piece], *, min_size: int = 10, max_merged: int = 60) -> list[Piece]:
    return apply_small_chunk_policy(pieces, min_size=min_size, max_merged=max_merged)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", False),
        ("  \n ", False),
        ("---", False),
        ("* * *", False),
        ("12", False),
        ("Página 3", False),
        ("pág. 3 de 10", False),
        ("- 4 -", False),
        ("\u2013 4 \u2013", False),
        ("(4)", False),
        ("180 °C", True),
        ("¡Peligro!", True),
        ("Ver anexo 2.", True),
    ],
)
def test_has_content(text: str, expected: bool) -> None:
    assert has_content(text) is expected


def test_policy_merges_forward_within_the_same_path() -> None:
    pieces = [Piece(("A",), "corto"), Piece(("A",), "un texto largo de verdad")]

    assert [p.text for p in policy(pieces)] == ["corto\n\nun texto largo de verdad"]


def test_policy_merges_forward_into_a_subsection_and_takes_its_path() -> None:
    pieces = [Piece(("A",), "corto"), Piece(("A", "A.1"), "un texto largo de verdad")]

    assert [(p.path, p.text) for p in policy(pieces)] == [
        (("A", "A.1"), "corto\n\nun texto largo de verdad")
    ]


def test_policy_merges_backward_within_the_same_path() -> None:
    pieces = [Piece(("A",), "un texto largo de verdad"), Piece(("A",), "corto")]

    assert [p.text for p in policy(pieces)] == ["un texto largo de verdad\n\ncorto"]


def test_policy_never_merges_across_unrelated_sections() -> None:
    pieces = [
        Piece(("A",), "un texto largo de verdad"),
        Piece(("B",), "corto"),
        Piece(("C",), "otro texto largo de verdad"),
    ]

    assert [p.text for p in policy(pieces)] == [p.text for p in pieces]


def test_policy_backward_merge_respects_max_merged() -> None:
    pieces = [Piece(("A",), "x" * 55), Piece(("A",), "corto")]

    assert [p.text for p in policy(pieces)] == ["x" * 55, "corto"]


def test_policy_joins_overlapping_pieces_of_one_section_without_repeating() -> None:
    body = "uno dos tres cuatro cinco"
    first = Piece(("A",), body[:13], section=0, start=0, end=13, end_section=0)
    second = Piece(("A",), body[8:], section=0, start=8, end=len(body), end_section=0)

    merged = policy([first, Piece(("A",), "", section=0), second], min_size=20)

    assert [p.text for p in merged] == [body]


def test_policy_drops_pieces_without_content() -> None:
    pieces = [Piece(("A",), "un texto largo de verdad"), Piece(("A",), "---")]

    assert [p.text for p in policy(pieces)] == ["un texto largo de verdad"]
