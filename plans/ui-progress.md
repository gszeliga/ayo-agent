# Admin UI milestone: plan and progress

The browser UI for the documents API (`plans/crud-progress.md`, done 2026-11-02). There is
no spec file: this file holds the decisions, the plan and the progress log; resume from
the first unchecked item under "Progress log".

## Decisions (agreed 2026-11-02)
1. **Clickable prototype first.** A throwaway Artifact page with mock data settles the
   look and the flows before any real code; it is iterated on until approved.
2. **The UI lives in `ui/` in this repo.** Its API types are generated from the committed
   `docs/openapi.json`, so one commit can change the API and the UI together.
3. **React + Vite + TypeScript.** Styling (Tailwind + shadcn/ui or what the prototype's
   design system suggests) is decided in the U2 brief, after the prototype.
4. **"Modern yet simple":** calm neutral layout, one accent colour, dense but readable
   tables, light and dark themes, no dashboard clutter. Usable down to tablet width.

## Order of work (one commit per step, brief first, stop after each)
- **U0** This file; `CLAUDE.md` points at it.
- **U1** Clickable prototype as a private Artifact (not committed code). Mock data shaped
  exactly like the API (`Document`, `ChunkPage`, `TenantSummary`, `{"detail": [...]}`
  errors), realistic Spanish procedures over 2-3 tenants, some `outdated`. Screens:
  - Documents list: tenant filter (with counts), search, sort, pagination, status badge
    (reason in a tooltip), chunks, size, relative `updated_at`; empty, no-match and
    loading states.
  - Document detail: inline rename, status, tenant, copyable `doc_id`; facts (times,
    size, chunks, shortened hashes, configs); tabs Content (rendered/raw) and Chunks
    (paged cards, "show vectors" marked as debug); actions Replace, Reprocess (force),
    Delete.
  - Upload/Replace dialog: drag and drop `.md`, tenant pick-or-type with the tenant
    pattern, optional title, `source_key` under "advanced", force. Replace fixes tenant +
    `source_key` and prefills the current title (a re-upload resets a rename otherwise).
    Toast for `indexed` (201) / `up_to_date` (200).
  - Delete confirmation: permanent, type the title to confirm.
  - Connection: API base URL + key in `sessionStorage`, "internal use only" banner, a
    401 reopens it.
  - Errors: 422 next to the field, 404 "no longer exists", 409 `document_changed`
    "retry", 502 "provider failed, nothing changed", 413 "too large"; triggerable from a
    "simulate error" menu.
  Review loop on the same Artifact until approved; the link and the outcome go in the log.
  Added during review (2026-11-02): multi-select and bulk delete on the list (one request
  to B2's endpoint; ids already gone are reported, not errors), and an "Indexing settings" page plus per-document "now differs" notes on the
  configs (needs B1).
- **B1** Backend: `GET /admin/settings` (agreed 2026-11-02), before the UI build. Read-only,
  no secrets (no keys, no URLs). Returns the current chunking values (`chunk_size`,
  `chunk_overlap`, `min_chunk_size`, version) and their `chunker_config` string; the
  embedding provider, model, dimensions, batch size and `embedder_config` string;
  `max_upload_bytes`; and document counts: total, indexed, outdated by reason
  (`unknown`, `chunker_changed`, `embedder_changed`, same precedence as
  `service.document_status`), counted in SQL against the current config strings.
  Shape, field names and tests settled in its brief. OpenAPI, contract, README.
- **B2** Backend: bulk delete (agreed 2026-11-02), before the UI build. Proposed:
  `POST /admin/documents/delete` with `{"doc_ids": [...]}` (1-100 distinct ids, each
  matching `DOC_ID_PATTERN`; a POST because a body on `DELETE` is poorly supported),
  operation `delete_documents`. One transaction, one statement (`delete ... where doc_id
  = any(%s) returning doc_id, tenant, chunk_count`); `200` with the deleted documents and
  the ids that were not found (already gone is not an error); one log line per deleted
  document, as the single DELETE. Lifts the spec's "no bulk operations" for deletes only.
  Shape and tests settled in its brief. The UI's bulk delete uses it: all or nothing, so
  no partial-failure handling beyond "not found".
- **B3** Backend: service status (agreed 2026-11-02), before the UI build. Proposed:
  `GET /admin/health` behind the key (it names the provider and its errors); the public
  `/health` stays liveness only, so a provider outage never fails it. Database: `select 1`
  through the pool with a ~2 s timeout, status and latency. Embeddings: active check
  (embed one short word, short timeout, result cached ~60 s, run on page load and on
  "Check now", never polled in a loop) plus passive tracking of the last real embedding
  call (last success, last error); the fake provider reports up. Shape and tests
  (mocked provider) settled in its brief. UI: two status dots in the header with a
  popover, and a "Services" card on the settings page.
- **U2** Scaffold `ui/`: Vite + React + TS, ESLint/Prettier, Vitest + Testing Library +
  MSW; `openapi-typescript` types from `docs/openapi.json` with a staleness check,
  `openapi-fetch`. README and `CLAUDE.md` commands.
- **U3** API client wrapper (base URL, key, the error type) and the connection screen.
- **U4** Documents list (TanStack Query, filters in the URL).
- **U5** Detail: facts, content, chunks.
- **U6** Upload/replace dialog.
- **U7** Rename, reprocess, delete.
- **U8** Polish (themes, empty/error states); manual end-to-end run against the local API
  with the fake embedder and `CORS_ALLOWED_ORIGINS=http://localhost:5173`.

## Progress log (update after every step; resume from the first unchecked item)
- [x] U0. Plan agreed with the user (2026-11-02) and written here.
- [x] U1. Clickable prototype, approved by the user (2026-11-02). Private Artifact
  (a Design canvas, one interactive artboard):
  https://claude.ai/artifact/We1nZk6KWUYCXvHJvGwoZt. Its source is the artboard file
  `project/Main.dc.html` in that Artifact (a new session reads it with the Artifact tool's
  `read` action and that `path`; the session scratchpad copy is gone). It is a reference
  for U2-U8, not code to port: mock data, a "Prototype" menu that simulates errors and
  outages, and click handlers instead of forms (the Artifact sandbox blocks form
  submission; the real UI uses normal forms).
  What the design settles:
  - Look: Inter + JetBrains Mono (ids, hashes, configs), neutral greys, one accent
    (`#2f6fed`), light and dark themes; status badges green `indexed`, amber `outdated`
    with the reason in words; English UI copy, Spanish document content.
  - Shell: header with the API host, service status (B3) and Disconnect; nav tabs
    Documents | Indexing settings; a dismissible "internal use only" key banner.
  - Connect screen: base URL + key (kept in `sessionStorage`); a 401 anywhere returns to it.
  - Documents: tenant sidebar with counts (`/admin/tenants`), search, 8 sort orders,
    pagination, loading/empty/no-match states, row checkboxes + page select-all, a
    selection bar and bulk delete (B2) confirmed by typing `delete N`; selection kept
    across pages, cleared when tenant or search change.
  - Detail: inline rename, copyable `doc_id`, Replace (tenant + `source_key` locked,
    current title prefilled), Reprocess split button (normal / force), Delete confirmed by
    typing the title; tabs Content (rendered/raw) and Chunks (paged cards, "show vectors"
    debug toggle); facts panel with shortened copyable hashes and the configs, with a
    "now differs: size 1000 -> 800" note when they differ from the current settings (B1).
  - Upload dialog: drag-and-drop or pick, tenant pick-or-type validated as typed,
    optional title, advanced `source_key` + force; a warning when embeddings are down.
  - Indexing settings page (B1): indexed/outdated counts by reason, Chunking, Embeddings,
    Services (B3) and Uploads cards, each setting with its env var; read-only.
  - Errors: 422 next to the field, 404 "no longer exists" page, 409 retry toast, 502
    "nothing changed" toast/alert, 413 on the file field.
- [x] B1. `GET /admin/settings` (2026-11-05). Operation `get_settings`, new OpenAPI tag
  `settings`. Body `IndexingSettings`: `chunking` (`chunker_version`, `chunk_size`,
  `chunk_overlap`, `min_chunk_size`, `chunker_config`), `embedding` (`provider`, `model`,
  `dimensions`, `batch_size`, `embedder_config`), `uploads.max_upload_bytes`, `documents`
  (`total`, `indexed`, `outdated.{unknown,chunker_changed,embedder_changed}`). The configs
  come from `service.current_configs`; counts are one `count(*) filter` statement
  (`repository.document_status_counts`) with `document_status`'s precedence, cross-checked
  against it in a test. `200`/`401` only. Not included (agreed): a tenant filter on the
  counts, the embedding timeout/retries. The UI keeps the env var names itself.
- [x] B2. Bulk delete (2026-11-05). `POST /admin/documents/delete`, operation
  `delete_documents`; kept a `POST` after discussing `DELETE` with a body (allowed by HTTP
  and OpenAPI 3.1, but proxies may drop it) and `DELETE` with query ids. Body
  `{"doc_ids": [...]}`: 1-100 ids matching `DOC_ID_PATTERN`, unknown fields rejected,
  repeats rejected with `422 duplicate_doc_ids` (agreed; schema says `uniqueItems`).
  `200 {"deleted": [{doc_id, tenant, chunk_count}], "not_found": [...]}`, both in request
  order. One statement locking the rows in `doc_id` order (`... where id in (select ...
  order by doc_id for update)`) so overlapping bulk deletes can't deadlock (agreed
  deviation from the plan's plain `any()` delete). One transaction; the single delete's
  log line per deleted document.
- [ ] B3. `GET /admin/health`.
- [ ] U2. Scaffold `ui/`.
- [ ] U3. API client and connection.
- [ ] U4. Documents list.
- [ ] U5. Detail.
- [ ] U6. Upload/replace.
- [ ] U7. Rename, reprocess, delete.
- [ ] U8. Polish and manual run.

## Next (resume here)
**B3** (`GET /admin/health`): write its brief and wait for approval. Then U2, each briefed
and committed separately. The backend steps follow the CRUD conventions in `CLAUDE.md` (OpenAPI with
examples, contract cases, `docs/openapi.json` export, README).

## Open items
- From the CRUD report, for the UI: replacing content answers `201` for an existing
  document; no `status` filter or bulk reprocess yet; delete leaves only a log line;
  `include_embedding` is heavy; the key in a browser is for internal/dev use only.
