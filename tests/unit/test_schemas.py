from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import DocumentRow, SearchHit
from ayo_copilot.ingestion.service import current_configs
from ayo_copilot.schemas import Document, DocumentUpdate, SearchRequest, SearchResponse
from ayo_copilot.search import SearchOutcome, SearchResult

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


# --- search ---------------------------------------------------------------------


def test_search_request_defaults() -> None:
    request = SearchRequest(query="¿Cómo priorizo los defectos?")

    assert request.model_dump() == {
        "query": "¿Cómo priorizo los defectos?",
        "tenants": None,
        "top_k": 5,
        "min_similarity": None,
        "doc_ids": None,
        "include_outdated": False,
        "debug": False,
    }


def test_search_query_is_trimmed_and_may_be_2000_characters() -> None:
    assert SearchRequest(query="  ¿Qué es OEE?\n").query == "¿Qué es OEE?"
    assert len(SearchRequest(query="ñ" * 2000).query) == 2000


def test_search_bounds_are_inclusive() -> None:
    request = SearchRequest(
        query="q", top_k=50, min_similarity=1, tenants=["ayo"], doc_ids=["upload-" + "0" * 12]
    )
    assert (request.top_k, request.min_similarity) == (50, 1)
    assert SearchRequest(query="q", top_k=1, min_similarity=0).min_similarity == 0
    assert (
        len(SearchRequest(query="q", tenants=[f"t{i:02}" for i in range(50)]).tenants or []) == 50
    )


@pytest.mark.parametrize(
    ("body", "error_type", "loc"),
    [
        ({}, "missing", ("query",)),
        ({"query": ""}, "string_too_short", ("query",)),
        ({"query": " \t\n "}, "string_too_short", ("query",)),
        ({"query": "a" * 2001}, "string_too_long", ("query",)),
        ({"query": "q", "top_k": 0}, "greater_than_equal", ("top_k",)),
        ({"query": "q", "top_k": 51}, "less_than_equal", ("top_k",)),
        ({"query": "q", "min_similarity": -0.1}, "greater_than_equal", ("min_similarity",)),
        ({"query": "q", "min_similarity": 1.1}, "less_than_equal", ("min_similarity",)),
        ({"query": "q", "tenants": ["Cliente ACME"]}, "string_pattern_mismatch", ("tenants", 0)),
        ({"query": "q", "tenants": []}, "too_short", ("tenants",)),
        ({"query": "q", "tenants": [f"t{i:02}" for i in range(51)]}, "too_long", ("tenants",)),
        ({"query": "q", "tenants": ["ayo", "ayo"]}, "duplicate_tenants", ("tenants",)),
        ({"query": "q", "doc_ids": ["pareto.md"]}, "string_pattern_mismatch", ("doc_ids", 0)),
        ({"query": "q", "doc_ids": []}, "too_short", ("doc_ids",)),
        (
            {"query": "q", "doc_ids": [f"upload-{i:012x}" for i in range(51)]},
            "too_long",
            ("doc_ids",),
        ),
        (
            {"query": "q", "doc_ids": ["upload-000000000000"] * 2},
            "duplicate_doc_ids",
            ("doc_ids",),
        ),
        ({"query": "q", "tenant": "ayo"}, "extra_forbidden", ("tenant",)),
    ],
)
def test_search_request_rejects_invalid_bodies(
    body: dict[str, object], error_type: str, loc: tuple[str | int, ...]
) -> None:
    with pytest.raises(ValidationError) as raised:
        SearchRequest.model_validate(body)

    (error,) = raised.value.errors()
    assert (error["type"], error["loc"]) == (error_type, loc)


def search_outcome(**overrides: object) -> SearchOutcome:
    hit = SearchHit(
        chunk_id=uuid4(),
        chunk_index=3,
        heading=None,
        chunk_text="Usa el diagrama de Pareto.",
        char_count=26,
        doc_id="upload-3f9a1c2b7d4e",
        title=None,
        source_key="pareto.md",
        tenant="ayo",
        embedder_outdated=True,
        distance=0.12,
    )
    values: dict[str, object] = {
        "results": [SearchResult(rank=1, similarity=0.88, hit=hit)],
        "embedder_mismatch": 2,
        "embedded_query": "¿Pareto?",
        "embedder_config": EMBEDDER,
        "chunker_config": CHUNKER,
        "embed_ms": 41.26,
        "search_ms": 0.04,
        "total_ms": 41.3,
    }
    values.update(overrides)
    return SearchOutcome(**values)


def test_search_response_without_debug_keeps_debug_null() -> None:
    body = SearchResponse.from_outcome(search_outcome(), debug=False).model_dump(mode="json")

    (result,) = body["results"]
    assert body["query"] == "¿Pareto?"
    assert body["skipped"] == {"embedder_mismatch": 2}
    assert body["debug"] is None
    assert (result["heading"], result["document_title"]) == (None, None)
    assert (result["rank"], result["similarity"], result["embedder_outdated"]) == (1, 0.88, True)
    assert result["chunk_text"] == "Usa el diagrama de Pareto."


def test_search_response_debug_rounds_timings_to_a_tenth() -> None:
    body = SearchResponse.from_outcome(search_outcome(), debug=True).model_dump(mode="json")

    assert body["debug"] == {
        "embedded_query": "¿Pareto?",
        "input_type": "query",
        "embedder_config": EMBEDDER,
        "chunker_config": CHUNKER,
        "timings_ms": {"embed": 41.3, "search": 0.0, "total": 41.3},
    }
