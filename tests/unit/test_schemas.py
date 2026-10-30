from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import DocumentRow
from ayo_copilot.ingestion.service import current_configs
from ayo_copilot.schemas import Document, DocumentUpdate

SETTINGS = Settings(_env_file=None, admin_api_key="k", embedding_provider="fake")
CHUNKER, EMBEDDER = current_configs(SETTINGS)
MADRID = timezone(timedelta(hours=2))
STAMP = datetime(2026, 10, 15, 11, 30, tzinfo=MADRID)

ROW = DocumentRow(
    id=uuid4(),
    doc_id="upload-1890b5dc5335",
    tenant="acme",
    source_type="upload",
    source_key="pro-014.md",
    title="PRO-014",
    content_hash="9f2c1a7e" + "0" * 56,
    chunk_signature="c" * 64,
    embed_signature="e" * 64,
    chunk_count=12,
    size_bytes=8421,
    chunker_config=CHUNKER,
    embedder_config=EMBEDDER,
    created_at=STAMP,
    updated_at=STAMP,
    chunked_at=STAMP,
    embedded_at=None,
)


def test_timestamps_are_serialized_in_utc() -> None:
    body = Document.from_row(ROW, SETTINGS).model_dump(mode="json")

    assert body["created_at"] == body["updated_at"] == body["chunked_at"]
    assert body["created_at"] == "2026-10-15T09:30:00Z"
    assert body["embedded_at"] is None


def test_hashes_and_configs_are_copied_whole() -> None:
    document = Document.from_row(ROW, SETTINGS)

    assert (
        document.content_hash,
        document.chunk_signature,
        document.embed_signature,
        document.chunker_config,
        document.embedder_config,
    ) == (
        ROW.content_hash,
        ROW.chunk_signature,
        ROW.embed_signature,
        ROW.chunker_config,
        ROW.embedder_config,
    )


def test_status_comes_from_the_stored_configs() -> None:
    stale = replace(ROW, embedder_config="voyage-3/document/1024")

    document = Document.from_row(stale, SETTINGS)

    assert (document.status, document.outdated_reason) == ("outdated", "embedder_changed")
    assert Document.from_row(ROW, SETTINGS).status == "indexed"


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("  Válvula ñ \n", "Válvula ñ"),
        ("x", "x"),
        ("a" * 200, "a" * 200),
        ("  " + "a" * 200 + "  ", "a" * 200),
    ],
)
def test_update_title_is_trimmed_and_kept(given: str, stored: str) -> None:
    assert DocumentUpdate.model_validate({"title": given}).title == stored


@pytest.mark.parametrize(
    ("body", "error_type", "loc"),
    [
        ({"title": ""}, "string_too_short", ("title",)),
        ({"title": " \t\n "}, "string_too_short", ("title",)),
        ({"title": "a" * 201}, "string_too_long", ("title",)),
        ({"title": None}, "string_type", ("title",)),
        ({"title": 14}, "string_type", ("title",)),
        ({}, "missing", ("title",)),
        ({"title": "Nuevo", "tenant": "beta"}, "extra_forbidden", ("tenant",)),
    ],
)
def test_update_rejects_invalid_bodies(
    body: dict[str, object], error_type: str, loc: tuple[str, ...]
) -> None:
    with pytest.raises(ValidationError) as caught:
        DocumentUpdate.model_validate(body)

    (error,) = caught.value.errors()
    assert (error["type"], error["loc"]) == (error_type, loc)
