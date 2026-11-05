# AYO admin UI

Browser UI for the documents API (`/admin`): list, inspect, upload, replace, reprocess and
delete knowledge documents, and see the indexing settings and service status. React +
Vite + TypeScript, Tailwind CSS v4 and shadcn/ui components. **Internal use only:** it
sends the shared admin key from the browser.

Being built step by step: plan and progress in `../plans/ui-progress.md`. The approved
clickable prototype it follows is linked there (U1).

## Setup

Needs Node 24+ and pnpm (the version is pinned in `package.json`, `packageManager`).

```sh
cd ui
pnpm install
pnpm dev            # http://localhost:5173 (fixed port: the API's CORS allows this origin)
```

The API must allow the origin: start it with `CORS_ALLOWED_ORIGINS=http://localhost:5173`.
For example, with the local database and the fake embedder, from the repo root:

```sh
EMBEDDING_PROVIDER=fake CORS_ALLOWED_ORIGINS=http://localhost:5173 \
  DATABASE_URL=postgresql://ayo:ayo@localhost:5433/ayo ALLOW_REMOTE_DATABASE=false \
  uv run ayo-copilot
```

## Connecting

The UI opens on a connect screen: the API address and the admin key, checked with
`GET /admin/tenants` before they are kept. They live in `sessionStorage`, so only in this
tab and only until it closes. Any `401` later (a changed key) returns to the connect screen
with a notice; Disconnect forgets them.

A browser reports a CORS refusal exactly like a network failure. When the check fails that
way, the screen sends one `no-cors` request to the public `/health` (exempt from CORS): if
it succeeds, the API is up and refuses this page's origin, and the message says to add it
to `CORS_ALLOWED_ORIGINS`; otherwise the API is unreachable (`src/connection/reachability.ts`).

The address defaults to `VITE_API_BASE_URL` when it is set at build time, else to the
page's own origin, which is right when a proxy serves the UI and the API together
(production, see `../plans/ui-progress.md` decision 5). `.env.development` sets it to
`http://127.0.0.1:8000` for `pnpm dev`. For a build against an API on another host:
`VITE_API_BASE_URL=https://api.example.com pnpm build`.

## Documents list

`/documents?tenant=…&q=…&sort=…&page=…`: the URL holds the whole view, so it can be
reloaded, shared and stepped through with Back. Defaults are left out (`sort=-updated_at`,
`page=1`) and invalid values fall back to them, the URL corrected in place, so a
hand-edited URL never reaches the API as a `422` (`src/documents/listParams.ts`; its test
checks the limits against `docs/openapi.json`). Tenant, sort and page changes add history
entries; the search updates the URL 300 ms after typing pauses, without one. Changing a
filter or the sort goes back to page 1; a page past the end moves to the last one. Page
size is fixed at 25.

Data comes through TanStack Query (`src/documents/queries.ts`, client in
`src/api/queryClient.ts`): fresh for 30 s, refetched when the window regains focus, only
network failures retried (once), and the cache cleared whenever the connection changes.
While a page or filter loads, the current rows stay, dimmed.

## Document detail

`/documents/:docId?tab=chunks&cpage=2&cview=rendered` or `?view=raw`: header (title, status, tenant,
copyable `doc_id`), a facts panel, and the Content and Chunks tabs, each fetched when first
opened. The header shows at once from the list's cache when the document is there.
"← Documents" returns to the list as it was left (the list passes its URL in the location
state). A malformed id, or a `404` from any of the document's three calls, shows "This
document no longer exists". "Show vectors" (debug, heavy) is local state, never in the URL.

Chunks show **raw by default**: exactly the text that was embedded, so a table or list the
splitter cut is visible as such. "Rendered" (`cview=rendered`) renders each chunk on its
own with the same safe renderer, so a code block cut mid-way stays inside its card.

**Rendering documents safely** (`src/document/Markdown.tsx`; documents are customer
content): raw HTML is never rendered (no `rehype-raw`), `javascript:` links are dropped,
links open in a new tab with `rel="noopener noreferrer"`, and **images are not loaded**
(their alt text shows): a remote image would tell its host who reads the document. Keep
these rules when touching it; `Markdown.test.tsx` checks each. The renderer is loaded on
demand (`React.lazy`), so the Markdown libraries stay out of the main bundle.

## Upload and replace

One dialog (`src/upload/`), loaded on first open: **Upload** on the list (tenant prefilled
from the list's filter) and **Replace** on a document (tenant and `source_key` locked, the
current title prefilled so a rename survives). It sends `POST /admin/documents` as
multipart. Before sending it refuses a file that is not `.md`, is empty, or exceeds
`max_upload_bytes` from `/admin/settings` (skipped when that call fails; the API's `413`
still applies), and checks the tenant as typed. In Upload mode it **warns when the tenant
and `source_key` match a stored document** (one debounced list query, exact `source_key`
only), because the API replaces it silently. `201` and `200 up_to_date` end in a toast and
a refresh of the list, tenants and document; Upload then opens the new document. Errors
keep the dialog and its input: `422` next to its field, `413` on the file, `502` as "nothing
was stored". While sending, Esc and clicks outside do nothing; Cancel aborts and says the
API may still finish indexing.

## Rename, reprocess, delete

On a document (`src/document/`): **rename** in place (pencil or double-click; Enter saves,
Esc cancels; trimmed, 1–200 characters; not optimistic), **Reprocess** as a split button
(normal, or Force from its menu; a `409` says a newer upload won, with Retry in the toast;
`502` says nothing was written), and **Delete**, confirmed by typing the title (the
`source_key` without one); a `404` counts as already gone. Both return to the list as it
was left.

On the list (`src/documents/`): row checkboxes and select-all (indeterminate when part of
the page is selected). The selection is kept across pages and sorts, cleared when the
tenant or the search changes, and never put in the URL. **Bulk delete** is confirmed by
typing `delete N`, lists up to five titles, and sends batches of 100 (each all or nothing);
ids already gone are reported in the toast; if a later batch fails, the dialog says what
was deleted and keeps the rest selected. All writes go through `src/documents/mutations.ts`,
which updates or invalidates the cached data they change.

## Routes

`/connect`, `/documents`, `/documents/:docId`, `/settings`; everything but `/connect` needs
a connection. They are listed in `src/paths.ts`. **No UI route may start with an API path**
(`/admin`, `/health`, `/docs`, `/redoc`, `/openapi.json`): on a shared origin the proxy
sends those to the API. `src/paths.test.ts` reads the API's paths from `docs/openapi.json`
and fails on a clash. A server serving `dist/` must answer unknown paths with `index.html`.

## Commands

```sh
pnpm dev            # dev server with hot reload
pnpm build          # type-check and build into dist/
pnpm check          # everything CI-like: gen:api:check, lint, format:check, typecheck, test
pnpm test           # Vitest once (test:watch to keep it running)
pnpm lint           # ESLint (type-aware typescript-eslint, react-hooks)
pnpm format         # Prettier (format:check only checks)
pnpm gen:api        # regenerate src/api/schema.d.ts from ../docs/openapi.json
```

## API types

`src/api/schema.d.ts` is generated by [openapi-typescript](https://openapi-ts.dev/) from the
API's committed contract, `../docs/openapi.json`, and committed. Never edit it. After an
API change: `uv run python scripts/export_openapi.py` at the repo root, then `pnpm gen:api`
here, and commit both with the change. `pnpm gen:api:check` (part of `pnpm check`) fails
when the file is stale. Requests use [openapi-fetch](https://openapi-ts.dev/openapi-fetch/)
with these types: `useApiClient()` gives the client of the current connection (it sends
`X-API-Key`), and `unwrap(client.GET(...))` returns the data or throws `ApiError`.

`ApiError` (`src/api/errors.ts`) is the one error type: `status` (null when the API could
not be reached, which includes a CORS refusal), `items` (the API's `{"detail": [...]}`),
`type` (the first item's code) and `fieldErrors()` (messages by field, for forms). A body
that is not the API's error format (a proxy's HTML page) becomes one generic item.

## Styling

Theme tokens are CSS variables in `src/index.css`, copied from the prototype and named as
shadcn/ui expects (`primary` is the brand accent `#2f6fed`; shadcn's `accent` is a hover
background), plus `success`, `warning`, `danger-muted` and `link`. Light and dark themes:
`index.html` sets the `dark` class on `<html>` from the system preference. Fonts are
self-hosted (Inter, JetBrains Mono for ids, hashes and configs) via Fontsource.

shadcn/ui components are added as needed with `pnpm dlx shadcn@latest add <component>`
(config in `components.json`; it resolves `@/` through the root `tsconfig.json`, and wrote
into a literal `@/` folder before that was set); they are copied into `src/components/ui/`
and are ours to edit. When `add` asks to overwrite an existing component (a dependency such
as `button`), answer no (`yes n | pnpm dlx shadcn@latest add …`): ours carry changes. The
registry's components import `cn` from shadcn's `cn` package
whatever the config says, and `add` installs it: after adding, point the import at
`@/lib/utils` and `pnpm remove cn`. shadcn/ui is MIT-licensed (<https://github.com/shadcn-ui/ui>, copyright shadcn);
the copied files keep that licence.

## Tests

Vitest with jsdom and Testing Library. [MSW](https://mswjs.io/) intercepts `fetch`: a request
no handler answers fails the test (`onUnhandledFrame: 'error'`), so tests never reach a real
API. Shared handlers go in `src/test/handlers.ts`; a test adds its own with `server.use()`.

**Tests that send a file run under happy-dom** (`// @vitest-environment happy-dom` at the top
of `src/upload/UploadDialog.test.tsx`), the rest under jsdom. In Vitest's jsdom environment
`fetch` cannot send a multipart body with a file: its typed arrays come from another realm,
so Node miscounts the body (`RequestContentLengthMismatchError`). happy-dom runs in Node's
own realm; the page is given the mocked API's origin (as behind the production proxy) so it
sends no CORS preflights. Browsers are not affected. The setup also stubs what jsdom lacks
and the UI calls: `matchMedia` and pointer capture (the toaster). An MSW response is single use: build
one per request (`() => HttpResponse.json(...)`), never share an instance.

## Layout

```
index.html            entry; sets the theme class before the first paint
vite.config.ts        Vite + Vitest config, `@/` alias for src/
eslint.config.js      flat config; .prettierrc.json; components.json (shadcn/ui)
scripts/gen-api.mjs   schema.d.ts generation and its --check
src/
  main.tsx            fonts, CSS, React root
  App.tsx             router + connection provider
  routes.tsx          the route tree; paths.ts lists the paths (and paths.test.ts guards them)
  index.css           Tailwind, theme tokens (light and dark)
  api/                schema.d.ts (generated; schema.test.ts checks it at compile time),
                      client.ts (createApiClient, unwrap), errors.ts (ApiError)
  connection/         storage, base URL rules, provider + useConnection/useApiClient, guard
  layout/AppShell.tsx header, nav, Disconnect, internal-use banner
  documents/          the list: DocumentsPage, listParams (URL <-> state), queries,
                      mutations (rename, reprocess, delete, bulk delete), useSelection,
                      SelectionBar, BulkDeleteDialog,
                      TenantFilter (sidebar + narrow select), DocumentsTable, StatusBadge,
                      status (reasons in words), Pagination
  document/           the detail (lazy-loaded route): DocumentPage, params (URL <-> state, back
                      link), queries, TitleEditor, ReprocessButton, DeleteDialog,
                      FactsPanel, ContentTab + Markdown (safe rendering) + LazyMarkdown,
                      ChunksTab + ChunkCard, ViewToggle, NotFound, TabError, errors
  upload/             UploadDialog (+ LazyUploadDialog), FileDrop, Field, useUpload (mutation,
                      error placement), useExistingDocument (overwrite warning), validation
  settings/queries.ts useIndexingSettings (GET /admin/settings)
  hooks/              useDebouncedValue
  components/         CopyButton (feedback, "Copy unavailable" outside secure contexts),
                      ConfirmByTyping
  pages/              ConnectPage, NotFoundPage, Placeholder (until U8)
  components/ui/      shadcn/ui: button, input, label, card, alert, table, badge (+ success,
                      warning variants), tooltip, skeleton, tabs, dialog, sonner (toasts;
                      without next-themes), checkbox, collapsible, dropdown-menu,
                      alert-dialog
  lib/                utils.ts (cn), format.ts (relative time, UTC time, sizes)
  test/               setup.ts (jest-dom, MSW, storage reset), server.ts, handlers.ts,
                      render.tsx (renderApp(path, {connected}): router, query client,
                      location probe and Back), fixtures/ (Spanish documents, a procedure
                      in Markdown with a table, links, an image and raw HTML)
```
