"""Search the knowledge base: embed a query, find the nearest chunks. This module owns the
transaction; the SQL lives in `db/repository.py`.

Queries can be as sensitive as the documents: neither the query text nor the chunks found
are logged, only tenants, counts and durations.
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.db import repository
from ayo_copilot.db.repository import SearchHit
from ayo_copilot.ingestion.embedding import Embedder
from ayo_copilot.ingestion.service import current_configs

logger = logging.getLogger(__name__)

# Decimals of the reported similarity.
SIMILARITY_DECIMALS = 4


@dataclass(frozen=True)
class SearchResult:
    rank: int
    # 1 - cosine distance, rounded: 1 for the same direction, 0 for orthogonal vectors.
    similarity: float
    hit: SearchHit


@dataclass(frozen=True)
class SearchOutcome:
    results: list[SearchResult]
    # Documents matching the filters but left out: embedded with another config.
    embedder_mismatch: int
    # The text sent to the embedder (the query itself: Voyage adds its prompt server-side).
    embedded_query: str
    embedder_config: str
    chunker_config: str
    embed_ms: float
    search_ms: float
    total_ms: float


def search(
    pool: ConnectionPool,
    embedder: Embedder,
    settings: Settings,
    *,
    query: str,
    top_k: int,
    tenants: Sequence[str] | None = None,
    doc_ids: Sequence[str] | None = None,
    min_similarity: float | None = None,
    include_outdated: bool = False,
    clock: Callable[[], float] = time.perf_counter,
) -> SearchOutcome:
    """The `top_k` chunks nearest to `query`, nearest first, with `min_similarity` (if
    given) dropping weaker ones. Input is assumed valid (the API schema checks it).

    The embedder is called before the transaction opens; an `EmbeddingError` propagates
    and nothing is read. The search and the skipped count share one read-only snapshot.
    """
    chunker_config, embedder_config = current_configs(settings)
    started = clock()
    vector = embedder.embed_query(query)
    embedded = clock()
    with pool.connection() as conn, conn.transaction():
        conn.execute("set transaction isolation level repeatable read, read only")
        hits = repository.search_chunks(
            conn,
            embedding=vector,
            embedder_config=embedder_config,
            limit=top_k,
            tenants=tenants,
            doc_ids=doc_ids,
            include_outdated=include_outdated,
        )
        mismatched = (
            0
            if include_outdated
            else repository.count_embedder_mismatches(
                conn, embedder_config=embedder_config, tenants=tenants, doc_ids=doc_ids
            )
        )
    finished = clock()

    # Nearest first, so the threshold only cuts the tail: filtering after the limit is
    # the same as before it, and keeps the distance out of the SQL filter.
    kept = [hit for hit in hits if min_similarity is None or 1 - hit.distance >= min_similarity]
    results = [
        SearchResult(rank=i, similarity=round(1 - hit.distance, SIMILARITY_DECIMALS), hit=hit)
        for i, hit in enumerate(kept, start=1)
    ]
    outcome = SearchOutcome(
        results=results,
        embedder_mismatch=mismatched,
        embedded_query=query,
        embedder_config=embedder_config,
        chunker_config=chunker_config,
        embed_ms=(embedded - started) * 1000,
        search_ms=(finished - embedded) * 1000,
        total_ms=(finished - started) * 1000,
    )
    logger.info(
        "search: tenants=%s doc_ids=%d top_k=%d results=%d skipped_embedder=%d"
        " embed_ms=%.0f search_ms=%.0f",
        ",".join(tenants) if tenants is not None else "*",
        len(doc_ids) if doc_ids is not None else 0,
        top_k,
        len(results),
        mismatched,
        outcome.embed_ms,
        outcome.search_ms,
    )
    return outcome
