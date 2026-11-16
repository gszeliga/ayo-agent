# Knowledge base: documents

How to load and manage the Markdown documents the copilot searches: upload, read,
rename, replace, reprocess, delete, and how they are chunked. Searching them is in
[search.md](search.md). Every route here needs the `X-API-Key` header (see [Endpoints](../README.md#endpoints));
`/docs` has every field, status and error `type`.

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
document reprocesses it.

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
#  "documents": {"total": 12, "indexed": 9,
#   "outdated": {"unknown": 0, "chunker_changed": 2, "embedder_changed": 1}}}
```

Read-only: the chunking, embedding and upload settings new uploads and reprocesses use
(from the environment; no keys, URLs or database settings), and how many documents across
all tenants are `indexed` with them or `outdated`, by the same reasons as each document's
`outdated_reason`. The two config strings are the ones documents are compared with.

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
