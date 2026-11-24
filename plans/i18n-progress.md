# UI languages milestone: plan and progress

The admin UI (`ui/`) in English and Spanish, built so more languages can be added later.
There is no spec file: the request ("multi language support in the UI, Spanish along with
English as a starting point", 2026-11-23) and the decisions below are the agreement. The
decisions here win over the plan and the log. Front end only: no API, OpenAPI or backend
change, and no billed call anywhere in this milestone.

## Next (resume here)
I1 is done (2026-11-24). **Next: I2.** Write its brief and wait for the user's OK; it
starts by agreeing the glossary (decision 7), then the connect screen, `describeError`
and the connection messages. The shell's Spanish from I1 is adjusted if the glossary
differs.

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

## Glossary
To be agreed in I2.

## Order of work (one commit per step, brief first, stop after each)
- [x] **I1** Setup, language picker, locale-aware formatters, the shell translated.
- [ ] **I2** Glossary agreed (recorded above); connect screen, `describeError`, connection
  messages (`src/pages/ConnectPage.tsx`, `src/connection/*`, `src/api/errors.ts`).
- [ ] **I3** Documents list: filters, table, pagination, selection, bulk delete and
  reprocess dialogs, upload (`src/documents/*`, `src/upload/*`).
- [ ] **I4** Document detail: facts, content, chunks, rename, reprocess, delete
  (`src/document/*`, `src/components/ConfirmByTyping.tsx`, `CopyButton.tsx`).
- [ ] **I5** Search and Settings, including `ServiceDetails` (`src/search/*`, `src/settings/*`).
- [ ] **I6** Test chat: cases list, filters, case view, composer, send errors, phases,
  `chat/format.ts` (`src/chat/` minus the inspector).
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
