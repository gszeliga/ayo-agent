# 0002: Exact vector search for filtered queries

- Status: accepted (2026-11-10)
- Date: 2026-11-10
- Updated: 2026-11-14 (TOAST and reprocessing corrections, revisit order, prepared
  halfvec measurement; the decision is unchanged)

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

### Why filters break an HNSW search

An HNSW index is a graph: each chunk is a node linked to about 16 of its nearest
neighbours (`m`). A search starts at an entry point, keeps moving to whichever neighbour
is closer to the query, and keeps a list of the best `hnsw.ef_search` candidates
(default 40). It stops when no neighbour improves that list and returns those
candidates, nearest first.

The index knows nothing about tenants. Postgres applies the `WHERE` to those ~40 rows
only. If the filter keeps 20% of the chunks, about 8 of the 40 survive, and a `limit 20`
query returns those few: there is no way to ask the index for more. A smaller filter,
such as one customer plus `ayo` among many tenants, leaves even fewer, often none.

**Iterative scans** (`hnsw.iterative_scan`, pgvector 0.8) keep searching outward
through the graph when the filter has thrown away too much, until the query has its
`limit` or `hnsw.max_scan_tuples` (default 20,000) is reached. `strict_order` keeps exact
distance order. But a scan only finds nodes it can **reach by following edges**. When the
index is built, each node keeps only its `m` best links. A small group of chunks far from
a dense cluster links out to the cluster, but the cluster's nodes keep their links among
themselves and drop the ones back. Those chunks have edges going out and none coming in,
so no scan starting outside the group can reach them. The test layout below is built
that way on purpose; real embeddings are far less extreme, but the mechanism is the
reason HNSW recall is approximate. The same small, distinct tenant next to a large one
can be poorly linked.

The planner also chooses between the index and an exact scan from table statistics, so
the same query can switch plans, and return different chunks, as data grows.

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

About 9-12 µs per searched chunk, mostly reading the vectors: 1024 floats are 4 KB,
stored out of line (TOAST, uncompressed: `vector` has `external` storage), and fetched
with one TOAST lookup per row. The distance itself is cheap. A Voyage query embedding (about 100-300 ms) takes longer than all of these but
the unfiltered case.

What counts is the number of chunks **one search covers**, not the size of the
database: the tenant and document filters run first, through the ordinary indexes on
`documents`. A production search covers one customer plus `ayo`, so its cost depends on
those two tenants only, however many other customers there are.

Caveats: random vectors, one run each, on a local machine. Neon will probably be slower
(less CPU, storage over the network); it was not measured there to avoid writing test
data to it. The endpoint's `debug.timings_ms.search` reports the real figure per call.

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
  20,000 chunks locally, probably more on Neon.
- `tests/integration/test_search.py` covers the pitfall: with the planner pushed towards
  the index, a plain HNSW query returns fewer than 5 of the target tenant's chunks, and the
  search returns the 5 nearest.

## When to revisit

When one search covers about **20,000 chunks**, or its `debug.timings_ms.search` gets
close to the embedding time. At 10-30 chunks per plant procedure, that is roughly
700-2,000 documents for one customer plus `ayo`. `GET /admin/tenants` already reports
chunk counts per tenant.

Options then, from least to most effort:

1. **HNSW with iterative scans** (option 2), with a larger `hnsw.ef_search`. Measure its
   recall against exact search with the evaluation harness (`ayo-eval compare`) before
   switching.
2. **Smaller vectors**: `halfvec` (2 bytes per value instead of 4) halves storage and read
   cost with almost no loss in similarity accuracy, and the search stays exact. It needs
   a migration, but no reprocessing: `using embedding::halfvec(1024)` converts the stored
   vectors. Voyage can also return 512 dimensions, which does need every document
   re-embedded. Measure first: see "Prepared measurement" below.
3. **Per-tenant indexes or table partitioning**, so each search's index holds only the
   tenants it may return. That removes the filtering problem at its root, at more
   maintenance cost. Of the three, this is the only one that would make HNSW safe under
   tenant filters: storage changes (option 2) make exact search cheaper, not HNSW exact.
   Partitioning needs a `tenant` column on `chunks`; `doc_ids` filters and
   `include_outdated` would stay on exact search.

The order agreed on 2026-11-14: measure option 2 first (it keeps results exact and
reproducible), and plan partitioning with HNSW only when real tenants near the limit and
the evaluation harness can measure recall.

## Prepared measurement: halfvec and row storage

A brief, written 2026-11-14, for the first step when this ADR is revisited. Not started.
Like every step, it is re-briefed against the code of that day and approved before work.

**Why.** Exact search spends its time reading vectors, not computing distances. On the
Neon dev branch (49 chunks, read-only queries, 2026-11-14): `chunk_text` averages 542
bytes (max 879) and sits in the row uncompressed; every `embedding` (4,100 bytes) is in
TOAST, which is 392 kB against a 56 kB heap. So each searched chunk costs a TOAST lookup
plus 4 KB. A `halfvec(1024)` is 2,056 bytes: with `STORAGE main` it could stay in the row,
turning the search into a sequential heap read. A row of about 2.6 KB is over the 2 KB
TOAST threshold, though, so whether it stays in the row has to be measured, not assumed.
Compressing `chunk_text` in the application was considered and rejected: the text is not
what the search reads, and it would cost SQL readability, `char_length` in
`search_chunks` and a future full-text (hybrid) search. Postgres can compress it per
column if needed (lz4).

**What it delivers.** Timings and storage figures, added to this ADR as a new section, and
a recommendation: migrate to `halfvec` or not, and with which storage settings. No
migration, no app change, no change to `search_chunks`.

**Files.** One script, `scripts/bench_vector_storage.py` (or under `eval/`), committed so
the figures can be reproduced; this ADR.

**Where.** A throwaway database on the local dev DB (`scripts/dev_db.sh up`), created and
dropped by the script, like the 2026-11-10 runs. Never Neon: it writes test data. No
billed calls.

**Data.** The same layout as the evidence above (10 chunks per document, 20 tenants), at
1,000, 5,000 and 20,000 chunks. Realistic chunk text: Spanish text of 300-900 bytes per
chunk (from `tests/fixtures/`), because the text's size decides what stays in the row.
Random unit vectors are fine for timing. They are not fine for judging halfvec's
precision, so precision is checked separately (below).

**Variants.**

| | Column | Storage | `chunk_text` |
|---|---|---|---|
| A | `vector(1024)` | `external` (today) | default |
| B | `halfvec(1024)` | `external` | default |
| C | `halfvec(1024)` | `main` | default |
| D | `halfvec(1024)` | `main` | `compression lz4` |
| E | `vector(1024)` | `main` | default |

E separates the effect of size from the effect of TOAST.

**Measured, per variant and size.**
- The `search_chunks` query as it is (materialized CTE, top 5 and top 20), with the query
  cast to the column type: `EXPLAIN (ANALYZE, BUFFERS)`, median of at least 5 runs after a
  warm-up, plus one cold run (after a restart) for the worst case.
- Filtered (one tenant, about 20% of the chunks) and unfiltered.
- Storage: `pg_relation_size` of heap and TOAST, average `pg_column_size(embedding)`, and
  whether the vectors are in the row (TOAST size near zero).
- Precision: the top-20 from `halfvec` against the top-20 from `vector` for the same
  queries (overlap, and the largest distance difference). Run on real embeddings: the
  local DB's own documents if any were ingested with Voyage, otherwise the vectors already
  stored on the Neon dev branch, copied out with a read-only query. Embedding new queries
  with Voyage would be billed: give the call count and wait for the OK.

**Decision rule** (proposed, to confirm at the brief). Migrate to `halfvec` if the
fastest variant cuts the filtered 20,000-chunk search by at least 30% and the precision
check finds the same top-20 (or differences only between near-ties, under 1e-3).

**If it is adopted, a separate step** (not part of this one): a migration
(`alter column ... type halfvec(1024) using ...`, the chosen storage, the HNSW index
rebuilt with `halfvec_cosine_ops` or dropped), the query cast in `search_chunks`, the
startup dimension check (`embedding_dimensions` reads `atttypmod`, which `halfvec` also
uses; the type should be checked too), test helpers that insert vectors, and the Neon dev
branch migration with the user's OK.
