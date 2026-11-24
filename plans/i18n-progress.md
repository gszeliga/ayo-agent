# UI languages milestone: plan and progress

The admin UI (`ui/`) in English and Spanish, built so more languages can be added later.
There is no spec file: the request ("multi language support in the UI, Spanish along with
English as a starting point", 2026-11-23) and the decisions below are the agreement. The
decisions here win over the plan and the log. Front end only: no API, OpenAPI or backend
change, and no billed call anywhere in this milestone.

## Next (resume here)
I1-I5 and I6a are done (2026-11-24). **Next: I6b** (the case view: header, stepper, turns,
phase marker, composer, send errors as codes, read-only notice, not found, delete dialog;
brief agreed with I6, decision 25). Write its brief again only if it changes; wait for the
user's OK. Then propose the side step for the two slow tests (I6a's log entry). Use the glossary below; `describeError`,
`relativeTime` and `formatBytes` take the language (`useLanguage().language`); counts use
i18next plurals (`count`, `_one` / `_other`).

Where the UI stands (surveyed 2026-11-23, at `c9e6b5d`):
- ~190 files, ~8,600 lines of TSX under `ui/src/`; every string is an English literal in a
  component. No i18n library.
- Dates: one fixed `Intl.DateTimeFormat('en-GB')` in `src/lib/format.ts`. Relative time
  ("just now", "5 min ago", "3 h ago", "2 d ago", then "5 Oct 2026"), `formatBytes`,
  `formatUtc` there; `formatCost`, `formatTokens`, `plural`, `formatDuration` in
  `src/chat/format.ts`. About 66 call sites outside those two files.
- UI-worded errors: `describeError` (`src/api/errors.ts`), `src/chat/sendErrors.ts`,
  `src/chat/summaryErrors.ts`, `src/document/errors.ts`, `src/upload/useUpload.ts`. The
  API's own `msg` is English.
- Phase labels: `PHASE_LABELS` in `src/chat/phases.ts`. Document status: `src/documents/status.ts`.
- Model for the picker: `src/layout/ThemeToggle.tsx` + `src/lib/theme.ts` (localStorage
  `ayo.theme`, blocked storage -> `system`) and `public/theme-boot.js`.
- Tests: Vitest + MSW, `renderApp` in `src/test/render.tsx`; ~24 test files find elements
  by English text. `src/a11y.test.tsx` runs axe-core.
- The copilot's prompts are Spain Spanish with *tú* (`src/ayo_copilot/conversation/prompts/`).
- `Intl` gives different English from today's wording: `RelativeTimeFormat('en-GB')` says
  "3 hr ago", "2 days ago", "yesterday"; currency says "US$0.02". Hence decision 6.
- Packages checked 2026-11-23: `i18next` 27.2.5 and `react-i18next` 18.0.3 (peers accept
  TypeScript 5 and React 19), `eslint-plugin-i18next` 6.1.5.

## Decisions (agreed 2026-11-23)
1. **i18next + react-i18next.** Resources bundled, initialised synchronously at import (no
   flash of untranslated text, no Suspense). Typed keys through `CustomTypeOptions`
   (`t('typo')` fails `tsc`). English is the source; Spanish is typed as the same shape
   (`Catalog`), so a missing Spanish key fails `tsc`. Not Lingui (needs a compiler plugin,
   risky with Vite 8 / plugin-react 6); not hand-rolled (plurals and interpolation).
2. **Catalogs** in `ui/src/i18n/locales/{en,es}/<area>.ts` (TypeScript, typed), one
   namespace per area: `common`, `connect`, `documents`, `document`, `search`, `settings`,
   `chat`. Keys are nested by component or purpose, not the English sentence.
3. **Choosing the language:** a header dropdown next to the theme toggle: English /
   Español / System. Language names always in their own language. System follows
   `navigator.languages` (`es*` -> Spanish, otherwise English) and the `languagechange`
   event. The choice is kept in `localStorage` (`ayo.lang`); blocked storage -> System
   (like `theme.ts`). `<html lang>` follows the active language. No boot script: React
   renders all text, so there is nothing to flash.
4. **Translated:** all UI copy: labels, aria-labels, placeholders, tab titles
   (`useDocumentTitle`), phase / status / tab names, toasts, the UI's own error messages.
5. **Not translated:** the API's `msg` (stays English, shown as received; codes the UI
   already words itself get Spanish text), document content, model output, tenant ids,
   URL parameters (`?status=indexed` stays English), the brand "AYO Admin". No backend
   change.
6. **Formatting:** `lib/format.ts` and `chat/format.ts` take a `locale: Language`
   argument and take their words from the catalogs (`i18n.getFixedT(locale, 'common')`);
   `Intl` only for dates and decimals, formatters cached per locale. Dates "5 Oct 2026" /
   "5 oct 2026"; decimals "4.2 KB" / "4,2 KB"; relative "5 min ago" / "hace 5 min"; cost
   "$0.02" / "0,02 $". The exact-time tooltip stays `2026-11-05 10:14 UTC`. Today's
   English output must not change. Until each area's step, `locale` defaults to `'en'`; I8
   removes the default so `tsc` finds any call left over.
7. **Spanish:** Spain Spanish, *tú* (as the copilot's prompts). A glossary is agreed at
   the start of I2, before the bulk of the copy (candidates: chunk, tenant, embedding,
   trace, reprocess, case, phase names, "Test chat", "Indexing settings"); it is recorded
   here under "Glossary".
8. **Tests:** tests render in English by default (existing tests unchanged);
   `renderApp(path, { language })` for Spanish. A parity test checks both catalogs for the
   same keys, the same `{{placeholders}}` and the same plural forms. Every translated area
   gets at least one Spanish render test. I8 adds an axe run in Spanish and
   `eslint-plugin-i18next` (`no-literal-string`) as an error in components.
9. **One commit per step**, brief first, stop after each (the repo's rule).
10. (I1, 2026-11-24) **i18next 27.2.4**, not 27.2.6: pnpm 11's `minimumReleaseAge` (one
    day) rejects 27.2.5 and 27.2.6, and `pnpm add` silently writes a
    `minimumReleaseAgeExclude` into a new `pnpm-workspace.yaml` to get past it. Not done:
    the gate is a supply-chain guard. A later step may move to a newer 27.x once it is
    old enough. react-i18next 18.0.3.
11. (I1) **System** takes the first entry of `navigator.languages` that the UI has
    (`['fr', 'es-MX']` -> Spanish), else English: decision 3's "`es*` -> Spanish" for the
    first entry, extended down the list, as browsers mean it.
12. (I1) **Plurals:** Spanish's CLDR forms are one / many / other; i18next falls back from
    `_many` to `_other`, so every language keeps the English keys (`_one`, `_other`) and
    `Catalog` stays one shape. The parity test checks the same keys and placeholders and
    that every plural has `_other`.
13. (I1) Formatter signatures: `relativeTime(iso, language = 'en', now)` and
    `formatBytes(bytes, language = 'en')`; the three call sites that pass `now` now pass
    `'en'` explicitly until their area's step. Bytes: `Intl.NumberFormat` with one decimal
    and no grouping, so English output is unchanged ("1024.0 KB").
14. (I1) Status trigger in Spanish: "base de datos OK / sin servicio / estado
    desconocido" (gender-neutral after "base de datos" and "embeddings"). "Embeddings"
    stays untranslated pending the glossary.
15. (I2) **A language menu on the connect screen** too (top right): the header's shows only
    once connected, and the first screen should not be stuck on the browser's language.
    Agreed 2026-11-24 (not in the plan).
16. (I2) **Messages as codes, worded when shown:** the connect screen's field errors, its
    form error and the connection notice (`ConnectionNotice = 'keyRejected'`, replacing the
    `KEY_REJECTED` sentence) are kept as codes or as the error itself, so a switch rewords a
    message already shown. `describeError(error, baseUrl, language = 'en')` words the
    network error and `unexpected_response` ("The API answered HTTP 502") itself; any other
    `msg` is the API's, shown as received (decision 5). Its other callers stay English until
    their area's step.

17. (I3, 2026-11-24) **I3 split in three** (I3a list, I3b bulk dialogs, I3c upload): about
    2,300 lines in 21 files, too much for one reviewable step. `ConfirmByTyping` moves
    from I4 to I3b (bulk delete uses it first). **The phrase to type is translated**
    ("delete 130" -> "eliminar 130"): people type what they see. The single delete's
    phrase is the document's name, unchanged.
18. (I3a) **Option labels by value:** `STATUS_OPTIONS`, `SORT_OPTIONS` and
    `OUTDATED_REASONS` are lists of the API's values; their words are in the `documents`
    catalog keyed by those values (`sort.-updated_at`), so `listParams.ts` holds no UI
    text and the URL stays English. `outdatedReasonLabel(reason, language)`; Settings
    passes `'en'` until I5. `LoadError` (shared by every screen) takes the language now,
    in step with its Retry, Spanish since I1. English copy unchanged, including "(1 on
    other pages)" (the plural keys are there; English wording kept as it was).

19. (I3b) **Markup in a string** goes through `<Trans>` with a self-closing component
    (`'Type <phrase/> to confirm'`, the element given with its own children), so the
    value (a document's name in I4) is never parsed as markup. The parity test also
    compares `<Trans>` tags. Dialog errors are kept as the `Error` and worded when shown
    (decision 16); toasts are worded once, when shown. `REPROCESS_PROVIDER_FAILED` stays
    a literal in `ReprocessButton.tsx` until I4 (a computed export there trips
    react-refresh); the catalog's `reprocessProviderFailed(language)` replaces it then.

20. (I3c) **An `upload` namespace** (added to decision 2's list): the dialog opens from the
    list (upload) and the document page (replace), so its replace mode is Spanish before
    I4. Problems are codes (`validation.ts` `Problem`, `useUpload.ts` `FormProblem`),
    worded when shown; a 422's `msg` for a field is the API's and shown as received.
    `useUploadProblems` became a plain function (`uploadProblems`): the wording, the only
    part that needed the connection, moved to the render. The tests' imported constants
    (`PROVIDER_FAILED`, `CANCELLED_NOTE`) became literals in the test.
21. (I3c) **English oddities kept for now**, to keep English output unchanged during the
    milestone; to fix in I8 (or later, the user's call): "1 chunks" in the upload toast,
    "(1 on other pages)" in the selection bar, "Reprocess all 1 outdated". The plural keys
    are in place, so each fix is a one-word catalog change.

22. (I4) **`document` namespace.** `backLink()` returns `{ to, target }` and
    `highlightLabel()` became `highlightSource()` (`'chat' | 'search'`): codes, worded by
    the page (`back.*`, `backTo.*`, `chunks.highlight.*`); `params.test.ts` asserts the
    codes now. `configDiff` (in `settings/`, used only by the facts panel) takes a
    `language` (default `'en'` until I8) and its part names are in `document.configPart`;
    an unknown part shows as is. Rename problems are codes, delete errors the `Error`,
    worded when shown. `DOCUMENT_CHANGED` and `REPROCESS_PROVIDER_FAILED` left
    `ReprocessButton.tsx` (closes the I3b loose end); `actions.test.tsx` uses literals.
    `CopyButton`'s "Copied" / "Copy unavailable" are in `common` (shared: Search and Chat
    get them now; their labels stay English until their step). The delete phrase is the
    document's name, unchanged. "Reprocessed: 1 chunks" and "its 1 chunks" kept in
    English (decision 21). Spanish view toggle: "Formateado / Texto".

23. (I5, 2026-11-24) **I5 split in two** (agreed): I5a Settings and `ServiceDetails` (the
    Settings card and the header's popover), I5b Search. New `settings` namespace; service
    states and locations by the API's value. Spanish states "En marcha / Sin servicio /
    Desconocido" (neutral after "Base de datos" and "Embeddings"), location "Remota";
    the header trigger keeps I1's "OK / sin servicio". Env var names inside sentences go
    through `<Trans>` `<code>` tags (the text inside comes from the catalog, never from
    data). Settings' outdated reasons follow the UI language now (closes decision 18's
    `'en'`).

24. (I5b) **`search` namespace.** Search problems are codes (`FieldProblem`,
    `OtherProblem`), worded when shown; a 422's `msg` for a field is the API's. Decimals
    through a new `formatDecimal(value, language, { min, max })` in `lib/format.ts`
    (cached `Intl.NumberFormat`, no grouping; `toFixed` output in English): similarity 4
    decimals, timings 1, the typed minimum up to 15 (more shows the binary value).
    `tenantsSummary` takes a language (default `'en'` until I8). The question placeholder
    is an example question in Spanish in both languages (the content's language). **A
    small English change:** with options set, the Options button's accessible name was the
    run-together "Options1set" (names are joined without spaces, so the badge's sr-only
    " set" lost its space; no test covered it); it now has an `aria-label`, "Options, 2
    set" / "Opciones, 2 activas", and the badge is `aria-hidden`. New English test for it.

25. (I6, 2026-11-24) **I6 split in two** (agreed): I6a the cases column (formatters,
    phase names, list, filters, rows, panels, new conversation), I6b the case view. The
    `chat` namespace holds both and I7's inspector. "overdue" -> **"atrasada(s)"** (the
    user's choice). Phase names by value (`chat.phase.*`); `PHASE_LABELS` stays for the
    files not translated yet and goes in I7. `formatCost` / `formatTokens` /
    `formatDuration` take `language` (default `'en'` until I8) and use `formatDecimal`
    ("0,02 $", "12,3k tokens", "4,5 s"); `plural()` stays for the inspector until I7.
    **Deviation from the brief:** `PanelToggle` takes `panel: 'cases' | 'inspector'` and
    words the whole phrase from the catalog (`panel.hide.*` / `panel.show.*`) instead of
    taking two labels, so the inspector's toggle is Spanish already (as `CopyButton` in
    I4); the inspector's resize label stays English until I7. The rail's sr-only " cases"
    is a plural suffix after the visible count.

## Glossary
Agreed 2026-11-24 (I2). Spain Spanish, *tú*. The API's field names and URL parameters stay
English (`tenant`, `?status=indexed`); ids are shown as they are.

| English | Spanish | Note |
|---|---|---|
| tenant | organización | the user's choice; "Organización" as a label |
| chunk / chunks | chunk / chunks | kept, the user's choice |
| embedding(s) | embeddings | kept |
| trace | traza | |
| reprocess | reprocesar | |
| case | caso | |
| phases | Entender, Cuestionar, Analizar, Actuar, Seguimiento, Cerrado | as the copilot's `prompts/glossary.md` |
| Test chat | Chat de prueba | |
| Indexing settings | Ajustes de indexación | |
| document | documento | |
| upload | subir | |
| source key | clave de origen | |
| turn | turno | |
| summary | resumen | |
| action(s) | acción / acciones | |
| inspector | inspector | |
| session | sesión | |
| Indexed / Outdated | Indexado / Desactualizado | |
| admin key | clave de administración | |

## Order of work (one commit per step, brief first, stop after each)
- [x] **I1** Setup, language picker, locale-aware formatters, the shell translated.
- [x] **I2** Glossary agreed (recorded above); connect screen, `describeError`, connection
  messages (`src/pages/ConnectPage.tsx`, `src/connection/*`, `src/api/errors.ts`).
- [x] **I3a** Documents list: page, filters, table, badge, pagination, selection bar,
  empty states (decision 17).
- [x] **I3b** Bulk delete and bulk reprocess dialogs, their toasts, `ConfirmByTyping`.
- [x] **I3c** Upload: dialog, file drop, field checks, API error placement, toasts
  (`src/upload/*`).
- [x] **I4** Document detail: facts, content, chunks, rename, reprocess, delete
  (`src/document/*`, `src/components/ConfirmByTyping.tsx`, `CopyButton.tsx`).
- [x] **I5a** Settings and the service status (`src/settings/*`, decision 23).
- [x] **I5b** Search (`src/search/*`, decision 24).
- [x] **I6a** Test chat: the cases column, phases, `chat/format.ts`, new conversation
  (decision 25).
- [ ] **I6b** Test chat: the case view, composer, send errors, delete dialog.
- [ ] **I7** Inspector: State, Trace, Summary, Actions tabs, summary errors, export (the
  brief proposes whether the export follows the UI language).
- [ ] **I8** `locale` defaults removed, lint rule as error, axe in Spanish, docs, final
  report and "Open items"; CLAUDE.md marks the milestone done.

### I1 brief: setup and the shell
**Delivers:** a working English / Español / System switch in the header, and the shell
translated: the internal-use banner and Dismiss, the nav (Test chat, Knowledge,
Documents, Search, Indexing settings, the `Main` nav label), the status indicator's
trigger, the theme and language menus, Disconnect, the error boundary, the 404 page, Retry
in `ErrorState`. Every other screen stays English until its step.

**New files (`ui/`):**
- `src/i18n/index.ts`: i18next init at import (bundled resources, `fallbackLng: 'en'`,
  `interpolation.escapeValue: false` since React escapes, synchronous).
- `src/i18n/resources.ts`: catalogs per language and the `Catalog` type.
- `src/i18n/i18next.d.ts`: typed keys (`CustomTypeOptions`, `defaultNS: 'common'`).
- `src/i18n/locales/en/common.ts`, `src/i18n/locales/es/common.ts`: shell copy, time
  units, sizes.
- `src/lib/language.ts`: `Language = 'en' | 'es'`, `LANGUAGE_KEY = 'ayo.lang'`,
  read / save the choice, resolve System from `navigator.languages`, `Intl` locale per
  language (`en-GB`, `es-ES`).
- `src/layout/LanguageProvider.tsx` + `languageContext.ts` (`useLanguage()`): switches
  i18next, sets `document.documentElement.lang`, follows `languagechange` on System. Goes
  inside `ThemeProvider` in `App.tsx`.
- `src/layout/LanguageToggle.tsx`: dropdown like `ThemeToggle` (lucide `Languages` icon).

**Changed:**
- `package.json`, `pnpm-lock.yaml`: `i18next`, `react-i18next` (latest, exact check of
  peers at install).
- `src/main.tsx`: imports `@/i18n` before `App`.
- `AppShell.tsx`, `StatusIndicator.tsx` (trigger only), `ThemeToggle.tsx`,
  `ErrorBoundary.tsx` (a class component: its two messages move into a small function
  component using `useTranslation`), `NotFoundPage.tsx`, `StateMessage.tsx`: copy via `t()`.
- `src/lib/format.ts`: `relativeTime` and `formatBytes` take `locale: Language = 'en'`;
  words from the catalog, date formatter cached per locale; English output unchanged.
  (`chat/format.ts` waits for I6.)
- `src/test/render.tsx`, `src/test/setup.ts`: `language` option on `renderApp`; reset to
  English and System before each test.
- Docs: `ui/README.md` gets a "Languages" section (the picker, what is and is not
  translated, how to add a string or a language); `CLAUDE.md`: active milestone in "Where
  things stand", the UI convention "English UI copy" becomes "UI copy goes through the
  catalogs (English source, Spanish typed against it)", `src/i18n/` in the layout. This
  file: tick I1, log entry.

**Tests:**
- `src/i18n/catalog.test.ts`: same keys, placeholders and plural forms in `en` and `es`,
  for every namespace.
- `src/lib/language.test.ts`: the choice round-trips; blocked storage -> System; System
  maps `es-AR`, `es` -> `es` and `fr`, `en-US` -> `en`.
- `src/layout/LanguageToggle.test.tsx`: Español turns the nav Spanish ("Documentos",
  "Búsqueda"), sets `lang="es"` and is kept; System follows `languagechange`; starting
  with `ayo.lang=es` opens in Spanish.
- `src/lib/format.test.ts`: current English cases unchanged, plus Spanish ("hace 5 min",
  "5 oct 2026", "4,2 KB").
- One Spanish case each in `ErrorBoundary.test.tsx` and for the 404 page.
- `pnpm check` passes.

**Note:** the shell's Spanish comes before the glossary (I2). It uses only common words
(Documentos, Búsqueda, Ajustes de indexación, Chat de prueba, Conocimiento, Desconectar);
I2 adjusts them if the glossary differs.

## Progress log
- 2026-11-23: plan agreed and written down (this file); UI surveyed (see "Next"). No code
  yet.
- 2026-11-24, **I1** (set-up, picker, formatters, shell). i18next 27.2.4 + react-i18next
  18.0.3 (decision 10). New: `src/i18n/` (init at import, `resources`, `Catalog`, typed
  keys, `locales/{en,es}/common.ts`), `lib/language.ts`, `LanguageProvider` +
  `languageContext` + `LanguageToggle` (header, after the theme toggle; names in their own
  language with `lang`, System in the UI's). Translated: banner, Dismiss, nav and its
  label, status trigger (aria-label and the two words), theme menu (trigger "Theme:
  dark" unchanged in English), Disconnect, error boundary (messages moved into a
  `CrashMessage` function component), 404 page and its tab title, Retry in `ErrorState`.
  `lib/format.ts` per language (decision 13). Tests: `catalog.test.ts` (parity),
  `language.test.ts`, `LanguageToggle.test.tsx` (switch, kept, `lang`, System follows
  `languagechange`, stored choice wins, a stored Spanish opens the 404 page in Spanish),
  Spanish cases in `format.test.ts` and `ErrorBoundary.test.tsx`; setup resets to English
  before each test. 524 tests; existing ones unchanged except `format.test.ts` (the
  argument order). `pnpm check` and `pnpm build` pass. Docs: `ui/README.md` "Languages"
  and layout; `CLAUDE.md`.
  **Found, not fixed (pre-existing):** under full-suite load, `bulkDelete.test.tsx` ("more
  than 100 go in batches of 100") and `DeleteExport.test.tsx` ("delete says what goes...")
  take 4.4-4.8 s against Vitest's 5 s default, on the base commit `0f8b760` as well
  (measured in a scratch worktree); 1.6-1.7 s alone either way. With I1's extra tests they
  timed out in 2 of 4 full runs here (0 of 3 on the base). Proposed side step: a longer
  timeout for those two tests (or `testTimeout: 10000`), or a faster setup in them.
- 2026-11-24, **side step: slow tests' limits.** The two tests above get 15 s (like
  `ChatSession.test.tsx`), each with a comment saying why. A scan of four full runs for
  tests over 3 s found two more near their limits, fixed the same way: "the structured
  summary is built from the case record..." (`Summary.test.tsx`, 1.6 s alone, 4.1-4.7 s in
  the suite, default 5 s) -> 15 s; "\"Reprocess all outdated\" runs every match..."
  (`bulkReprocessDialog.test.tsx`, 5.9 s alone, 13-15.1 s in the suite against a 15 s wait
  and a 20 s test) -> 30 s wait, 45 s test. Limits only, no test behaviour changed; the
  slowest stay as slow (making them faster is not done). Six full runs after: 524 passed
  each time; `pnpm check` passes.
- 2026-11-24, **I2** (glossary, connect screen, connection and error messages). Glossary
  agreed and recorded above (the user: keep "chunk", tenant -> "organización"); the I1
  shell needed no change. New `connect` namespace (`locales/{en,es}/connect.ts`): the
  connect screen's copy, field checks, tab title and the key-rejected notice; `common`
  gets `errors` (unreachable, CORS refusal, unexpected status). A language menu on the
  connect screen (decision 15). Messages as codes (decision 16): `ConnectionNotice`
  replaces `KEY_REJECTED`; `describeError` and `unreachableMessage` take a language.
  Tests: Spanish connect screen (labels, tab title, field checks reworded on a switch,
  rejected key, CORS), a language chosen there kept once connected, the notice worded in
  the language shown (`App.test.tsx`), `describeError` and `unreachableMessage` in both
  languages. 538 tests; existing ones unchanged except `App.test.tsx` (the constant became
  a literal, the 401 set-up shared). `pnpm check` passes. Docs: `ui/README.md`
  ("Languages", "Connecting"); `CLAUDE.md`.
- 2026-11-24, **I3a** (documents list). I3 split in three (decision 17). New `documents`
  namespace: tab title, heading, the count ("2 documentos", plurals), Upload button,
  filters (search, status, sort, Clear filters, "Reprocesar los N desactualizados"),
  organización sidebar and select, table headers and aria-labels, status badge and the
  outdated reasons, pagination ("1–25 de 130", Anterior / Siguiente), selection bar, empty
  states. Labels by value (decision 18); the table's dates and sizes and `LoadError`
  follow the language. Tests: four Spanish cases in `DocumentsPage.test.tsx` (the whole
  list, a count of one and the outdated button, no documents, no match); the catalog
  parity test covers the new namespace. 547 tests; existing ones unchanged except
  `listParams.test.ts` (the options are plain values now). `pnpm check` passes.
- 2026-11-24, **I3b** (bulk delete and bulk reprocess). `documents` gets `bulkDelete.*`
  and `bulkReprocess.*`; `common` gets `confirmByTyping` (`<Trans>`, decision 19). Bulk
  delete: title, warning with the chunk count, the list ("y 96 más"), the phrase to type
  ("eliminar 3", decision 17), the buttons, the toast ("Eliminado 1 documento; 2 ya no
  existían"), the partial failure. Bulk reprocess: both confirmations, the running stage
  (progress, current document, stopping, Stop, the progress bar's label), the summary
  (titles, "N documentos procesados", still selected, outcome rows by value, "No
  empezados", "Detenido en «…»: …"), the provider-failed message. Local `plural()` helpers
  replaced by i18next plurals; glued sentences became whole keys. English output
  unchanged. Tests: three Spanish cases in `bulkDelete.test.tsx` (the flow with the
  phrase in bold and the English phrase refused, already gone, a partial failure on the
  dialog alone with 101 selected, reworded when the browser's language changes) and three
  in `bulkReprocessDialog.test.tsx` (confirm and summary, a provider failure on the
  filter, running and stop); the parity test compares `<Trans>` tags. 556 tests; existing
  ones unchanged. `pnpm check` passes.
- 2026-11-24, **I3c** (upload). New `upload` namespace (decision 20): title and description
  (upload and replace), the provider-down warning, the file drop (`<Trans>` for the
  emphasised "Elige un archivo"), size, Remove file, Organización and its hint, Title,
  Advanced, Source key, Force reindex, the existing-document warning (relative time per
  language), every field check, the provider-failed and cancel notes, the buttons, the
  toasts. Tests: four Spanish cases (the form and its checks, an API field error placed as
  received and a provider failure, the existing warning and the success toast, a problem
  reworded when the browser's language changes). 566 tests; existing ones unchanged except
  the two constants in `UploadDialog.test.tsx` (decision 20). `pnpm check` passes.
  Noticed: `UploadDialog.test.tsx` prints an `Error: socket hang up` (MSW interceptor)
  from an existing English test, on the base commit too; nothing fails. Not looked into.
- 2026-11-24, **I4** (document page). New `document` namespace (decision 22): back link and
  the not-found page, header buttons, tabs, view toggle, Copy Markdown, chunks (cards,
  chars, vectors, debug badge, the outlined chunk's source, pagination, none), facts
  (labels, "sin registrar", dates and sizes per language, "Ahora difiere: …"), rename,
  reprocess (toasts, Retry, the menu), delete (dialog, toasts), `CopyButton`'s feedback.
  Tests: five Spanish cases in `DocumentPage.test.tsx` (the page with both tabs, now
  differs, not recorded, not found, the outlined chunk's label from chat and search), four
  in `actions.test.tsx` (rename checks and toast; reprocess done, up to date, 409 with
  Reintentar, 502; the forced reprocess in the menu; delete), one in `CopyButton.test.tsx`,
  two in `configDiff.test.ts`. 585 tests; existing ones unchanged except `params.test.ts`
  (codes instead of labels) and the two literals in `actions.test.tsx`. `pnpm check`
  passes.
- 2026-11-24, **I5a** (Settings and service status). I5 split in two (decision 23). New
  `settings` namespace: tab title, heading and intro, the six cards and every label and
  unit ("800 caracteres", "128 textos por petición", "800 tokens", "5,0 MB"), the outdated
  note (plurals) and reasons, the copilot card's fallback and missing-key note
  (`<Trans>`), the fake-provider note, the copy buttons; `ServiceDetails`: states,
  location, rows, relative times, "(en caché)", "Estado desconocido: …", Comprobar ahora.
  Tests: four Spanish cases in `SettingsPage.test.tsx` (the cards; the fallback and no
  key; the popover from the header; an unreachable status endpoint). 595 tests; existing
  ones unchanged. `pnpm check` passes.
- 2026-11-24, **I5b** (test search). New `search` namespace (decision 24): title, intro,
  provider-down note, the form and its hint, the local checks ("ahora N"), the 422 and
  502 messages, the organization picker (counts, loading / failed / none, the note with
  `<Trans>` for `ayo`), the options popover, result cards (similarity "0,8734", other
  model, no heading, chunk, show more / less), the summary ("mín. 0,2", timings "41,2
  ms", details rows), the skipped banner (plurals), the empty states. The Options button's
  name fixed (decision 24). Tests: seven Spanish cases in `SearchPage.test.tsx` (form and
  first visit; local checks; picker and options; results and summary; skipped banner and
  nothing to search; nothing above the minimum; a 422 placed as received and a 502 that
  rewords when the browser's language changes) and one English (the Options button's
  name). 609 tests; existing ones unchanged. `pnpm check` passes.
- 2026-11-24, **I6a** (the chat's cases column). I6 split in two (decision 25). New `chat`
  namespace: tab title, phase names, the formatters' words, the "Pick a case" state, the
  cases list (heading, New conversation, loading, no match with Quitar filtros, no
  conversations, Load more and its error, the collapsed rail with "N casos"), the filters
  (search, Organización, Fase, Estado by value), the rows ("Caso sin título", turnos,
  pendientes, atrasadas, Otro canal, "Actualizado hace 1 h"), the panel toggles and the
  resizer's value text, the new conversation page and dialog. Tests: five Spanish cases in
  `ChatPage.test.tsx` (page, rows and filters with the API's values kept; no match and no
  cases; Load more and the rail; a new conversation from the dialog to the empty chat; no
  organizations), Spanish and duration cases in `format.test.ts`. 635 tests; existing ones
  unchanged. `pnpm check` passes.
  **Found, not fixed:** 1 of 4 full runs failed two tests on Vitest's 5 s default, passing
  alone: "a new conversation asks the tenant, then the first reply opens its case"
  (`Send.test.tsx`, 4.2 s in the suite) and "a batch failing after another succeeded..."
  (`bulkDelete.test.tsx`, 4.9 s). The same pattern as I1's side step; proposed: the same
  fix (15 s each, with a comment), as a side step after I6b or before it, the user's call.

