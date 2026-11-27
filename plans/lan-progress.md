# The UI from another device on the network: progress

Goal (2026-11-27): use the admin UI, and through it the API, from a phone or another
computer on the same network. No spec file; agreed in the chat.

## Decisions (agreed 2026-11-27)

1. **Proxy the API through the UI's server, not bind the API to the network.** First
   brief (H1): `API_HOST`/`API_PORT` settings for `main()`, plus `CORS_ALLOWED_ORIGINS`
   for the LAN origin. Replaced by H1 below: the Vite dev and preview servers forward the
   API's paths to `127.0.0.1:8000`, so the UI and the API share one origin (no CORS, as
   behind Caddy in production, `plans/ui-progress.md` decision 5) and only the UI's port
   is open to the network; the API keeps listening on `127.0.0.1`.
2. **Network exposure is opt-in**: `pnpm dev --host` or `pnpm preview --host`; the config
   never sets `host`.
3. **The proxied prefixes are read from `docs/openapi.json`** (plus `/docs`, `/redoc`,
   `/openapi.json`), with the same rule as the route-clash test (`src/apiPaths.ts`), so a
   new API prefix is proxied without touching the config.
4. **`pnpm dev` defaults to the page's own origin**: `ui/.env.development` (which set
   `VITE_API_BASE_URL=http://127.0.0.1:8000`) is removed. On the laptop too, `pnpm dev`
   no longer needs `CORS_ALLOWED_ORIGINS`; the setting stays for a UI on another origin
   (deployment phase 2).
5. Out of scope: HTTPS, access control beyond the key, reaching the laptop from outside
   the network (Tailscale would be a separate step), any API change.
6. **The address is shown as text behind a Change button (H2)**, asked for after H1: the
   default is right almost always, and a phone user saw the field as a question. The field
   opens on Change, or by itself after a "no answer" failure; it stays open once opened.

## Steps

- [x] H1. Vite proxy for the API's paths (2026-11-27).
- [x] H2. The connect screen's address as text behind Change (2026-11-27).

## Log

- **H1 (2026-11-27).** `src/apiPaths.ts`: `API_DOC_PATHS`, `apiPrefixes` (moved from
  `paths.test.ts`), `isUnderPrefix` (the former `clashes`) and `proxyPattern` (a `^`
  regular-expression key, so `/admin` never catches `/administration` and the query
  string is allowed). `vite.config.ts` reads the contract and proxies every prefix to
  `http://127.0.0.1:8000` in `server` and `preview` (preview pinned to 4173).
  `ui/.env.development` removed. Tests (`src/apiPaths.test.ts`): the prefixes come from
  the contract; every contract path (parameters filled in, with a query string) is
  proxied; no UI route, `/` or `/administration` is; the pattern agrees with
  `isUnderPrefix`. `paths.test.ts` uses the shared helpers. Tried by hand against the
  running API: `/`, `/documents`, `/chat` and `/administration` answer the UI's HTML,
  `/health` and `/openapi.json` the API's JSON, `/admin/tenants` the API's 401. Docs:
  `ui/README.md` (Setup without CORS, "From another device": `--host`, firewall, plain
  HTTP, billed calls), `README.md`, `docs/configuration.md` (CORS section), `CLAUDE.md`.
  `pnpm check`: 49 files, 704 tests.
- **H2 (2026-11-27).** `ConnectPage.tsx`: `editingAddress` state; closed, the label, the
  address in monospace and a link-style button ("Change", named "Change the API address"
  for screen readers; Spanish "Cambiar" / "Cambiar la dirección de la API"); open, the
  former field, focused when it appears. A `noAnswer` result opens it. Catalogs:
  `connect.change`, `connect.changeAddress`. Tests: closed by default with the origin as
  text, Change opens a focused field with the value; connecting without opening it keeps
  the origin; an address that answers nothing opens the field, focused. The tests that
  type an address (connect, chat, documents) click Change first; the axe pass covers the
  closed screen. Side fix: `vite.config.ts` imports `./src/apiPaths.ts` with its
  extension (Vite warned that the native config loader will require it). The deletion of
  `ui/.env.development` (H1) was left out of H1's commit by mistake and lands here; the
  file was already gone on disk, so H1's checks ran without it. `pnpm check`: 706 tests.

## Open items

- Not tried from a real phone yet (only through the proxy on this machine).
- HTTPS on the network (the key crosses it in plain text) waits for D1 or a tunnel.
