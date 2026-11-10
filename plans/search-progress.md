# Search and retrieval evaluation milestone: plan and progress

`POST /admin/search` and an evaluation harness (golden set, `ayo-eval run|compare`,
metrics, reports) over a synthetic Spanish corpus. The spec was pasted into the session on
2026-11-10 (not committed); this file holds the agreed deviations, the plan and the
progress log. Resume from the first unchecked step.

## Decisions (agreed 2026-11-10)
1. **The embedder is Voyage, not BGE-M3 on Ollama** as the spec assumed. Queries go through
   a new `Embedder.embed_query`, which Voyage sends with `input_type: "query"` (Voyage adds
   its retrieval prompt server-side; there is no prefix to configure). The search's
   `debug.embedded_query` is the trimmed query. A switch to Ollama would be its own milestone.
2. **No `deleting_at`.** The spec skips documents being deleted, but deletes are
   single-transaction hard deletes with no such state. The rule and `skipped.deleting`
   are dropped; `skipped` holds only `embedder_mismatch`.
3. **One commit per step** (the repo's rule), not the spec's "small commits".
4. **Exact vector search**, not HNSW with iterative scans: correct top-k under any filter
   and reproducible runs, about 10 µs per searched chunk. Evidence and the threshold to
   revisit it are in `docs/decisions/0002-filtered-vector-search.md`.
5. `min_similarity` is applied after the top-k query: the rows are nearest first, so
   cutting the tail gives the same result and keeps the distance out of the SQL filter.
6. The eval CLI calls the HTTP endpoint (the spec's preference): it tests exactly what the
   UI will use. Its search function is injected, so the harness tests run on scripted
   rankings.

## Order of work (one commit per step, brief first, stop after each)
- [x] **S1** `embed_query` (Voyage, fake, health tracker); `repository.search_chunks`
  (exact, filters, outdated flag) and `count_embedder_mismatches`; `search.search` (own
  read-only transaction, timings, logs without query or chunk text); ADR 0002. Replaces
  `similar_chunks`.
- [ ] **S2** `POST /admin/search`: schemas and validation, 502 mapping, OpenAPI examples,
  contract tests, `docs/openapi.json`, `ui/src/api/schema.d.ts`, README.
- [ ] **S3** Eval core without I/O: golden-file loader (every problem reported at once),
  metrics (hit@k for documents and chunks, MRR, calibration, latency percentiles), `compare`
  classification. Adds `pyyaml`.
- [ ] **S4** `ayo-eval run` / `compare` CLI over HTTP, JSON reports (git-ignored except an
  example), `--fail-under`. Configs for the report from `GET /admin/settings`.
- [ ] **S5** Synthetic corpus (`eval/corpus/`), `eval/golden.example.yaml`, `eval/README.md`,
  `live` test; manual run (upload, Swagger searches, eval, chunker change, reprocess,
  compare) and the final report.

## Progress log
- **S1 (2026-11-10).** `Embedder.embed_query` on the protocol; Voyage shares the payload
  and retry code with `input_type="query"`; the fake returns the document vector of the
  same text and records `query_calls`; `TrackedEmbedder` tracks queries too, so a failed
  search shows in `/admin/health`. `repository.search_chunks` (materialized CTE, ties by
  chunk id, filters before distances, `embedder_outdated` flag) and
  `count_embedder_mismatches` replace `similar_chunks` (its three test users moved over).
  `search.search` embeds outside the transaction, then runs the search and the count in
  one repeatable-read read-only transaction; rounds similarity to 4 decimals; measures
  embed, search and total; logs tenants, `doc_ids` count, `top_k`, results, skipped and
  durations only. Input validation is left to the S2 schema.
  - Tests: unit (Voyage query payload, retries, error mapping without the text, malformed
    answer; fake; tracker). Integration in `tests/integration/test_search.py`: exact
    similarities (1, 0.6, 0, -1), rounding, tiebreak, `top_k` above the corpus, empty
    base, tenant isolation, all tenants, filters matching nothing, `doc_ids`,
    `min_similarity` boundaries, mismatched and null embedder configs skipped and counted
    (following the filters), `include_outdated` flagged, chunker-only change searched, the
    filtered-HNSW pitfall (planner pushed to the index; plain HNSW control returns fewer
    than 5), `embed_query` used, embedder failure before any read, timings, logs without
    query or chunks. `ScriptedEmbedder` and `axis_vector` in `tests/integration/support.py`.
  - Finding behind decision 4: `strict_order` iterative scans returned 0 rows in the
    pitfall test's layout (unreachable graph nodes), so the planned iterative-scan approach
    was replaced by exact search, with the user's OK.
- **ADR 0002 expanded (2026-11-10)**, at the user's request: how filters break HNSW and
  why iterative scans can still miss (unreachable nodes), where the exact-search cost
  comes from and what one search covers, the measurement caveats, and a "When to
  revisit" section (threshold in chunks and documents, three options in order of effort).
  Docs only.
