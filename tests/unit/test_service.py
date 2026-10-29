import pytest

from ayo_copilot.config import Settings
from ayo_copilot.ingestion import signatures
from ayo_copilot.ingestion.chunking import Chunk
from ayo_copilot.ingestion.embedding import FakeEmbedder
from ayo_copilot.ingestion.service import (
    chunk_document,
    compute_signatures,
    current_configs,
    decode_markdown,
    document_status,
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


def test_compute_signatures_matches_the_signature_functions() -> None:
    markdown = "# Título\n\nTexto del procedimiento.\n"

    sigs = compute_signatures(markdown, SETTINGS)

    content_hash = signatures.content_hash(markdown)
    chunker = signatures.chunker_descriptor(
        size=SETTINGS.chunk_size, overlap=SETTINGS.chunk_overlap, min_size=SETTINGS.min_chunk_size
    )
    embedder = signatures.embedder_descriptor(
        model=SETTINGS.embedding_model, dimensions=SETTINGS.embedding_dimensions
    )
    chunk_signature = signatures.chunk_signature(content_hash, chunker)
    assert (sigs.content_hash, sigs.chunker_config, sigs.embedder_config) == (
        content_hash,
        chunker,
        embedder,
    )
    assert sigs.chunk_signature == chunk_signature
    assert sigs.embed_signature == signatures.embed_signature(chunk_signature, embedder)


def test_compute_signatures_changes_with_the_settings() -> None:
    markdown = "# Título\n\nTexto.\n"
    other = Settings(
        _env_file=None, admin_api_key="k", embedding_provider="fake", embedding_model="voyage-x"
    )

    before, after = compute_signatures(markdown, SETTINGS), compute_signatures(markdown, other)

    assert before.chunk_signature == after.chunk_signature
    assert before.embedder_config != after.embedder_config
    assert before.embed_signature != after.embed_signature


CURRENT_CHUNKER, CURRENT_EMBEDDER = current_configs(SETTINGS)


@pytest.mark.parametrize(
    ("chunker", "embedder", "expected"),
    [
        (CURRENT_CHUNKER, CURRENT_EMBEDDER, ("indexed", None)),
        ("old-chunker", CURRENT_EMBEDDER, ("outdated", "chunker_changed")),
        (CURRENT_CHUNKER, "old-embedder", ("outdated", "embedder_changed")),
        ("old-chunker", "old-embedder", ("outdated", "chunker_changed")),
        (None, CURRENT_EMBEDDER, ("outdated", "unknown")),
        (CURRENT_CHUNKER, None, ("outdated", "unknown")),
        (None, None, ("outdated", "unknown")),
    ],
)
def test_document_status(chunker: str | None, embedder: str | None, expected: tuple) -> None:
    assert document_status(chunker, embedder, SETTINGS) == expected


def test_a_settings_change_makes_stored_configs_outdated() -> None:
    changed = Settings(_env_file=None, admin_api_key="k", embedding_provider="fake", chunk_size=300)

    assert document_status(CURRENT_CHUNKER, CURRENT_EMBEDDER, changed) == (
        "outdated",
        "chunker_changed",
    )


def test_current_configs_are_what_compute_signatures_stores() -> None:
    sigs = compute_signatures("# Título\n\nTexto.\n", SETTINGS)

    assert current_configs(SETTINGS) == (sigs.chunker_config, sigs.embedder_config)
