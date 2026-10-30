# Documents CRUD milestone: plan and progress

Spec: `plans/claude-code-prompt-documents-crud.md` (intentionally untracked, like the
ingestion spec). This file holds the agreed deviations, the plan and the progress log;
resume from the first unchecked item under "Progress log". The ingestion slice's record
is `plans/progress.md`.

## Decisions (these override the spec; agreed 2026-10-28)
1. **No disk-related parts.** The Markdown has lived in `documents.markdown` since step
   6a.1, so these are dropped: `KNOWLEDGE_DIR`, path-safety checks, `content_available`,
   the 409s for a missing file (`/content`, reprocess), `deleting_at`, the `deleting`
   status and the retry-delete flow. **Delete is one transaction**: write the audit row,
   delete the document, chunks go by cascade. `status` is `indexed | outdated`. The
   spec's tests for these parts are dropped too.
2. **No PUT.** Replacing content is `POST /admin/documents` with the document's `tenant`
   + `source_key` (both are in every summary); POST's description says so. The title
   rule is unchanged (given, else first H1, else file name), so the UI sends the current
   `title` if it wants to keep a rename. No `replace_document` operation.
3. **Tracking** in this file.
4. **Smaller choices, confirmed in each step's brief:**
   - Status derivation: superseded by Decision 7.
   - `size_bytes` = UTF-8 length of the stored normalized Markdown. The migration
     backfills it with `octet_length(markdown)` (the spec leaves it null).
   - `total` comes from a separate `count(*)` (a window count returns nothing for an
     offset past the end). Under read committed two statements can see different data,
     so C4 runs page and count in one `repeatable read, read only` transaction.
   - New error types: `document_not_found` (404, `["path","doc_id"]`) and
     `document_changed` (409, reprocess optimistic check), added to the error table of
     the API description.
   - `GET /admin/tenants` returns a plain array, as in the spec (not paginated).
5. **No deletion audit table** (agreed 2026-10-29). No `document_deletions`, no
   `GET /admin/deletions`, no `reason` parameter and no `X-Actor` header. `DELETE` is one
   plain statement (chunks go by cascade) and logs `doc_id`, tenant and the deleted chunk
   count (no content); that log line is the only trace. Overrides the DELETE details of
   Decision 1 and the spec.

6. **Reprocess (C7) skips up-to-date documents and guards on the content** (agreed
   2026-10-29). The spec's "always reprocess" served only failure recovery, which doesn't
   exist (a failed upload writes nothing). The final write is conditional on
   `content_hash`, not `updated_at`: a rename meanwhile is no conflict, a newer upload
   is (its chunks must not be overwritten with the old content's), and a delete meanwhile
   matches no row. Two named store functions instead of one with a mode parameter.

7. **Status in Python, no `status` filter** (agreed 2026-10-29). The repository returns
   the stored configs; `service.document_status(chunker_config, embedder_config,
   settings)` derives `status`/`outdated_reason` (either null -> `unknown`, then
   `chunker_changed`, then `embedder_changed`), unit-tested. A filter applied after SQL
   pagination would give short pages and a wrong `total`, so the list has no `status`
   filter for now; if needed later, add it as a plain equality filter on the two configs.

8. **`doc_id` path parameters are validated** (agreed 2026-10-29) with
   `signatures.DOC_ID_PATTERN` (`^[a-z]+-[0-9a-f]{12}$`): malformed -> 422
   `string_pattern_mismatch` at `["path","doc_id"]`, well-formed but unknown -> 404
   `document_not_found`. Otherwise FastAPI documents a default 422 with its
   `HTTPValidationError` schema that could never happen. Applies to every `{doc_id}`
   route (C5-C8).

9. **One `Document` schema for the list and the detail** (agreed 2026-10-30). The spec's
   summary/detail split existed mostly for on-disk fields that Decision 1 dropped; what
   was left gave two shapes, and `content_hash` meant 8 characters in one and 64 in the
   other. Now both endpoints return the same object with the full hash, signatures and
   configs (about 350 more bytes per listed item). The UI shortens hashes for display.

## Order of work (one commit per step, brief first, stop after each)
- **C0** This file; `CLAUDE.md` and `progress.md` point at it.
- **C1** Migration `0002`: `documents` gets `chunk_count int not null default 0`,
  `size_bytes int` (nullable until C2 writes it), `chunker_config text`,
  `embedder_config text`; index `documents_tenant_updated_at_id_idx`
  `(tenant, updated_at desc, id)`. Backfill `chunk_count` and `size_bytes`; configs stay
  null (`outdated`/`unknown`). Reversible. Tests: upgrade on a database with documents,
  downgrade, upgrade again.
- **C2** Ingestion writes the new columns: `DocumentRecord` gets `chunk_count`,
  `chunker_config`, `embedder_config`; `size_bytes` is `octet_length(markdown)` in the
  upsert (same as the backfill). Shared stages for reprocess (C7): `compute_signatures`
  and `index_markdown` (chunk + embed, no DB); `store_document` (renamed from
  `replace_document_chunks`) stays upload-only; C7 adds its own store function.
- **C3** Read-side repository: `DocumentRow`, `list_documents` (tenant, escaped `ILIKE`
  on title/source_key, whitelisted sort mapped to columns, `id` tiebreaker,
  limit/offset, total), `get_document`. Pure helpers `parse_sort`, `escape_like`;
  `service.current_configs` and `document_status` (Decision 7). `list_chunks` moved to
  C5 and `tenant_summaries` to C9, each with its endpoint.
- **C4** `GET /admin/documents` and `GET /admin/documents/{doc_id}`: one `Document`
  schema for both (Decision 9; was `DocumentSummary`/`DocumentDetail`), generic `Page[T]` with clean OpenAPI names
  (`DocumentPage`); query bounds validated by FastAPI (422); unknown `sort` -> 422;
  `status`/`outdated_reason` from `document_status`; page + count in one
  repeatable-read transaction. **Parametrized 401 test
  over every `/admin` route.** OpenAPI, contract tests (200/401/404/422), export.
- **C5** `GET .../{doc_id}/content` (`text/markdown; charset=utf-8`, from the DB) and
  `GET .../{doc_id}/chunks` (`ChunkPage`; `include_embedding` documented as heavy);
  repository `list_chunks` (embedding optional).
- **C6** `PATCH /admin/documents/{doc_id}` (`{"title"}`, trimmed, 1-200 characters,
  `extra="forbid"`): only `title` and `updated_at` change; tests check the embedder is
  never called and the signatures stay the same.
- **C7** `POST .../{doc_id}/reprocess` (Decision 6): stored Markdown; if the stored
  `embed_signature` equals today's, `up_to_date` without calling the provider; else
  `compute_signatures` + `index_markdown` outside any transaction, then
  `store_reprocessed_document(pool, document, chunks, vectors) -> bool`, which runs
  `repository.update_indexed_document` (`UPDATE ... WHERE doc_id=%s AND content_hash=%s`,
  never inserts; writes only chunk/embedding columns, not `title` or `markdown`). No row
  -> nothing written, 409 `document_changed` (404 vs 409 for a delete in the meantime:
  decide in C7). 200/404/409/502; a provider failure leaves the DB as it was.
- **C8** `DELETE /admin/documents/{doc_id}` (204/404), one statement (`delete ...
  returning tenant, chunk_count`), one log line (Decision 5). Tests: cascade, 404,
  re-upload afterwards creates a new row.
- **C9** `GET /admin/tenants`: repository `tenant_summaries` (group by tenant, sum of
  `documents.chunk_count`, ordered by tenant).
- **C10** CORS: `CORS_ALLOWED_ORIGINS` (comma-separated, empty = off), `CORSMiddleware`
  in `create_app`; methods `GET, POST, PATCH, DELETE`; headers `X-API-Key`,
  `Content-Type`; no credentials. `.env.example`, README, tests (allowed preflight,
  disallowed origin gets no CORS headers).
- **C11** README (endpoints, `CORS_ALLOWED_ORIGINS`, curl for list, replace
  via POST, reprocess, delete), `CLAUDE.md` layout, manual run on the local DB, final
  report (an API key in a browser is for internal or dev use only).

Every endpoint step: `ApiError` for errors; `operation_id` from the spec's list; every
status in `responses` with examples and every field described; each documented status
triggered for real in `tests/api/test_contract.py`; `docs/openapi.json` re-exported in
the same commit; `README.md` updated for every new or changed endpoint (user's rule,
2026-10-30); `CLAUDE.md` updated when layout or conventions change.

Code to reuse: `ingestion/service.py` stages (`decode_markdown`, `chunk_document`,
`embed_chunks`, `replace_document_chunks`, signature computation);
`signatures.chunker_descriptor` / `embedder_descriptor` are exactly the stored config
strings; `routers/admin.py` `_error`, `_examples`, `require_admin_key`; `errors.ApiError`;
`tests/conftest.py` `db_pool`, `scratch_database_url`.

## Verification (each step, and at the end)
- `uv run pytest`; `uv run ruff check . && uv run ruff format --check .`.
- `uv run python scripts/export_openapi.py --check`.
- `uv run alembic upgrade head` / `downgrade -1` on the local dev DB. The Neon dev branch
  only with the user's OK, after checking what is there.
- End (C11), local DB + fake embedder, curl and Swagger: upload, list, chunks, rename,
  re-upload via POST, change `CHUNK_SIZE` -> `outdated` (`chunker_changed`), reprocess
  -> `indexed`, delete (log line, chunks gone), tenant counts.

## Progress log (update after every step; resume from the first unchecked item)
- [x] C0. Plan agreed with the user (2026-10-28) and written here.
- [x] C1. Migration `0002` (2026-10-29). Deletion table dropped from the plan
  (Decision 5). Three migration tests: backfill on 0001 data (UTF-8 bytes, not
  characters), columns + index + defaults at head, downgrade keeps documents and
  upgrades again. Upgrade/downgrade/upgrade checked on the local dev DB (backfill
  matched the real chunk counts); Neon not touched.
- [x] C2. Ingestion writes the new columns (2026-10-29). `compute_signatures`,
  `index_markdown`, `_chunk_records`, `store_document`. `DocumentRecord`'s new fields
  are required (configs nullable, no default), so a caller can't forget them. Tests:
  unit (`compute_signatures` vs the signature functions), repository upsert writes the
  columns on insert and update, service stores counts/bytes/configs and updates them on
  re-index and on a config change. `compute_signatures` reproduces the embed signatures
  stored on the local dev DB, so the refactor re-indexes nothing.
- [x] C3. Read-side repository (2026-10-29). Status moved to Python and the `status`
  filter dropped (Decision 7); `list_chunks` -> C5, `tenant_summaries` -> C9. ORDER BY
  built with `psycopg.sql` (`Identifier` from the whitelist), no `nulls` clause so the
  default sort can use `documents_tenant_updated_at_id_idx`. Tests: unit (`parse_sort`,
  `escape_like`, `document_status` incl. precedence, `current_configs` vs
  `compute_signatures`), integration `test_document_queries.py` (default order, tenant,
  `q` case-insensitive on both columns, literal `%`/`_`/`\`, combined filters + total,
  every sort key both ways, tie paging with `limit=1`, offset past the end, get).
- [x] C4. List and detail endpoints; 401 over every `/admin` route (2026-10-29).
  `documents.py` (service: page + count in one repeatable-read read-only transaction),
  `DocumentSummary`/`DocumentDetail` (`from_row` computes the status, converts
  timestamps to UTC), generic `Page[T]` with `DocumentPage`; `sort` is a `Literal`
  (`literal_error` 422); `doc_id` pattern (Decision 8). Nullable fields are sent as
  null. Found along the way: FastAPI 0.148 wraps included routers in a private
  `_IncludedRouter`, so the auth test enumerates `/admin` operations from the OpenAPI
  document; Starlette's `Allow` header on a 405 lists only the first matching route's
  methods (says `POST` for `/admin/documents` although `GET` exists), left as is.
  Contract tests now keyed by operation, plus a check that every `/admin` operation has
  cases. Manual curl on the local dev DB: list, detail, 404, 422, 401 as expected;
  the two pre-0002 documents show `outdated`/`unknown`.
- [x] C4a. One `Document` schema for list and detail (2026-10-30, Decision 9).
  `DocumentSummary`/`DocumentDetail` and `SHORT_HASH_LENGTH` gone; `docs/openapi.json`
  re-exported. The read API test now asserts the detail equals the listed item.
- [x] C5a. `GET .../{doc_id}/content` (2026-10-30). C5 split in two commits (content,
  chunks). `repository.get_markdown` (the only read of `markdown`), `documents.read_markdown`.
  Route uses `response_class=Response` with an explicit `text/markdown; charset=utf-8`
  200, so no JSON 200 is documented and errors stay `application/json`. No
  `Content-Disposition`, no `ETag` (could be `content_hash` later). The contract test now
  takes the documented media type from the response's `Content-Type`, so a body in an
  undocumented media type fails. Tests: exact text and header, BOM/CRLF/CR come back
  normalized and hash to `content_hash`, JSON 404, 422; repository `get_markdown`.
- [x] C5b. `GET .../{doc_id}/chunks` (2026-10-30). `ChunkPage` of `Chunk`
  (`chunk_index`, `heading`, `chunk_text`, `char_count` = `char_length`, `embedding`).
  `embedding` is always present, null unless `include_embedding` (one shape, as Decision
  9); the column is only selected when asked for. `total` is `documents.chunk_count`
  (`repository.get_chunk_count`, which also gives the 404), read with the page in one
  repeatable-read transaction; no `count(*)`. Order by `chunk_index` alone (unique per
  document). `chunk_text` is documented as not exactly the embedded text (heading path +
  blank line + text). `limit` 1-200, default 50, kept with vectors and documented as heavy.
  Tests: repository (order with out-of-order inserts, paging, past the end, characters
  not bytes, vectors only when asked and equal to float4 precision, other documents
  excluded, `get_chunk_count`), API (default page, paging, the vector equals the fake
  embedder's for heading + text, 404, 422s), OpenAPI parameters, contract cases.
  README gained "Reading documents" (list, detail, content, chunks), catching up on C4
  and C5a; keeping it current is now a rule in `CLAUDE.md`.
- [ ] C6. PATCH rename.
- [ ] C7. Reprocess.
- [ ] C8. Delete.
- [ ] C9. Tenants.
- [ ] C10. CORS.
- [ ] C11. README, manual run, final report.

## Open items
- No deletion audit trail (Decision 5). Revisit with real authentication; deletions made
  before then leave only log lines.
- POST re-upload resets a PATCH rename unless the client sends `title`; the UI must know.
- A POST still in flight while a DELETE commits re-creates the document. Acceptable
  (same as "upload after delete"); document it.
- **Null values vanish from OpenAPI examples** (found in C5b). FastAPI renders the
  document with `exclude_none=True`, so `"outdated_reason": null` (Document) and
  `"embedding": null` (Chunk) are missing from the examples, which then fail their own
  schemas (required fields). Fix in its own step, with a test that every example validates
  against its schema.
- Carried over from `progress.md`: the settings-env isolation fixture (proposed), the
  iterative HNSW scan before any search endpoint, Neon password rotation unconfirmed.
