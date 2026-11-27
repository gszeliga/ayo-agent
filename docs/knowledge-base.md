# Knowledge base: documents

How to load and manage the Markdown documents the copilot searches: upload, read,
rename, replace, reprocess, delete, and how they are chunked. Searching them is in
[search.md](search.md). Every route here needs the `X-API-Key` header (see [Endpoints](../README.md#endpoints));
`/docs` has every field, status and error `type`.

## Converting and uploading documents with docling

The knowledge base takes Markdown only. `docling-import-files` converts PDF, DOCX, PPTX,
XLSX, HTML, CSV, AsciiDoc and images with [docling](https://github.com/docling-project/docling),
using its defaults (images become `<!-- image -->` placeholders; no pictures are exported),
then uploads each Markdown file as below. docling is an optional dependency group, kept
out of the API's install because it brings torch and its layout models (a large download;
the models load on the first conversion):

```sh
uv sync --group convert                                       # once; plain `uv sync` removes it again
uv run docling-import-files manual.pdf --tenant acme          # -> manual.md next to it, uploaded
uv run docling-import-files docs/ --tenant acme --out md/ -r  # a folder tree -> md/, same subfolders
uv run docling-import-files docs/ --tenant acme --dry-run     # what it would do; writes and sends nothing
uv run docling-import-files docs/ --no-upload                 # convert only (no tenant, no key needed)
uv run docling-import-files docs/ --tenant acme --api-url https://kb.example.com   # another API
uv run docling-import-files docs/ --tenant acme -v            # also docling's own info logs
uv run docling-import-files docs/ --tenant acme --delay 10    # at least 10 s between embedded uploads
uv run docling-import-files docs/ --tenant acme --office-converter /usr/bin/soffice   # for .ppt/.doc/.xls
```

It uploads to `--api-url` (default `http://127.0.0.1:8000`) with `ADMIN_API_KEY` from the
environment or `.env` (never a flag, never printed). The `source_key` is the Markdown file's
name, so uploading again replaces the document; `--force` reindexes unchanged ones. **Each
upload of new or changed content is one billed Voyage call on the server**; unchanged
files come back `up_to_date` without one, so a rerun is cheap.

Voyage limits requests and tokens per minute. The server retries a `429` for up to a minute
([configuration](configuration.md#chunking-and-embeddings)), but a large import can still
run into the limit. `--delay SECONDS` keeps that many seconds between the end of an upload
the server embedded (or that failed) and the next upload. Time spent converting counts, so
a slow conversion is not followed by a full wait; an `unchanged` answer embedded nothing,
so the next upload does not wait for it. A wait prints `waiting     N s`. The default is 0.

A folder is scanned flat unless `--recursive`; hidden files and folders and `--out` itself
are not scanned. A file of a type the tool cannot read (`.zip`, ...) is listed as
`skipped` at the start, also in a dry run, and counted in the summary.

docling cannot read the old binary Office formats (`.ppt`, `.doc`, `.xls`), so the tool
first converts them to `.pptx`, `.docx` or `.xlsx` in a temporary folder with an office
converter: `--office-converter PATH` if given (`x2t` by its name, else LibreOffice), else
OnlyOffice Desktop Editors' `x2t` (`/opt/onlyoffice/desktopeditors/converter/x2t`), else
`soffice` or `libreoffice` on PATH. The run names the one it uses. The Markdown is named
after the original (`deck.ppt` -> `deck.md`) and no `.pptx` is left behind. A converter
that fails or times out (300 s) fails that file only; its own messages are never printed.
An old file whose newer copy sits next to it (`deck.ppt` and `deck.pptx`) is skipped in
favour of the copy. Without a converter, old files are skipped with an install hint. `x2t`
is OnlyOffice's internal converter, not a documented command: a new OnlyOffice version
could change it (the tool checks its exit status and its output). A Markdown file newer than its source is not converted again (`up to date`)
unless `--reconvert`, but is still uploaded; other `.md` files found are uploaded `as is`.
The run refuses to start when two sources would write the same file (`a.pdf` and `a.docx`)
or two Markdown files share a name (`x/a.md` and `y/a.md` would replace each other in the
knowledge base). A file that fails to convert (or comes out without text) is not uploaded;
a file the API refuses (`413`, `422`, `502`) is reported; the run goes on. A wrong key,
a URL without the endpoint or an unreachable API stops the run.

docling takes from seconds to minutes per document on a CPU (layout, tables and OCR for
every page), so each conversion prints a `converting (n/N)` line when it starts; every line
is flushed, so progress also shows through `| tee`. `--verbose` (`-v`) adds docling's info
logs. Its OCR may warn `RapidOCR returned empty result` for pages or pictures without text:
harmless.

```text
skipped     docs/archive.zip (unsupported: .zip)
uploading to http://127.0.0.1:8000, tenant acme
converting  (1/2) docs/manual.pdf …
converted   docs/manual.pdf -> docs/manual.md
indexed     docs/manual.md (upload-1890b5dc5335, 12 chunks)
up to date  docs/pro-014.md
unchanged   docs/pro-014.md (upload-4be0c2a91d7f, already indexed)
converting  (2/2) docs/scan.png …
failed      docs/scan.png (EmptyMarkdownError: no text extracted)
3 documents: 1 converted, 1 up to date, 1 failed; uploaded: 1 indexed, 1 unchanged; 1 skipped
```

Exit status: `0` all done, `1` some file failed, `2` the run could not start or was
stopped. It prints paths, statuses and error types only, never document content.

## Uploading a document

```sh
curl -H "X-API-Key: $ADMIN_API_KEY" \
  -F file=@tests/fixtures/pro-014-control-sellado.md \
  -F tenant=acme \
  http://127.0.0.1:8000/admin/documents
```

```json
{"doc_id": "upload-…", "status": "indexed", "chunk_count": 5, "embedding_model": "voyage-4", "embed_signature": "17047d562b7e…"}
```

That's `201`. Sending the same file again gives `200` and `{"doc_id": "upload-…", "status": "up_to_date"}`,
without calling Voyage. Changing the file, or the chunking or embedding settings,
reindexes it. `-F force=true` reindexes anyway. Optional fields: `title`, and `source_key`
(identifies the document within the tenant; the file name by default).

Errors all have one shape, told apart by `type`:

```json
{"detail": [{"type": "file_empty", "loc": ["body", "file"], "msg": "file is empty"}]}
```

## Reading documents

A document is addressed by the `doc_id` that the upload and the listing return.

```sh
H="X-API-Key: $ADMIN_API_KEY"
API=http://127.0.0.1:8000/admin/documents

curl -H "$H" "$API?tenant=acme&q=sellado&sort=-updated_at&limit=25&offset=0"  # list
curl -H "$H" "$API?status=outdated"                                         # outdated ones
curl -H "$H" "$API/upload-1890b5dc5335"                                      # one document
curl -H "$H" "$API/upload-1890b5dc5335/content"                              # its Markdown
curl -H "$H" "$API/upload-1890b5dc5335/chunks?limit=50&offset=0"             # its chunks
```

- **List**: a page `{"items": [...], "total": N, "limit": N, "offset": N}`. Filters:
  `tenant`, `q` (case-insensitive substring of the title or the source key), `status`
  (`indexed` or `outdated` against the current settings: the documents
  `GET /admin/settings` counts as outdated, whatever the reason). `sort` is
  one of `updated_at`, `created_at`, `title`, `chunk_count`, with `-` for descending
  (default `-updated_at`). `limit` is 1 to 100 (default 25).
- **One document**: the same object as a list item. `status` is `indexed`, or `outdated`
  when the chunking or embedding settings changed since it was indexed (`outdated_reason`
  says which).
- **Content**: the stored Markdown as `text/markdown; charset=utf-8`, after normalization
  (no BOM, LF line endings).
- **Chunks**: a page of `{chunk_index, heading, chunk_text, char_count, embedding}` in
  order. `limit` is 1 to 200 (default 50). `embedding` is null unless
  `include_embedding=true`, which is heavy (one float per dimension, per chunk).

An unknown `doc_id` gives `404` (`document_not_found`); a malformed one gives `422`.

## Renaming a document

```sh
curl -X PATCH -H "$H" -H "Content-Type: application/json" \
  -d '{"title": "PRO-014 Control de sellado (rev. 3)"}' \
  "$API/upload-1890b5dc5335"
```

Returns the renamed document. Only `title` (trimmed, 1 to 200 characters) and
`updated_at` change; nothing is re-chunked or re-embedded, and renaming to the current
title changes nothing. Any other field in the body is a `422`.

## Replacing a document

Upload the new file with the document's `tenant` and `source_key` (both are in every
listed item); the `doc_id` stays the same:

```sh
curl -H "$H" -F file=@pro-014-v2.md -F tenant=acme \
  -F source_key=pro-014-control-sellado.md -F "title=PRO-014 Control de sellado (rev. 3)" \
  "$API"
```

Changed content answers `201` with `indexed`; identical content `200` with `up_to_date`.
The upload sets the title again (the `title` field, else the first `# ` heading, else the
file name), so send `title` to keep a rename.

## Reprocessing a document

After changing the chunking or embedding settings (`CHUNK_SIZE`, `EMBEDDING_MODEL`, ...),
documents indexed before show `"status": "outdated"`; `GET /admin/documents?status=outdated`
lists them. Reprocess one from its stored Markdown, without uploading it again:

```sh
curl -X POST -H "$H" "$API/upload-1890b5dc5335/reprocess"
```

The answer has the upload's shape, always with `200`: `indexed` (re-chunked and
re-embedded) or `up_to_date` (nothing to do, no Voyage call). `?force=true` reprocesses
anyway. The title, the Markdown and `updated_at` are kept. A document indexed before its
settings were recorded (`outdated_reason: unknown`) but still matching them just gets
them recorded. `409 document_changed` means a newer upload replaced the document
meanwhile (nothing was written); `502` means Voyage failed (nothing was written either).

Changing `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MIN_CHUNK_SIZE`, `EMBEDDING_MODEL` or
`EMBEDDING_DIMENSIONS` changes the document signatures, so the next upload of each
document reprocesses it. So does switching `EMBEDDING_PROVIDER`: the fake embedder's
vectors are labelled `fake/document/<dimensions>` (`embedder_config`), whatever the model,
so they never pass for a real model's.

## Deleting a document

```sh
curl -X DELETE -H "$H" "$API/upload-1890b5dc5335"   # 204, no body
```

Removes the document and its chunks for good (no undo, no audit table yet: the only trace
is a log line with `doc_id`, tenant and chunk count). A second delete answers `404`.
Uploading the same file name for the same tenant afterwards creates a new document with
the same `doc_id`.

## Deleting several documents

```sh
curl -H "$H" -H "Content-Type: application/json" \
  -d '{"doc_ids": ["upload-1890b5dc5335", "upload-4be0c2a91d7f"]}' "$API/delete"
# {"deleted": [{"doc_id": "upload-1890b5dc5335", "tenant": "acme", "chunk_count": 12}],
#  "not_found": ["upload-4be0c2a91d7f"]}
```

1 to 100 distinct ids, deleted with their chunks in one transaction (all or none). Ids with
no document come back in `not_found`, not as an error, so repeating the request is safe.
A `POST` rather than `DELETE`, since proxies may drop a body on `DELETE`. Each deleted
document gets the same log line as a single delete.

## Tenants

```sh
curl -H "$H" "http://127.0.0.1:8000/admin/tenants"
# [{"tenant": "acme", "document_count": 4, "chunk_count": 57}]
```

Every tenant with stored documents, ordered by tenant, with its document and chunk counts
(for a tenant filter). Not paginated; a tenant whose last document is deleted disappears.

## Indexing settings

```sh
curl -H "$H" "http://127.0.0.1:8000/admin/settings"
# {"chunking": {"chunker_version": "md-header+recursive@v3", "chunk_size": 800, ...,
#   "chunker_config": "md-header+recursive@v3/size=800/..."},
#  "embedding": {"provider": "voyage", "model": "voyage-4", "dimensions": 1024,
#   "batch_size": 128, "embedder_config": "voyage-4/document/1024"},
#  "uploads": {"max_upload_bytes": 5242880},
#  "copilot": {"configured": true, "model": "mistralai/...", "summary_model": "mistralai/...",
#   "summary_model_source": "llm_model", "prompts_version": "draft-1", ...},
#  "documents": {"total": 12, "indexed": 9,
#   "outdated": {"unknown": 0, "chunker_changed": 2, "embedder_changed": 1}}}
```

Read-only: the chunking, embedding and upload settings new uploads and reprocesses use
(from the environment; no keys, URLs or database settings), and how many documents across
all tenants are `indexed` with them or `outdated`, by the same reasons as each document's
`outdated_reason`. The two config strings are the ones documents are compared with.
`copilot` names the conversation model, the model a new case summary uses
(`summary_model`: `SUMMARY_MODEL`, else `LLM_MODEL`, which `summary_model_source` says),
both prompt versions, `SUMMARY_MAX_TOKENS`, and whether a provider key is set
(`configured`; the key itself never). The test chat names the summary model from it before
a billed summary call.

## Chunking

Markdown is split by `#`, `##` and `###` headings (`MarkdownHeaderTextSplitter`), and
long sections are then split by characters (`RecursiveCharacterTextSplitter`). Each chunk
keeps its heading path, e.g. `PRO-014 Control de sellado > 3. Pasos`.

Small chunks are merged, never silently discarded, because a short chunk can be the
critical one (for example "Temperatura máxima: 180 °C"). The rules, in order:

1. No content at all (every line is blank, a separator such as `---`, or a page number):
   dropped. A file left with no chunks at all is rejected (`422`, "no indexable content").
2. Shorter than `MIN_CHUNK_SIZE` and followed by a chunk of the same section (same
   heading path or a subsection of it): merged forward into it. This covers lead-ins
   like "Los pasos son:".
3. Shorter than `MIN_CHUNK_SIZE` and last in its section: merged backward into the
   previous chunk of the same section, as long as the result stays within
   1.5 × `CHUNK_SIZE`.
4. Otherwise kept as its own chunk.

Chunks are never merged across unrelated sections.
