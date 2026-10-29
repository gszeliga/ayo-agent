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
   - Status derivation lives in **one SQL `CASE` expression** (it serves both the response
     field and the `status` filter), with the current descriptors as bound parameters.
     Precedence: either config null -> `unknown`, then `chunker_changed`, then
     `embedder_changed`. Tested through integration tests, not as a pure unit (the spec
     asks for unit tests).
   - `size_bytes` = UTF-8 length of the stored normalized Markdown. The migration
     backfills it with `octet_length(markdown)` (the spec leaves it null).
   - `total` comes from a separate `count(*)` in the same transaction (a window count
     returns nothing for an offset past the end).
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
- **C3** Read-side repository: `list_documents` (tenant, escaped `ILIKE` on
  title/source_key, status, whitelisted sort mapped to columns, `id` tiebreaker,
  limit/offset, total), `get_document`, `list_chunks` (embedding optional),
  `tenant_summaries`. Pure helpers `parse_sort`, `escape_like` with unit tests;
  integration tests for filters, sort ties, pagination edges and status.
- **C4** `GET /admin/documents` and `GET /admin/documents/{doc_id}`: `DocumentSummary`
  (8-character hash), `DocumentDetail`, generic `Page[T]` with clean OpenAPI names
  (`DocumentPage`); query bounds validated by FastAPI (422). **Parametrized 401 test
  over every `/admin` route.** OpenAPI, contract tests (200/401/404/422), export.
- **C5** `GET .../{doc_id}/content` (`text/markdown; charset=utf-8`, from the DB) and
  `GET .../{doc_id}/chunks` (`ChunkPage`; `include_embedding` documented as heavy).
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
- **C9** `GET /admin/tenants`: counts from `documents.chunk_count`.
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
the same commit; `CLAUDE.md` updated when layout or conventions change.

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
- [ ] C3. Read-side repository.
- [ ] C4. List and detail endpoints; 401 over every `/admin` route.
- [ ] C5. Content and chunks endpoints.
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
- Carried over from `progress.md`: the settings-env isolation fixture (proposed), the
  iterative HNSW scan before any search endpoint, Neon password rotation unconfirmed.
