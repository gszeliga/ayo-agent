from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import DocumentRow
from ayo_copilot.ingestion.service import current_configs
from ayo_copilot.schemas import DocumentDetail, DocumentSummary

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


def test_summary_timestamps_are_serialized_in_utc() -> None:
    body = DocumentSummary.from_row(ROW, SETTINGS).model_dump(mode="json")

    assert body["created_at"] == body["updated_at"] == "2026-10-15T09:30:00Z"
    assert body["embedded_at"] is None


def test_summary_shortens_the_hash_and_the_detail_does_not() -> None:
    assert DocumentSummary.from_row(ROW, SETTINGS).content_hash == "9f2c1a7e"
    assert DocumentDetail.from_row(ROW, SETTINGS).content_hash == ROW.content_hash


def test_status_comes_from_the_stored_configs() -> None:
    stale = replace(ROW, embedder_config="voyage-3/document/1024")

    summary = DocumentSummary.from_row(stale, SETTINGS)

    assert (summary.status, summary.outdated_reason) == ("outdated", "embedder_changed")
    assert DocumentSummary.from_row(ROW, SETTINGS).status == "indexed"


def test_detail_converts_timestamps_too() -> None:
    assert DocumentDetail.from_row(ROW, SETTINGS).chunked_at == datetime(
        2026, 10, 15, 9, 30, tzinfo=UTC
    )
