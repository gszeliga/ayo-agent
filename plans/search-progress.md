# Search and retrieval evaluation milestone: plan and progress

`POST /admin/search` and an evaluation harness (golden set, `ayo-eval run|compare`,
metrics, reports) over a synthetic Spanish corpus. Spec: `plans/claude-code-prompt-search-eval.md`
(untracked, like the earlier specs; pasted into the session on 2026-11-10). This file holds
the agreed deviations, which win over the spec, the plan and the progress log.

## Next (resume here)
**Paused (2026-11-10).** S1 and S2 are done and pushed: `POST /admin/search` is live. The
evaluation harness (S3-S5) is parked until the user has agreed the golden-set (case)
format with ayo (decision 10). Resume only when the user says so, starting with a fresh
S3 brief that uses the agreed format. The spec's Part 2 and its "Unit" and "Harness" tests
are the requirements; decisions 1, 2 and 6 below already settle the embedder, `deleting`
and HTTP-vs-in-process questions.

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

7. **`debug` is always in the response**, `null` unless requested (the spec said "present
   only when requested"). Leaving it out would need `exclude_none`/`exclude_unset`, which
   would also drop the nullable `heading` and `document_title`; a nullable field keeps the
   OpenAPI and the generated UI types simple.
8. **Empty `tenants` / `doc_ids` lists are a 422 (`too_short`)**: `null` means no filter, and
   an empty list is almost always a client bug. Lists are capped at 50 and must not repeat a
   value (`duplicate_tenants`, `duplicate_doc_ids`); the 50-tenant cap is ours (the spec only
   capped `doc_ids`). Unknown tenants and ids are not errors: they add no results.
9. Debug timings are milliseconds rounded to 0.1 (the spec's example showed integers; most
   searches here take under 1 ms).
10. **The evaluation harness is parked (2026-11-10)**, at the user's request: the golden-set
   format is to be agreed with ayo first, and the metrics, report and `compare` (S3), the
   CLI (S4) and the corpus and example set (S5) wait for it. A draft S3 brief was discussed
   but not implemented; its proposed interpretations, to revisit when resuming: `tenants`
   required per case; `must_contain` needs every string, matched in `chunk_text` only (NFC +
   casefold, accents kept); chunk-level metrics only for cases with `must_contain`; negative
   cases not classified by `compare` (top-similarity delta shown instead).

## Order of work (one commit per step, brief first, stop after each)
- [x] **S1** `embed_query` (Voyage, fake, health tracker); `repository.search_chunks`
  (exact, filters, outdated flag) and `count_embedder_mismatches`; `search.search` (own
  read-only transaction, timings, logs without query or chunk text); ADR 0002. Replaces
  `similar_chunks`.
- [x] **S2** `POST /admin/search`: schemas and validation, 502 mapping, OpenAPI examples,
  contract tests, `docs/openapi.json`, `ui/src/api/schema.d.ts`, README.
Parked (decision 10): S3, S4 and S5.
- [ ] **S3** Eval core without I/O: golden-file loader (every problem reported at once),
  metrics (hit@k for documents and chunks, MRR, calibration, latency percentiles), `compare`
  classification. Adds `pyyaml`.
- [ ] **S4** `ayo-eval run` / `compare` CLI over HTTP, JSON reports (git-ignored except an
  example), `--fail-under`. Configs for the report from `GET /admin/settings`.
- [ ] **S5** Synthetic corpus (`eval/corpus/`), `eval/golden.example.yaml`, `eval/README.md`,
  `live` test; manual run (upload, Swagger searches, eval, chunker change, reprocess,
  compare) and the final report.

## Open items
- When ADR 0002 is revisited (about 20,000 chunks per search), start with the prepared
  halfvec measurement in `docs/decisions/0002-filtered-vector-search.md` (2026-11-14).
- The evaluation harness (S3-S5): parked until the case format is agreed with ayo
  (decision 10).
- `/admin/search` (like `/admin/settings` and `/admin/health`) is listed under both its own
  tag and `documents` in Swagger, because the router's default tag is merged with the
  route's. Fixing it means moving the default tag to the document routes; not done here.

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
- **S2 (2026-11-10).** `POST /admin/search` (`search_documents`, tag `search`):
  `SearchRequest` (trimmed `query` 1-2000, `tenants`/`doc_ids` null or 1-50 unique valid ids,
  `top_k` 1-50 default 5, `min_similarity` 0-1, `include_outdated`, `debug`; extra fields
  forbidden) and `SearchResponse` (`query`, `results` of `SearchHitResult`,
  `skipped.embedder_mismatch`, `debug` with `embedded_query`, `input_type`, configs and
  `timings_ms`). `EmbeddingError` -> `502 embedding_failed`, logged without the query.
  OpenAPI: description with status table, three request examples, 422 examples, field
  examples only for the response (nullable fields); `docs/openapi.json` and
  `ui/src/api/schema.d.ts` regenerated. README "Searching" section and endpoint row. The
  `/admin/health` field descriptions now say searches count as embedding calls too.
  - Tests: unit (`tests/unit/test_schemas.py`: defaults, trimming, inclusive bounds, 17
    invalid bodies with type and loc, response mapping with `debug` null and timings
    rounding); API (`tests/api/test_search.py`, real pgvector: a chunk found by its own
    text at similarity 1.0 with every field, tenant filter, outdated skipped and flagged,
    debug, `min_similarity` and `doc_ids`, empty base, unknown tenant or id, 502 with no
    detail and no query in logs, 422 through HTTP, logs without query or chunks);
    contract (200 x3, 401, 422 x2, 502); OpenAPI (operation, request bounds, nullable
    fields, request examples now validated against their schema too); auth picks the
    route up by itself. 716 backend tests; `pnpm check` green (287 UI tests).
  - Smoke run of the real app against the local dev database with the fake embedder:
    filters, `skipped` (2 documents without recorded configs), debug timings, 401, `/docs`.
- **Pause (2026-11-10).** S3 brief discussed; the user parked the golden file, then the
  whole harness (S3-S5), to agree the case format with ayo first. Recorded as decision 10.
  Docs only.
