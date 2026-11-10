"""Search against a real pgvector: ordering, similarity, filters, outdated documents and
the filtered-HNSW pitfall (ADR 0002). Vectors are placed on chosen axes, so each expected
similarity is exact."""

import logging
from collections.abc import Sequence

import pytest
from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.db.repository import (
    ChunkRecord,
    DocumentRecord,
    replace_chunks,
    search_chunks,
    upsert_document,
)
from ayo_copilot.ingestion.embedding import EmbeddingError, FakeEmbedder
from ayo_copilot.ingestion.service import current_configs
from ayo_copilot.ingestion.signatures import make_doc_id
from ayo_copilot.search import search
from tests.integration.support import ScriptedEmbedder, axis_vector

pytestmark = pytest.mark.integration

SETTINGS = Settings(_env_file=None, admin_api_key="k", embedding_provider="fake")
CHUNKER, EMBEDDER = current_configs(SETTINGS)
QUERY = "¿Cómo priorizo seis tipos de defecto?"
# The query points along axis 0.
QUERY_VECTOR = axis_vector((0, 1.0))


def store(
    pool: ConnectionPool,
    vectors: Sequence[list[float]],
    *,
    tenant: str = "ayo",
    source_key: str = "pareto.md",
    embedder_config: str | None = EMBEDDER,
    chunker_config: str | None = CHUNKER,
) -> str:
    doc_id = make_doc_id(tenant, source_key)
    document = DocumentRecord(
        doc_id=doc_id,
        tenant=tenant,
        source_key=source_key,
        title=f"Título de {source_key}",
        markdown="# Método Pareto\n",
        content_hash="h",
        chunk_signature="c",
        embed_signature="e",
        chunk_count=len(vectors),
        chunker_config=chunker_config,
        embedder_config=embedder_config,
    )
    chunks = [
        ChunkRecord(index=i, heading=f"Pareto > Paso {i}", text=f"Fragmento {i}", embedding=v)
        for i, v in enumerate(vectors)
    ]
    with pool.connection() as conn, conn.transaction():
        replace_chunks(conn, upsert_document(conn, document), chunks)
    return doc_id


def run(pool: ConnectionPool, embedder=None, **kwargs):
    embedder = embedder or ScriptedEmbedder({QUERY: QUERY_VECTOR})
    kwargs.setdefault("top_k", 5)
    return search(pool, embedder, SETTINGS, query=QUERY, **kwargs)


def summary(outcome) -> list[tuple[int, str, int, float]]:
    return [(r.rank, r.hit.doc_id, r.hit.chunk_index, r.similarity) for r in outcome.results]


# --- ordering and similarity ---------------------------------------------------


def test_nearest_first_with_exact_similarities(db_pool: ConnectionPool) -> None:
    doc_id = store(
        db_pool,
        [
            axis_vector((1, 1.0)),  # orthogonal
            axis_vector((0, 1.0)),  # identical direction
            axis_vector((0, 0.6), (1, 0.8)),  # cosine 0.6
            axis_vector((0, -1.0)),  # opposite
        ],
    )

    outcome = run(db_pool, top_k=10)

    assert summary(outcome) == [
        (1, doc_id, 1, 1.0),
        (2, doc_id, 2, 0.6),
        (3, doc_id, 0, 0.0),
        (4, doc_id, 3, -1.0),
    ]
    best = outcome.results[0].hit
    assert (best.heading, best.chunk_text, best.char_count) == (
        "Pareto > Paso 1",
        "Fragmento 1",
        11,
    )
    assert (best.title, best.source_key, best.tenant) == ("Título de pareto.md", "pareto.md", "ayo")
    assert best.embedder_outdated is False


def test_similarity_is_rounded_to_four_decimals(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0), (1, 0.123456))])

    (result,) = run(db_pool).results

    assert result.similarity == round(1 / (1 + 0.123456**2) ** 0.5, 4)


def test_ties_are_broken_by_chunk_id(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0), (1, 1.0))] * 6)

    first, second = run(db_pool, top_k=6), run(db_pool, top_k=6)

    ids = [r.hit.chunk_id for r in first.results]
    assert ids == sorted(ids)
    assert ids == [r.hit.chunk_id for r in second.results]


def test_top_k_larger_than_the_knowledge_base(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0)), axis_vector((1, 1.0))])

    assert [r.rank for r in run(db_pool, top_k=50).results] == [1, 2]


def test_empty_knowledge_base(db_pool: ConnectionPool) -> None:
    outcome = run(db_pool)

    assert (outcome.results, outcome.embedder_mismatch) == ([], 0)


# --- filters --------------------------------------------------------------------


def test_never_returns_another_tenants_chunks(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0))], tenant="cliente-globex")
    acme = store(db_pool, [axis_vector((0, 0.2), (1, 1.0))], tenant="cliente-acme")
    ayo = store(db_pool, [axis_vector((0, 0.1), (2, 1.0))], tenant="ayo")

    outcome = run(db_pool, tenants=["cliente-acme", "ayo"])

    assert [r.hit.doc_id for r in outcome.results] == [acme, ayo]


def test_no_tenant_filter_searches_every_tenant(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0))], tenant="cliente-globex")
    store(db_pool, [axis_vector((0, 1.0))], tenant="ayo")

    assert len(run(db_pool, tenants=None).results) == 2


def test_filters_matching_nothing_return_no_results(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0))])

    assert run(db_pool, tenants=["cliente-nadie"]).results == []
    assert run(db_pool, doc_ids=[]).results == []


def test_doc_ids_restrict_the_search(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0))], source_key="cerca.md")
    far = store(db_pool, [axis_vector((0, 0.1), (1, 1.0))], source_key="lejos.md")

    outcome = run(db_pool, doc_ids=[far])

    assert [r.hit.doc_id for r in outcome.results] == [far]


def test_min_similarity_drops_weaker_results(db_pool: ConnectionPool) -> None:
    store(
        db_pool,
        [axis_vector((0, 1.0)), axis_vector((0, 0.6), (1, 0.8)), axis_vector((1, 1.0))],
    )

    assert [r.similarity for r in run(db_pool, min_similarity=0.6).results] == [1.0, 0.6]
    assert [r.similarity for r in run(db_pool, min_similarity=0.61).results] == [1.0]
    assert len(run(db_pool, min_similarity=0.0).results) == 3


# --- outdated documents ---------------------------------------------------------


def test_documents_of_another_embedder_are_skipped_and_counted(db_pool: ConnectionPool) -> None:
    current = store(db_pool, [axis_vector((0, 0.5), (1, 1.0))], source_key="actual.md")
    store(db_pool, [axis_vector((0, 1.0))], source_key="viejo.md", embedder_config="otro/1024")
    store(db_pool, [axis_vector((0, 1.0))], source_key="sin-config.md", embedder_config=None)

    outcome = run(db_pool)

    assert [r.hit.doc_id for r in outcome.results] == [current]
    assert outcome.embedder_mismatch == 2


def test_skipped_count_follows_the_filters(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0))], tenant="ayo", embedder_config="otro/1024")
    store(db_pool, [axis_vector((0, 1.0))], tenant="cliente-acme", embedder_config="otro/1024")

    assert run(db_pool, tenants=["ayo"]).embedder_mismatch == 1
    assert run(db_pool, doc_ids=[make_doc_id("ayo", "pareto.md")]).embedder_mismatch == 1


def test_include_outdated_returns_them_flagged(db_pool: ConnectionPool) -> None:
    current = store(db_pool, [axis_vector((0, 0.5), (1, 1.0))], source_key="actual.md")
    old = store(db_pool, [axis_vector((0, 1.0))], source_key="viejo.md", embedder_config="o/1")
    unknown = store(
        db_pool, [axis_vector((0, 0.1), (1, 1.0))], source_key="nulo.md", embedder_config=None
    )

    outcome = run(db_pool, include_outdated=True)

    assert [(r.hit.doc_id, r.hit.embedder_outdated) for r in outcome.results] == [
        (old, True),
        (current, False),
        (unknown, True),
    ]
    assert outcome.embedder_mismatch == 0


def test_a_chunker_change_alone_is_searched_normally(db_pool: ConnectionPool) -> None:
    doc_id = store(db_pool, [axis_vector((0, 1.0))], chunker_config="chunker-viejo")
    store(db_pool, [axis_vector((0, 1.0))], source_key="nulo.md", chunker_config=None)

    outcome = run(db_pool)

    assert doc_id in [r.hit.doc_id for r in outcome.results]
    assert len(outcome.results) == 2
    assert outcome.embedder_mismatch == 0


# --- the filtered-HNSW pitfall (ADR 0002): exact search is immune ------------


def hnsw_plan(conn, embedding: list[float]) -> str:
    rows = conn.execute(
        "explain select c.id from chunks c join documents d on d.id = c.document_id"
        " where d.tenant = any(%s) order by c.embedding <=> %s::vector limit 5",
        (["cliente-acme"], str(embedding)),
    ).fetchall()
    return "\n".join(line for (line,) in rows)


def test_a_selective_tenant_filter_returns_top_k_where_the_index_would_not(
    db_pool: ConnectionPool,
) -> None:
    # 300 chunks of other tenants, all closer to the query than any of the target's 10.
    for t in range(10):
        store(
            db_pool,
            [axis_vector((0, 1.0), (1 + t * 30 + i, 0.3)) for i in range(30)],
            tenant=f"cliente-otro-{t}",
        )
    target = [axis_vector((0, 0.5), (301 + i, 1.0 + i / 100)) for i in range(10)]
    store(db_pool, target, tenant="cliente-acme")

    with db_pool.connection() as conn, conn.transaction():
        conn.execute("analyze chunks")
        conn.execute("analyze documents")
        # Push the planner towards the HNSW index, as on a larger knowledge base.
        conn.execute("set local enable_seqscan = off")
        conn.execute("set local enable_bitmapscan = off")
        conn.execute("set local enable_sort = off")
        assert "chunks_embedding_hnsw_idx" in hnsw_plan(conn, QUERY_VECTOR)
        # Control: without iterative scans the index stops at `ef_search` candidates,
        # all of other tenants, and the filter leaves fewer than 5.
        conn.execute("set local hnsw.iterative_scan = off")
        plain = conn.execute(
            "select count(*) from (select c.id from chunks c"
            " join documents d on d.id = c.document_id where d.tenant = 'cliente-acme'"
            " order by c.embedding <=> %s::vector limit 5) s",
            (str(QUERY_VECTOR),),
        ).fetchone()
        assert plain is not None and plain[0] < 5

        hits = search_chunks(
            conn,
            embedding=QUERY_VECTOR,
            embedder_config=EMBEDDER,
            tenants=["cliente-acme"],
            limit=5,
        )

    assert [h.tenant for h in hits] == ["cliente-acme"] * 5
    # Exact: the five nearest of the target's chunks, nearest first.
    assert [h.chunk_index for h in hits] == [0, 1, 2, 3, 4]


# --- embedder and logging -------------------------------------------------------


def test_the_query_goes_through_embed_query(db_pool: ConnectionPool) -> None:
    store(db_pool, [axis_vector((0, 1.0))])
    embedder = FakeEmbedder(dimensions=1024)

    outcome = search(db_pool, embedder, SETTINGS, query=QUERY, top_k=5)

    assert (embedder.query_calls, embedder.calls) == ([QUERY], [])
    assert outcome.embedded_query == QUERY
    assert (outcome.embedder_config, outcome.chunker_config) == (EMBEDDER, CHUNKER)


def test_an_embedder_failure_propagates_before_any_read() -> None:
    class FailingEmbedder:
        def embed_query(self, text: str) -> list[float]:
            raise EmbeddingError("Embedding provider returned HTTP 503")

    class NoPool:
        def connection(self):
            raise AssertionError("the database is not touched when embedding fails")

    with pytest.raises(EmbeddingError):
        search(NoPool(), FailingEmbedder(), SETTINGS, query=QUERY, top_k=5)  # type: ignore[arg-type]


def test_timings_are_measured_around_each_stage(db_pool: ConnectionPool) -> None:
    ticks = iter([10.0, 10.040, 10.046])

    outcome = run(db_pool, clock=lambda: next(ticks))

    assert (outcome.embed_ms, outcome.search_ms, outcome.total_ms) == pytest.approx(
        (40.0, 6.0, 46.0)
    )


def test_logs_carry_neither_the_query_nor_the_chunks(
    db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    store(db_pool, [axis_vector((0, 1.0))])

    with caplog.at_level(logging.DEBUG):
        run(db_pool, tenants=["ayo"])

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "tenants=ayo" in text and "results=1" in text
    assert QUERY not in text and "Fragmento" not in text
