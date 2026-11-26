# Docling import milestone: plan and progress

A CLI that converts documents to Markdown with docling and uploads them to the knowledge
base. No spec file: the request (2026-11-26: "scan a folder or pick a file, transform each
document to Markdown into a target folder or next to it, then upload each with our API")
and the decisions below are the agreement.

## Next (resume here)
**The milestone is done** (K1-K2, 2026-11-26): see "Open items". Nothing is planned next:
ask the user.

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

## Steps
- [x] K1 (2026-11-26): convert: plan, converter, CLI (`--out`, `--recursive`, `--reconvert`,
  `--dry-run`), docs. 25 unit tests.
- [x] K2 (2026-11-26): upload: `Uploader` (httpx2), rejected vs aborted, source-key clash
  check, summary and exit code, `--tenant`, `--api-url`, `--no-upload`, `--force`;
  21 `MockTransport` tests (46 for the tool).

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

## Open items
- `DoclingConverter` has not run against real docling yet (`uv sync --group convert` was
  not run here: torch, large). First real run: one document, `--no-upload`.
- No real upload has been made with the tool (billed embeddings). First one: a local API,
  one small file, with the user's OK.
- Title: the server's default (first `# ` heading, else the file name); no `--title`.
- Uploads are sequential; parallel uploads were not needed.
