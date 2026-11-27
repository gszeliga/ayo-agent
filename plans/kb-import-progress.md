# Docling import milestone: plan and progress

A CLI that converts documents to Markdown with docling and uploads them to the knowledge
base. No spec file: the request (2026-11-26: "scan a folder or pick a file, transform each
document to Markdown into a target folder or next to it, then upload each with our API")
and the decisions below are the agreement.

## Next (resume here)
**The follow-ups are done** (K3-K7, 2026-11-27): see "Open items". Nothing is planned
next: ask the user.

## Decisions (agreed 2026-11-26)
1. **A CLI entry point** `docling-import-files` (the user's name), in
   `src/ayo_copilot/docling_import/`, with tests; not a loose script.
2. **docling as an optional dependency group** `convert` (`uv sync --group convert`), so
   the API's install never carries torch. Imported only when a run converts; missing ->
   exit 2 with the install hint. Tests fake the converter and never import docling.
3. **docling defaults**: `DocumentConverter().convert(...).document.export_to_markdown()`,
   images as placeholders, no picture export, no extra options (the user's manual use).
4. **Input:** a file or a folder; flat unless `--recursive`; hidden entries and `--out`'s
   tree skipped. Formats: PDF, DOCX, PPTX, XLSX, HTML/HTM, CSV, AsciiDoc, PNG/JPEG/TIFF/BMP/
   WebP. `.md` files are taken as they are (unless they are a scanned source's output).
5. **Output:** `<stem>.md` next to the source, or under `--out` keeping subfolders. Up to
   date (Markdown mtime >= source mtime) -> skipped unless `--reconvert`. Two sources with
   the same output -> exit 2 before writing anything. Writes are atomic (temp + replace).
6. **Upload (K2):** httpx2 to `--api-url` (default `http://127.0.0.1:8000`), `ADMIN_API_KEY`
   from `.env` (never printed), `--tenant` required, `source_key` = the `.md` file name; a
   source-key clash within the run stops it before uploading. `--no-upload`, `--force`.
7. **Output lines:** paths, actions, statuses, error type + first line of the message
   (capped at 200 chars); never document content. Exit 0 / 1 (some file failed) / 2 (could
   not start). A file with no text extracted counts as failed.

## Decisions (agreed 2026-11-27)
8. **Progress (K3):** a `converting (n/N) <source> …` line before each conversion (N counts
   only the files to convert), every line flushed (`print(flush=True)`), `--verbose`/`-v`
   sets the root logger to INFO (docling's logs). Scanned files of other types are listed
   `skipped (unsupported: .ext)` first (also in a dry run) and counted in the summary;
   `plan_import` returns a `Plan` (items + skipped). No per-page progress bar (no clean
   hook in docling).
9. **Old Office formats (K4):** `--office-converter PATH`, else OnlyOffice's
   `x2t` (`/opt/onlyoffice/desktopeditors/converter/x2t`), else `soffice`/`libreoffice` on
   PATH; convert to the new format in a temporary folder (timeout 300 s, exit 0 + non-empty
   output, the converter's messages never printed), Markdown named after the original;
   `X.ppt` beside `X.pptx` -> the old one is skipped. Without a converter: skipped + hint.
   `--office-converter` names x2t by its file name (`x2t`), anything else is LibreOffice.
   A single old file given by name without a converter is a `PlanError` (exit 2). The
   office line (`old Office files through x2t (PATH)`) prints only when an old file is to
   be converted. `knowledge-docs/` (the user's local customer documents) is git-ignored.
10. **File mode (K5):** `write_markdown` chmods its temporary file before the rename: the
    replaced file's mode if there is one, else `0o666 & ~umask` (read with `os.umask`,
    set and restored: fine in a single-threaded CLI). Files written before K5 keep 0600
    until reconverted; the tool does not touch files it does not write.
11. **Voyage 429s (K6, server side):** the user's import hit `429 Too Many Requests`; the
    embedder's retries (3, waits up to 1, 2, 4 s: about 7 s) ended inside Voyage's
    per-minute window. `VoyageEmbedder` now waits for `Retry-After` when sent (seconds or
    an HTTP date; `parse_retry_after` moved from `llm/openrouter.py` to `retry_after.py`),
    else full-jitter backoff capped at 30 s per wait; `EMBEDDING_MAX_RETRIES` default
    3 -> 6, new `EMBEDDING_RETRY_BUDGET_SECONDS` (60, per request/batch: no wait that
    would end past it). `embed_query` uses at most `QUERY_RETRY_BUDGET_SECONDS` (10 s, a
    constant): search and copilot turns fail fast. One WARNING per retry (status or
    exception type, attempt, delay); after a retry the error says `, after N attempts`.
    Client-side pacing in `docling-import-files`: K7.
12. **`--delay SECONDS` (K7):** float >= 0 (finite), default 0. Before an upload, wait
    what is left of the delay since the last upload that ended `indexed` or rejected
    (413/422/502...); conversion time counts. `unchanged` (no embedding) starts no gap; the
    first upload never waits. A wait prints `waiting     N.N s`. Accepted, and without
    effect, with `--dry-run` and `--no-upload`. No adaptive slow-down after a 429 (the
    server retries: K6). `main()` takes `sleep` and `clock` for tests.

## Steps
- [x] K1 (2026-11-26): convert: plan, converter, CLI (`--out`, `--recursive`, `--reconvert`,
  `--dry-run`), docs. 25 unit tests.
- [x] K2 (2026-11-26): upload: `Uploader` (httpx2), rejected vs aborted, source-key clash
  check, summary and exit code, `--tenant`, `--api-url`, `--no-upload`, `--force`;
  21 `MockTransport` tests (46 for the tool).
- [x] K3 (2026-11-27): progress: `converting (n/N)` lines, flushed output, `-v`, skipped
  files listed and counted (`Plan`). 10 new tests (56 for the tool).
- [x] K4 (2026-11-27): old Office formats: `office.py` (`X2tConverter`, `SofficeConverter`,
  `find_office_converter`, `UpgradingConverter`), skip reasons in the plan,
  `--office-converter`. 28 new tests (84 for the tool).
- [x] K5 (2026-11-27): Markdown files get the umask mode (or keep the replaced file's)
  instead of `mkstemp`'s 0600. 3 new tests (87 for the tool).
- [x] K6 (2026-11-27): Voyage retries outlast a rate-limit window: `Retry-After`, 30 s cap,
  60 s budget, 10 s for queries, a warning per retry. 9 new embedder tests.
- [x] K7 (2026-11-27): `--delay SECONDS` between embedded uploads. 12 new test cases
  (99 for the tool).

## Log
- 2026-11-26, K1: `docling>=2.153.0` in the `convert` group (locked, not installed here:
  it was not needed for the tests). `DoclingConverter` is untested against real docling;
  the first manual run checks it.
- 2026-11-26, K2: decisions refined in the brief: no `--api-key` flag (shell history);
  `ImportSettings` (just `ADMIN_API_KEY`, optional) in `config.py`, like `LLMSettings`.
  401, 404/405 and transport errors abort (exit 2, the rest counted "not attempted");
  413/422/502/other statuses are per file. No client retries: a rerun is cheap
  (`up_to_date`). Read timeout 120 s (the server embeds in the request). Files that were
  already up to date are uploaded too; their line says `unchanged` when the API answers
  `up_to_date`. Only the API's origin is printed (no credentials or path).

- 2026-11-27, K3: the first real run (50 documents under `knowledge-docs/`, by the user)
  showed nothing after docling's "Loading weights" for minutes: a line was printed only
  when a file was done, and docling's own logs are INFO (hidden). That run also showed
  the 2 `.ppt` files being left out silently. OnlyOffice's `x2t <in.ppt> <out.pptx>`
  (OnlyOffice Desktop Editors 10.0) converted one of them in 0.7 s, text intact: the basis
  of decision 9.
- 2026-11-27, K4: real check (no upload): `PDCA ESP 2012.ppt` -> x2t -> docling ->
  Markdown in 10 s (971 words), temporary folder removed. Tests inject the converter
  lookup: this machine has x2t, and the CLI tests must not depend on it.
- 2026-11-27, K5: the 0600 mode came from `mkstemp` (since K1), seen in the K4 real check.
- 2026-11-27, K6: whether Voyage sends `Retry-After` on 429 is not checked (no billed call
  made); both paths are tested. `.env` sets no `EMBEDDING_*` retry value, so the new
  defaults apply after a restart. Not tried against Voyage.
- 2026-11-27, K7: the wait is measured from the end of the previous embedded upload, not
  its start: the server's own retries (K6) already stretch a rate-limited upload.

## Open items
- docling's own Python warnings (`holder.bbox = ...`, RapidOCR) go to stderr; not ours to
  silence.
- `DoclingConverter` ran for real for the first time on 2026-11-27 (the user's run); its
  outcome is not recorded here yet.
- No real upload has been made with the tool (billed embeddings). First one: a local API,
  one small file, with the user's OK.
- Title: the server's default (first `# ` heading, else the file name); no `--title`.
- Uploads are sequential; parallel uploads were not needed.
- K6: the budget is per embedding request (one batch of 128 chunks). A document with
  several batches that are all rate limited can make the server take longer than the
  uploader's 120 s read timeout; the file then fails and a rerun picks it up. If 429s
  persist (e.g. Voyage's low limits without a payment method), use `--delay` (K7).
