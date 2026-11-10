# 0002: Exact vector search for filtered queries

- Status: accepted (2026-11-10)
- Date: 2026-11-10

## Context

`POST /admin/search` (search milestone, `plans/search-progress.md`) returns the `top_k`
chunks nearest to a query, restricted by tenant and document filters, and must not mix
vectors from different embedder configs (`documents.embedder_config`). The production
agent will search one customer's tenant plus the shared `ayo` tenant, so most queries are
filtered. The evaluation harness compares runs before and after a chunker or model change,
so the results should also be reproducible.

`chunks.embedding` has an HNSW index (`vector_cosine_ops`, migration 0001). An HNSW scan
returns its nearest candidates first and applies the `WHERE` afterwards, so a selective
filter can leave fewer than `top_k` rows. pgvector 0.8 adds iterative index scans
(`hnsw.iterative_scan`), which keep scanning until the limit is met.

Versions: pgvector **0.8.7** locally and in tests (`pgvector/pgvector:0.8.7-pg18-trixie`),
**0.8.6** on the Neon dev branch (read-only `select extversion`, 2026-11-10). Both have
iterative scans.

## Evidence

Measured on the local dev database (Docker, Postgres 18, pgvector 0.8.7) in a throwaway
database: random 1024-dimension vectors, 10 chunks per document, 20 tenants (`t00` has one
document, the others share the rest), the query vector as a bound parameter, as psycopg
sends it. `EXPLAIN (ANALYZE)` timings, one run each.

| Query (20,000 chunks unless noted) | Plan the planner chose | Rows | Time |
|---|---|---|---|
| Tenant `t00` (10 chunks), top 5 | exact: tenant index, then sort | 5 | 0.2-0.8 ms |
| No filter, top 5 | HNSW | 5 | 3-9 ms |
| 4 tenants (~20%), top 20, default settings | HNSW, filter after | **5 of 20** | 6.5 ms |
| Same, `hnsw.iterative_scan = strict_order` | HNSW, iterative | 20 | 44 ms |
| `t00`, index forced, iterative scan off | HNSW, filter after | **0 of 5** | 1.2 ms |
| `t00`, index forced, `strict_order` | HNSW, iterative (scanned 8,720 tuples) | 5 | 147 ms |

So default settings return short results under filters. Iterative scans fix those cases,
but they remain approximate. In the integration test's layout (300 chunks of other tenants,
all closer to the query than the target tenant's 10, which are far from everything), the
`strict_order` scan visited the 300 reachable chunks and **returned 0 rows**: the target
chunks were not reachable through the graph's edges. HNSW recall is never guaranteed,
and which plan is picked (exact or HNSW) depends on table statistics, so it can flip as
the data grows. That makes results change for reasons other than the chunker or the model.

Exact search with the final query (a materialized CTE computing the distance of every
chunk that passes the filters, then top-k):

| Chunks that pass the filters | Time |
|---|---|
| 10 | 0.3 ms |
| 1,050 | 13 ms |
| 4,220 | 38-50 ms |
| 20,000 (no filter) | 180-260 ms |

About 9-12 µs per searched chunk, nearly all of it reading the 4 KB vectors (TOAST) and
computing distances. A Voyage query embedding takes much longer than any of these.

## Options

1. **HNSW with default settings.** Fast, but returns short results under filters (above).
2. **HNSW with `hnsw.iterative_scan = strict_order`** set per transaction. Fixes the
   common short-result case and is fast on large sets, but stays approximate (it can miss
   the nearest chunks or return fewer than `top_k`), and plan changes make runs
   hard to compare.
3. **Exact search.** Correct top-k under any filter, deterministic (ties broken by chunk
   id), no settings. Cost is linear in the chunks the filters keep.

## Decision

**Exact search** (option 3), agreed with the user on 2026-11-10. `repository.search_chunks`
computes distances in a `materialized` CTE, which the planner cannot turn into an index
scan, then takes the top `limit` by `(distance, chunk id)` and joins the details for those
rows only. The filters (tenants, doc ids, embedder config) run before the distances, using
the documents indexes.

The HNSW index stays: the search does not use it, but dropping it is a migration, and it
would be needed again for option 2.

## Consequences

- Correct and reproducible results at the current scale. An evaluation `compare` shows
  only the effect of chunker, model or setting changes.
- Cost grows linearly with the chunks one search covers (tenant + `ayo`): about 0.2 s at
  20,000 chunks locally, probably more on Neon. **Revisit** when one search covers about
  20,000 chunks, or its search time (reported by the endpoint's `debug` timings) gets
  noticeable. Then measure option 2 (with `hnsw.ef_search` and `hnsw.max_scan_tuples`)
  against recall measured with the evaluation harness, or partition by tenant.
- `tests/integration/test_search.py` covers the pitfall: with the planner pushed towards
  the index, a plain HNSW query returns fewer than 5 of the target tenant's chunks, and the
  search returns the 5 nearest.
