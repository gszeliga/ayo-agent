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
- [ ] U1. Clickable prototype.
- [ ] U2. Scaffold `ui/`.
- [ ] U3. API client and connection.
- [ ] U4. Documents list.
- [ ] U5. Detail.
- [ ] U6. Upload/replace.
- [ ] U7. Rename, reprocess, delete.
- [ ] U8. Polish and manual run.

## Open items
- From the CRUD report, for the UI: replacing content answers `201` for an existing
  document; no `status` filter or bulk reprocess yet; delete leaves only a log line;
  `include_embedding` is heavy; the key in a browser is for internal/dev use only.
