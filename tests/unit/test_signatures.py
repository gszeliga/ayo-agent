import hashlib
import re

import pytest

from ayo_copilot.ingestion.chunking import normalize_markdown
from ayo_copilot.ingestion.signatures import (
    DOC_ID_PATTERN,
    chunk_signature,
    chunker_descriptor,
    content_hash,
    embed_signature,
    embedder_descriptor,
    make_doc_id,
    sig,
)

TEXT = "# PRO-014 Control de sellado\n\n## 1. Objeto\n\nVerificar la presión de sellado.\n"


def test_sig_joins_parts_with_pipe() -> None:
    assert sig("a", 1, "b") == hashlib.sha256(b"a|1|b").hexdigest()


def test_normalize_markdown_strips_bom_and_crlf() -> None:
    assert normalize_markdown("﻿uno\r\ndos\rtres\n") == "uno\ndos\ntres\n"


def test_content_hash_ignores_line_endings_and_bom() -> None:
    crlf = "﻿" + TEXT.replace("\n", "\r\n")

    assert content_hash(normalize_markdown(crlf)) == content_hash(normalize_markdown(TEXT))


def test_content_hash_changes_with_content() -> None:
    assert content_hash(TEXT) != content_hash(TEXT + "Añadido.\n")


def test_chunker_descriptor_reflects_configuration() -> None:
    assert (
        chunker_descriptor(size=800, overlap=80, min_size=100)
        == "md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1"
    )


def test_embedder_descriptor_reflects_configuration() -> None:
    assert embedder_descriptor(model="voyage-4", dimensions=1024) == "voyage-4/document/1024"


def test_changing_chunk_size_changes_chunk_and_embed_signatures_only() -> None:
    chash = content_hash(TEXT)
    embedder = embedder_descriptor(model="voyage-4", dimensions=1024)
    before = chunk_signature(chash, chunker_descriptor(size=800, overlap=80, min_size=50))
    after = chunk_signature(chash, chunker_descriptor(size=500, overlap=80, min_size=50))

    assert before != after
    assert embed_signature(before, embedder) != embed_signature(after, embedder)


def test_changing_model_changes_embed_signature_only() -> None:
    chunk_sig = chunk_signature(
        content_hash(TEXT), chunker_descriptor(size=800, overlap=80, min_size=50)
    )

    v4 = embed_signature(chunk_sig, embedder_descriptor(model="voyage-4", dimensions=1024))
    lite = embed_signature(chunk_sig, embedder_descriptor(model="voyage-4-lite", dimensions=1024))

    assert v4 != lite


def test_changing_content_changes_every_signature() -> None:
    chunker = chunker_descriptor(size=800, overlap=80, min_size=50)
    embedder = embedder_descriptor(model="voyage-4", dimensions=1024)
    a = chunk_signature(content_hash(TEXT), chunker)
    b = chunk_signature(content_hash(TEXT + "x"), chunker)

    assert a != b
    assert embed_signature(a, embedder) != embed_signature(b, embedder)


def test_doc_id_is_deterministic_and_prefixed() -> None:
    expected = "upload-" + hashlib.sha256(b"acme:upload:pro-014.md").hexdigest()[:12]

    assert make_doc_id("acme", "pro-014.md") == expected
    assert make_doc_id("acme", "pro-014.md") == make_doc_id("acme", "pro-014.md")


def test_doc_id_differs_between_tenants() -> None:
    assert make_doc_id("acme", "pro-014.md") != make_doc_id("globex", "pro-014.md")


@pytest.mark.parametrize(("tenant", "source_key"), [("acme", "pro-014.md"), ("b2", "Ñandú.md")])
def test_doc_ids_match_the_documented_pattern(tenant: str, source_key: str) -> None:
    assert re.fullmatch(DOC_ID_PATTERN, make_doc_id(tenant, source_key))
