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

## Decisions (agreed 2026-11-05)
5. **Deployment: one host first, separate hosts possible without code changes.**
   - Phase 1 (initial): one host, **Caddy** on :443 (automatic HTTPS) in front. It
     forwards `/admin/*`, `/health`, `/docs`, `/redoc` and `/openapi.json` to uvicorn on
     `127.0.0.1:8000`, and serves `ui/dist/` for everything else, unknown paths answering
     `index.html` (SPA fallback). Same origin, so no CORS. Caching: hashed assets
     forever, `index.html` never.
   - The API runs with **one uvicorn worker** under systemd (restart on failure, `.env`
     for secrets), with proxy headers trusted from `127.0.0.1` only. One worker because
     `/admin/health` keeps its probe cache and last-call tracking per process (B3);
     several workers would need that state in the database first.
   - Releases are independent: the API is pull + `uv sync` + `alembic upgrade head` +
     restart; the UI is `pnpm build` + copy `dist/`, no restart.
   - Phase 2 (when needed): the UI on its own static host, the API on its own. Only
     configuration changes: `CORS_ALLOWED_ORIGINS` set to the UI's origin, the UI pointed
     at the API's URL.
   - Consequences for the UI code: the API base URL defaults to the UI's own origin,
     overridable at build time with `VITE_API_BASE_URL` and on the connect screen; UI
     routes never start with an API path (`/admin`, `/health`, `/docs`, `/redoc`,
     `/openapi.json`), enforced by a test (both in U3). No `/api` prefix for now.
   - To settle in the deployment step: `/docs` on a public host (`DOCS_ENABLED=false`, or
     limited to the internal network by the proxy), and network-level access control,
     since the shared key in a browser is for internal use only.

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
  Routing with UI routes clear of the API's paths (a test checks it); the base URL
  defaults to the page's origin, or `VITE_API_BASE_URL` when set at build time (decision 5).
- **U4** Documents list (TanStack Query, filters in the URL).
- **U5** Detail: facts, content, chunks.
- **U6** Upload/replace dialog.
- **U7** Rename, reprocess, delete, and the list's multi-select bulk delete (B2).
  (Bulk delete assigned here on 2026-11-05: no step owned it.)
- **U8** Indexing settings page (B1: counts by reason, Chunking, Embeddings, Uploads cards,
  per-document "now differs" notes) and service status (B3: header dots with a popover,
  "Services" card with "Check now"). Added 2026-11-05: the review asked for them, but no
  step owned them.
- **U9** Polish (themes, empty/error states); manual end-to-end run against the local API
  with the fake embedder and `CORS_ALLOWED_ORIGINS=http://localhost:5173`.
- **D1** Deployment, phase 1 (decision 5): a `Caddyfile` (routing, SPA fallback, caching
  headers), a systemd unit for the API (one worker, proxy headers; `main()` made
  configurable or uvicorn called directly, settled in the brief), a release checklist,
  and a "Deployment" section in the README. Settles `/docs` exposure and access control.
  Tried end to end on a local machine or VM; no real server is touched without the
  user's OK.

## Progress log (update after every step; resume from the first unchecked item)
- [x] U0. Plan agreed with the user (2026-11-02) and written here.
- [x] U1. Clickable prototype, approved by the user (2026-11-02). Private Artifact
  (a Design canvas, one interactive artboard):
  https://claude.ai/artifact/We1nZk6KWUYCXvHJvGwoZt. Its source is the artboard file
  `project/Main.dc.html` in that Artifact (a new session reads it with the Artifact tool's
  `read` action and that `path`; the session scratchpad copy is gone). It is a reference
  for U2-U9, not code to port: mock data, a "Prototype" menu that simulates errors and
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
- [x] B3. `GET /admin/health` (2026-11-05). Operation `get_service_health`, tag `health`,
  always `200` (`status: ok|degraded`), plus `401` and `422` (`refresh`). `database`:
  `select 1` with `pool.connection(timeout=2)`, error `timeout` / `connection failed` (never
  psycopg's text). `embeddings`: `VoyageEmbedder.probe` (one word, 5 s, no retries;
  `FakeEmbedder.probe` always up; not on the `Embedder` protocol), cached 60 s in
  `health.EmbeddingMonitor` (failures too; a lock makes concurrent callers share one
  check; `refresh=true` bypasses), plus `last_success_at` / `last_error_at` / `last_error`
  of real calls from `health.TrackedEmbedder`, which the lifespan wraps around the
  embedder (in memory). Nullable fields: examples per field only. Agreed: no minimum gap
  between refreshes.
- [x] U2. Scaffold `ui/` (2026-11-05). pnpm 11 (pinned via `packageManager`), Node 24+;
  Vite 8 + React 19 + TypeScript 5.9 strict (TS 7 is out, but typescript-eslint supports
  `<6.1` and openapi-typescript wants 5.x); ESLint 10 flat config, `strictTypeChecked`;
  Prettier; Vitest 5 + jsdom + Testing Library + MSW 3 (`onUnhandledFrame: 'error'`, the
  v3 name). Styling decided: **Tailwind v4 + shadcn/ui** (MIT; components copied in as
  needed, none yet; `components.json`, `cn()`), fonts self-hosted via Fontsource. Prototype
  tokens copied into `src/index.css` under shadcn's names (+ `success`, `warning`,
  `danger-muted`, `link`); `dark` class set from the system preference in `index.html`
  (toggle in U9). `openapi-typescript` -> committed `src/api/schema.d.ts`,
  `pnpm gen:api:check` in `pnpm check`; `openapi-fetch` installed for U3. Agreed: `ui/`
  has its own README (root README points to it). No routing or data fetching yet (U3/U4).
- [x] U3. API client and connection (2026-11-05). React Router 8, plain component setup
  (`<Routes>`, no data loaders); paths in `src/paths.ts` (`/connect`, `/documents`,
  `/documents/:docId`, `/settings`), guarded by `RequireConnection` (redirects to
  `/connect?next=`; `safeNext` accepts in-app paths only). Connection `{baseUrl, apiKey}`
  in `sessionStorage` (try/catch, memory if blocked) behind `ConnectionProvider` /
  `useConnection` / `useApiClient`. Base URL default: `VITE_API_BASE_URL`, else the page
  origin; `.env.development` points `pnpm dev` at `http://127.0.0.1:8000`; validated as
  `http(s)://host[:port]`. `createApiClient` (openapi-fetch + middleware: `X-API-Key`,
  `onUnauthorized` on 401 -> disconnect with a notice), `unwrap`, `ApiError` (status null
  = unreachable; generic item for non-API bodies; `fieldErrors()`). Connect screen checks
  with `GET /admin/tenants`: 401 under the key field, unreachable names the URL and
  `CORS_ALLOWED_ORIGINS`. Shell: header (mark, host, nav, Disconnect) and a dismissible
  banner (`localStorage`). shadcn/ui: button, input, label, card, alert (+ `radix-ui`,
  `lucide-react`). Route-clash test reads the API's paths from `docs/openapi.json`. Plan
  fix agreed: bulk delete -> U7, settings page + service status -> new U8, polish -> U9.
  Found on the way: `shadcn add` needs the `@/` alias in the root `tsconfig.json` (it
  wrote into a literal `@/` folder and pulled in the `cn` package otherwise; both undone).
  Checked against the real local API (fake embedder): CORS preflight from
  `localhost:5173` allows `X-API-Key`, and a `401` carries the CORS header, so the UI can
  read it.
  Follow-up (2026-11-05, agreed after a manual test hit it): the connect screen tells a
  CORS refusal from an unreachable API with one `no-cors` request to `/health` after a
  network failure (`connection/reachability.ts`): "answers, but refuses requests from this
  page; add <origin> to CORS_ALLOWED_ORIGINS" vs "can't reach".
- [x] U4. Documents list (2026-11-05). TanStack Query 5 (`api/queryClient.ts`: stale 30 s,
  refetch on focus, retry network failures once, none for statuses; cache cleared on
  connect/disconnect). URL is the state (`documents/listParams.ts`): defaults omitted,
  invalid values fall back and the URL is corrected in place, limits checked against
  `docs/openapi.json`; tenant/sort/page push history, search replaces after 300 ms; filter
  or sort changes reset to page 1; past-the-end pages move to the last. Tenant sidebar
  (links, `aria-current`, a selected empty tenant listed with 0) and a select below `lg`.
  Native sort select with the prototype's eight options, Clear filters. Table: title link +
  mono `source_key`, tenant chip, status badge (outdated reason in a tooltip and sr-only
  text), chunks, size (`—` when not recorded), relative updated time (exact UTC in
  `title`, "now" = fetch time so renders stay pure). States: skeleton, dimmed rows while
  paging, no documents, no match + Clear filters, error + Retry. shadcn/ui: table, badge
  (+ success/warning variants), tooltip, skeleton. Small deviations: relative times
  hand-formatted ("3 h ago", as in the prototype) rather than `Intl.RelativeTimeFormat`;
  the exact time is a native `title` tooltip. Found: shadcn's registry imports `cn` from its
  `cn` package regardless of config (U3's note blamed the alias); imports rewritten again,
  README says how. Lint: `!` allowed in tests only.
- [x] U5. Detail (2026-11-05). `/documents/:docId`: back link to the list as left (location
  state from the list), title (falls back to `source_key`) + status + tenant + copyable
  `doc_id`, browser tab title; facts panel (prototype's order; hashes shortened to 12 with
  copy; nulls "not recorded"); Radix tabs Content / Chunks in the URL (`tab`, `view`,
  `cpage`), each fetched only when opened. Content: `react-markdown` + `remark-gfm` +
  `@tailwindcss/typography` (prose mapped to our tokens), no raw HTML, `javascript:` links
  dropped, links in a new tab with `noopener noreferrer`, images not loaded (alt shown);
  Raw with Copy Markdown; the renderer lazy-loaded (main bundle 140 KB gz, Markdown chunk
  49 KB). Chunks: cards (#, heading, chars, text), 20 per page, "Show vectors" (debug ·
  heavy, local state) with a 12-value preview and copy of the full vector. Header from the
  list's cache when present. Malformed id (pattern checked against `docs/openapi.json`) and
  a 404 from any of the three calls -> "This document no longer exists"; other errors stay
  in their tab with Retry. `CopyButton` says "Copy unavailable" without the clipboard API.
  Shared `describeError()` now in `api/errors.ts` (list and detail). Found while testing: an
  MSW `HttpResponse` reused across tests has its body consumed; tests build one per call.
  Follow-up (2026-11-05, raised by the user): inline code looked unrendered, because the
  typography plugin draws literal backticks around it, bold, with no background. `.markdown`
  now drops the backticks and styles inline code as a mono chip (`secondary` background);
  fenced blocks unchanged. The test procedure gained inline code and a fenced block.
  Follow-up (2026-11-05, agreed): chunks get a Raw / Rendered toggle, **raw by default**
  (what was embedded; split tables and lists stay visible), `cview=rendered` in the URL
  (separate from the content's `view`). Each chunk renders on its own through the same
  lazy safe renderer (`LazyMarkdown`), so a cut code block stays in its card. `ViewToggle`
  shared by both tabs.
- [x] U6. Upload/replace (2026-11-05). One dialog, two modes: Upload (list header and empty
  state; tenant prefilled from the filter, pick-or-type with a `<datalist>` of tenants,
  checked as typed) and Replace (detail header; tenant + `source_key` locked, title
  prefilled). Drop zone or picker; client checks `.md` / empty / `max_upload_bytes` from
  `/admin/settings` (new `useIndexingSettings`, reused in U8), skipped if unavailable.
  Advanced: `source_key`, Force reindex. Multipart through openapi-fetch's
  `bodySerializer`. Agreed addition: **overwrite warning** in Upload mode (debounced list
  query, exact `source_key` match). Toasts (shadcn `sonner`, `next-themes` dropped):
  "Indexed/Replaced ‹title›: N chunks" or "Already up to date". Errors stay in the dialog:
  `422` per field (Advanced opens for a `source_key` error), `413` on the file, `502`
  "nothing was stored". Busy: Esc/outside click blocked; Cancel aborts with a note.
  Invalidates documents, tenants, settings and the document. Dialog lazy-loaded (main
  bundle 151 KB gz). Deferred to U8 as agreed: the "embeddings down" warning. Found:
  Vitest's jsdom environment cannot fetch a multipart body with a file (cross-realm typed
  arrays -> `RequestContentLengthMismatchError`; plain Node + MSW is fine); upload tests run
  under happy-dom (dev dependency) with the page on the mocked API's origin. jsdom also
  lacks `matchMedia` (stubbed in the test setup for the toaster).
- [ ] U7. Rename, reprocess, delete.
- [ ] U8. Indexing settings page and service status.
- [ ] U9. Polish and manual run.
- [ ] D1. Deployment, phase 1.

## Next (resume here)
**U7** (rename, reprocess, delete, bulk delete): write its brief and wait for approval.

## Open items
- From the CRUD report, for the UI: replacing content answers `201` for an existing
  document; no `status` filter or bulk reprocess yet; delete leaves only a log line;
  `include_embedding` is heavy; the key in a browser is for internal/dev use only.
- Health state per process: with several uvicorn workers, `/admin/health`'s probe
  cache and last-call tracking would differ by worker. Fine with one worker (decision 5);
  move it to the database before scaling out.
