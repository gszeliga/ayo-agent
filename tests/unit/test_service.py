import pytest

from ayo_copilot.config import Settings
from ayo_copilot.ingestion.chunking import Chunk
from ayo_copilot.ingestion.embedding import FakeEmbedder
from ayo_copilot.ingestion.service import (
    chunk_document,
    decode_markdown,
    embed_chunks,
    embedding_text,
    first_h1,
    resolve_title,
)
from ayo_copilot.ingestion.storage import InvalidInputError

SETTINGS = Settings(_env_file=None, admin_api_key="k", embedding_provider="fake")


def test_decode_normalizes_bom_and_line_endings() -> None:
    raw = "﻿# Título\r\n\r\nLínea con ñ\rfin\n".encode()

    assert decode_markdown(raw) == "# Título\n\nLínea con ñ\nfin\n"


@pytest.mark.parametrize("raw", [b"", b"   \n\t\r\n", "﻿".encode()])
def test_decode_rejects_blank_files(raw: bytes) -> None:
    with pytest.raises(InvalidInputError, match="empty") as exc:
        decode_markdown(raw)
    assert (exc.value.field, exc.value.code) == ("file", "file_empty")


@pytest.mark.parametrize("raw", [b"\xff\xfe# T\x00", "Señal".encode("latin-1")])
def test_decode_rejects_invalid_utf8(raw: bytes) -> None:
    with pytest.raises(InvalidInputError, match="UTF-8") as exc:
        decode_markdown(raw)
    assert (exc.value.field, exc.value.code) == ("file", "file_encoding")


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# PRO-014 Control de sellado\n\nTexto", "PRO-014 Control de sellado"),
        ("Intro\n\n## Sección\n\n# Título real #\n", "Título real"),
        ("```bash\n# un comentario\n```\n\n# Después del código\n", "Después del código"),
        ("~~~\n# dentro\n~~~\n", None),
        ("## Solo h2\n\n#sin espacio\n", None),
    ],
)
def test_first_h1(markdown: str, expected: str | None) -> None:
    assert first_h1(markdown) == expected


def test_title_prefers_given_then_h1_then_file_name() -> None:
    assert resolve_title("  Dado  ", "# H1\n", "a.md") == "Dado"
    assert resolve_title("   ", "# H1\n", "a.md") == "H1"
    assert resolve_title(None, "Sin títulos\n", "a.md") == "a.md"


@pytest.mark.parametrize(
    "markdown",
    ["# Solo un título\n", "# Título\n\n---\n\n## Otro\n\nPágina 3\n", "---\n\n- 4 -\n"],
)
def test_documents_without_indexable_content_are_rejected(markdown: str) -> None:
    with pytest.raises(InvalidInputError, match="no indexable content") as exc:
        chunk_document(markdown, SETTINGS)
    assert (exc.value.field, exc.value.code) == ("file", "file_no_content")


def test_embedding_text_prefixes_the_heading_path() -> None:
    with_path = Chunk(index=0, text="Limpiar la mordaza.", heading_path="PRO-014 > 3. Pasos")
    without_path = Chunk(index=1, text="Texto suelto.", heading_path="")

    assert embedding_text(with_path) == "PRO-014 > 3. Pasos\n\nLimpiar la mordaza."
    assert embedding_text(without_path) == "Texto suelto."


def test_embed_chunks_sends_the_prefixed_texts_in_order() -> None:
    embedder = FakeEmbedder(dimensions=8)
    chunks = chunk_document("# A\n\nPrimero.\n\n# B\n\nSegundo.\n", SETTINGS)

    vectors = embed_chunks(embedder, chunks)

    assert embedder.calls == [["A\n\nPrimero.", "B\n\nSegundo."]]
    assert len(vectors) == 2
