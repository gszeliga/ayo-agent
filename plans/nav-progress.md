# Header navigation milestone: plan and progress

The admin UI's header (`ui/src/layout/AppShell.tsx`), redesigned so the navigation is easy
to find. There is no spec file: the request ("alternative designs for the top nav bar that
make the experience smoother and clearer", 2026-11-27), the design canvas of alternatives
(A-D, private: https://claude.ai/artifact/LTn3Dnz3woLSMsM1GFKvBD) and the decisions below
are the agreement. Front end only: no API change and no billed call.

## Next (resume here)
**The milestone is done** (N1-N3, 2026-11-27): see "Final report" and "Open items" at the
end. Nothing is planned next: ask the user.

## The problem (2026-11-27)
- Test chat was an outlined accent pill: it read as an action, not a place.
- The knowledge pages were grey, borderless text without icons; the "KNOWLEDGE" label read
  as a heading, not a menu.
- The status dots, theme, language and Disconnect shared the row at the same weight.
- The current page was only a light grey fill.

## Decisions (agreed 2026-11-27)
1. **Option D: one row, real tabs, the utilities folded away.** Tabs with icons, the bar's
   full height, the current one underlined in the primary colour, bold, its icon primary.
   Test chat is an ordinary tab (supersedes decision 21 in `chat-progress.md`); a divider
   after it keeps the grouping, and the knowledge pages are a group named "Knowledge base"
   for screen readers (no visible label). Below `md` the tabs show only icons (names
   `sr-only`) and the row scrolls sideways instead of wrapping.
2. **Three steps**: N1 the tabs; N2 the status pill (one pill: "All systems ok", or the
   failing service in the danger colour, or "Checking…"; the popover and its aria-label
   unchanged); N3 the connection menu (the host with a chevron: "Connected to <host>",
   Theme and Language as menu radio groups listed vertically, Disconnect in the danger
   colour; replaces the separate buttons; `LanguageToggle` stays for the connect page).
3. **N1 keeps the host under the brand** until N3 moves it into the menu (a small change
   from the N1 brief, which dropped it at once: no step goes without it). The brand's text
   hides below `sm`.

## Progress log
- [x] **N1** (2026-11-27): the tabs. `AppShell.tsx`: `NavTab` (icon + label, underline when
  current), the divider, the group "Knowledge base" (`shell.knowledge` -> `shell.knowledgeBase`,
  "Base de conocimiento"); the bar is one `h-14` row with no wrap. New
  `layout/AppShell.test.tsx` (the current tab per path, icons and the group, Spanish name);
  `ChatPage.test.tsx` follows the group's new name. Docs: `ui/README.md` "Navigation".
- [x] **N2** (2026-11-27): the status pill. `StatusIndicator.tsx`: one rounded pill with the
  existing `StatusDot`; `layout/healthSummary.ts` (`summarizeHealth`: ok, one or both down,
  checking while pending, unknown after a failure; own file for the fast-refresh lint).
  The `aria-label` is unchanged, so the Settings and Upload tests pass as they were.
  `status.summary.*` added, `status.database` / `status.embeddings` (no longer used)
  removed. New `layout/StatusIndicator.test.tsx` (each state, the popover, Spanish).
  Docs: `ui/README.md`, service status.
- [x] **N3** (2026-11-27): the connection menu. New `layout/ConnectionMenu.tsx` (outline
  button: server icon, the host, a chevron; "Connected to <host>" via `<Trans>`, Theme,
  Language, Disconnect as a destructive item). `ThemeToggle.tsx` -> `ThemeChoices.tsx` (the
  radio group only: the button had no other user); `LanguageChoices` pulled out of
  `LanguageToggle.tsx`, which the connect page keeps. The host leaves the brand (decision 3
  ends). Copy: `shell.connectionMenu`, `shell.connectedTo`; `theme.trigger` and
  `theme.current` removed. Tests: new `ConnectionMenu.test.tsx`; the theme and language
  tests open the menu; `openConnectionMenu(user)` in `test/render.tsx`; App, Documents and
  Connect tests follow. `a11y.test.tsx` checks the open menu itself (decision 4).
  Docs: `ui/README.md` (Navigation, Themes, Languages, layout).

## Decisions (agreed during the steps)
4. **axe checks the open menu on its own** (`a11yViolations(menu)`): Radix portals the menu
   outside every landmark, so axe's "region" best practice flags the whole page with it
   open; the menu's own markup is what this test is for.

## Final report (2026-11-27)
Option D is in: one header row with the brand, four tabs (icon + name, the current one
underlined; icons only below `md`), one status pill and a connection menu holding the
host, theme, language and Disconnect. Three commits (N1-N3); front end only; `pnpm check`
green (701 tests, axe on every screen in both languages, the open menu included).
Not checked in a browser by Claude: the look, dark mode and narrow widths are the user's
to check (`pnpm dev`).

## Open items
- A side menu (option B on the canvas) if the number of pages grows past what one row holds.
- Keyboard shortcuts for the tabs, if people ask for them.
- The connect page still has its own language button only (no theme): fine while the
  theme follows the system by default.
