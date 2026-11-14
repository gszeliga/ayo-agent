// Generated from docs/openapi.json by `pnpm gen:api` (openapi-typescript). Do not edit.

export interface paths {
    "/admin/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List documents
         * @description List the stored documents, one page at a time, newest change first.
         *
         *     Filter by `tenant`, by `q`, a case-insensitive substring of the title or the source key
         *     (`%` and `_` match themselves), and by `status`. `total` counts every match, so a client
         *     can page with `offset` until it has `total` items; the order is stable across pages, even
         *     on ties.
         *
         *     Each item carries a `status` computed now against the current settings: `outdated` means
         *     the chunking or embedding settings changed since the document was indexed (or were never
         *     recorded). `status=outdated` lists exactly the documents that `GET /admin/settings` counts
         *     as outdated, whatever their `outdated_reason`.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | A page, possibly empty. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `422` | A query parameter is out of range or not allowed (FastAPI validation). |
         */
        get: operations["list_documents"];
        put?: never;
        /**
         * Upload a Markdown document
         * @description Index one Markdown file for a tenant, so the copilot can retrieve it.
         *
         *     The file is split into chunks along its headings (each chunk keeps its heading path),
         *     each chunk is embedded, and the document, its Markdown and its chunks are stored in one
         *     transaction. A document is identified by `tenant` + `source_key` (by default the file
         *     name): uploading it again replaces its previous version.
         *
         *     **Idempotent.** If the content and the chunking and embedding settings are the same as
         *     the stored version, nothing is done and the answer is `200 up_to_date`, without calling
         *     the embedding provider. Send `force=true` to reindex anyway.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `201` | Indexed (new document, or a changed one). |
         *     | `200` | Already up to date: nothing was done. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `413` | The file is larger than `MAX_UPLOAD_BYTES` (default 5 MiB). |
         *     | `422` | Not a `.md` file, not UTF-8, empty, nothing to index, or an invalid field. |
         *     | `502` | The embedding provider failed after retries. Nothing was stored. |
         *
         *     Errors use the API's error format (see the API description) and are told apart by
         *     `detail[].type`.
         */
        post: operations["upload_document"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/documents/delete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Delete several documents
         * @description Delete up to 100 documents and their chunks at
         *     once, permanently, in one transaction: all of them or, on a failure, none. A `POST`, since
         *     a body on `DELETE` may be dropped by proxies.
         *
         *     An id with no document (never stored, or already deleted) is listed in `not_found`; that
         *     is not an error, so repeating a request is safe. Uploads and reprocesses in progress behave
         *     as with the single delete.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | Done: what was deleted and what was not found, in the request's order. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `422` | Not 1 to 100 distinct, well-formed ids (FastAPI validation). |
         */
        post: operations["delete_documents"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/documents/{doc_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get a document
         * @description One document, with the same fields as an item of the listing.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The document. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No document has this `doc_id`. |
         *     | `422` | `doc_id` is malformed (FastAPI validation). |
         */
        get: operations["get_document"];
        put?: never;
        post?: never;
        /**
         * Delete a document
         * @description Delete a document and its chunks, permanently: there is no undo and
         *     no trash. The answer has no body.
         *
         *     Uploading a file with the same `tenant` and file name afterwards creates a new document,
         *     with the same `doc_id` but new timestamps. An upload of it still in progress when the delete
         *     commits creates it again; a reprocess in progress answers `404`.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `204` | Deleted. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No document has this `doc_id` (or it was already deleted). |
         *     | `422` | `doc_id` is malformed (FastAPI validation). |
         */
        delete: operations["delete_document"];
        options?: never;
        head?: never;
        /**
         * Rename a document
         * @description Rename a document. Only `title` and `updated_at` change: the content,
         *     chunks, signatures and embeddings stay as they are, and the embedding provider is not
         *     called. Renaming to the current title changes nothing, not even `updated_at`.
         *
         *     A later upload of the same `tenant` and `source_key` sets the title again (the `title`
         *     field, else the first `# ` heading, else the file name), so send `title` with it to keep a
         *     rename.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The document, renamed. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No document has this `doc_id`. |
         *     | `422` | `doc_id` is malformed, or the body is not a valid update (FastAPI validation). |
         */
        patch: operations["update_document"];
        trace?: never;
    };
    "/admin/documents/{doc_id}/chunks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List a document's chunks
         * @description The document's chunks in order, one page at a time: how the chunker
         *     split it, and what the embeddings were computed from.
         *
         *     `total` is the document's `chunk_count`. Vectors are left out (`embedding` is null) unless
         *     `include_embedding=true`: each one is a float per dimension (1024 with the default model),
         *     so a full page with vectors is several megabytes of JSON.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | A page of chunks, possibly empty. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No document has this `doc_id`. |
         *     | `422` | `doc_id` is malformed or a query parameter is out of range (FastAPI validation). |
         */
        get: operations["list_document_chunks"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/documents/{doc_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get a document's Markdown
         * @description The stored Markdown, as `text/markdown; charset=utf-8`.
         *
         *     It is the uploaded file after normalization (no byte order mark, LF line endings), so its
         *     SHA-256 is the document's `content_hash`. Errors are JSON, like everywhere else.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The Markdown. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No document has this `doc_id`. |
         *     | `422` | `doc_id` is malformed (FastAPI validation). |
         */
        get: operations["get_document_content"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/documents/{doc_id}/reprocess": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reprocess a document
         * @description Re-chunk and re-embed a document from its stored Markdown, with the
         *     current chunking and embedding settings: the way to bring an `outdated` document back to
         *     `indexed` without uploading it again. The title, the Markdown and `updated_at` are kept;
         *     `chunked_at` and `embedded_at` record the reprocess.
         *
         *     A document that is already up to date is not reprocessed (`up_to_date`, no call to the
         *     embedding provider) unless `force=true`. One indexed before its settings were recorded
         *     (`outdated_reason: unknown`) but processed exactly as the current settings would, gets
         *     them recorded and becomes `indexed`, also without a provider call.
         *
         *     The provider is called before anything is written. If a newer upload replaces the
         *     document meanwhile, the reprocess writes nothing and answers `409`; if the document is
         *     deleted meanwhile, `404`.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | Reprocessed (`indexed`) or nothing to do (`up_to_date`). |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No document has this `doc_id`. |
         *     | `409` | A newer upload replaced the document meanwhile; nothing was written. |
         *     | `422` | `doc_id` is malformed or `force` is not a boolean (FastAPI validation). |
         *     | `502` | The embedding provider failed; nothing was written. |
         */
        post: operations["reprocess_document"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Check the database and the embedding provider
         * @description Whether the database and the embedding provider work, for a
         *     status display. Always `200` when the report could be made: a service that is down is
         *     reported in the body (`status: degraded`), not as an error. The public `/health` only
         *     says the process is up and never fails because of these services.
         *
         *     - **Database:** one query through the connection pool, on every request, within 2 s. It
         *       reports the PostgreSQL and pgvector versions, and where the database runs as a category
         *       (`local`, `neon` or `remote`).
         *     - **Embeddings:** one request embedding a single short word, within 5 s and without
         *       retries. The result, a failure included, is kept for 60 s, so loading a page doesn't
         *       call the provider each time; `refresh=true` checks again. Nothing is checked in the
         *       background. Also reported: when the last real embedding call (by an upload or a
         *       reprocess) succeeded and failed since the service started.
         *
         *     No keys, URLs or hosts are included.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The report, with each service `up` or `down`. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `422` | `refresh` is not a boolean (FastAPI validation). |
         */
        get: operations["get_service_health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Search the knowledge base
         * @description Find the chunks nearest to a question: what the copilot would
         *     retrieve for it. For trying questions against the knowledge base and evaluating
         *     retrieval; the answer has everything a result list needs, without further calls.
         *
         *     The query is embedded as a search query, then compared by cosine similarity with every
         *     chunk that passes the filters (exact search, no approximate index; see ADR 0002).
         *     Results are ordered by similarity, highest first, ties by chunk id, so the same request
         *     on the same data gives the same answer.
         *
         *     **Embedding models.** Vectors from different embedding models are not comparable.
         *     Documents embedded with another model than the current one (or an unknown one) are
         *     skipped and counted in `skipped.embedder_mismatch`; reprocess them to search them again.
         *     With `include_outdated=true` they are searched and flagged with `embedder_outdated`. A
         *     change of the chunking settings alone never skips a document.
         *
         *     **Tenants.** The production agent will always search one customer's tenant plus the
         *     shared `ayo` tenant, never across customers. `tenants=null` searches every tenant, for
         *     administrators only.
         *
         *     The results hold customer content, and queries can be sensitive too: neither is logged.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The results, possibly none (empty knowledge base, filters matching nothing). |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `422` | An invalid field: see the codes below. |
         *     | `502` | The embedding provider failed after retries. Nothing was searched. |
         */
        post: operations["search_documents"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get the indexing settings
         * @description The chunking, embedding and upload settings that new uploads and
         *     reprocesses use, and how many stored documents, across all tenants, are `indexed` with
         *     them or `outdated` (by reason, as each document's `outdated_reason`). Read-only: the
         *     settings come from the environment and change with a restart. No keys, URLs or database
         *     settings are included.
         *
         *     The `chunker_config` and `embedder_config` strings are the ones each document is compared
         *     with, so a client can show which part of a document's configs differs.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The settings and the counts. |
         *     | `401` | `X-API-Key` missing or wrong. |
         */
        get: operations["get_settings"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List tenants
         * @description Every tenant that has stored documents, in alphabetical order, with
         *     how many documents and chunks it has: the values for a tenant filter. A tenant whose last
         *     document is deleted is no longer listed. Not paginated.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The tenants, possibly none. |
         *     | `401` | `X-API-Key` missing or wrong. |
         */
        get: operations["list_tenants"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/copilot/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send a message to the copilot
         * @description Send one message of a session and get the copilot's reply.
         *
         *     The copilot guides a plant team through five phases: **understand** the problem (what,
         *     where, since when, the standard), **challenge** it with evidence, **analyse** the cause,
         *     agree **actions**, then **follow up** until the case is closed. Code checks each phase's
         *     exit criteria; the reply opens the next phase as soon as they are met.
         *
         *     The first message of a `session_id` opens a case for its `tenant`; the following ones
         *     continue it. A turn is atomic: if it fails (`409`, `502`, `503`), nothing of it is stored
         *     and the message can simply be sent again. A knowledge-base failure does not fail the
         *     turn: the copilot says it could not consult it.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The reply, the phase after the turn and the tools used. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `409` | `case_closed`, or `case_changed` (another turn won; send it again). |
         *     | `422` | Body not acceptable, text too long, or `tenant_mismatch`. |
         *     | `502` | The language model failed (`llm_*`, see below). |
         *     | `503` | `llm_not_configured`: no language model key. |
         */
        post: operations["send_copilot_message"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/copilot/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get a copilot session
         * @description A session's case as it is stored: phase, the four facts, the
         *     annotations, the actions and the conversation. For inspection while testing; it never
         *     returns system prompts, traces or retrieved text.
         *
         *     | Status | Meaning |
         *     |---|---|
         *     | `200` | The session. |
         *     | `401` | `X-API-Key` missing or wrong. |
         *     | `404` | No message was ever sent with this `session_id`. |
         *     | `422` | `session_id` is not a UUID (FastAPI validation). |
         */
        get: operations["get_copilot_session"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Check that the service is up
         * @description Answers as soon as the process serves requests. It does not check the database or the embedding provider.
         */
        get: operations["health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** Body_upload_document */
        Body_upload_document: {
            /**
             * File
             * @description The Markdown file (`.md`, UTF-8).
             */
            file: string;
            /**
             * Force
             * @description Reindex even when the stored version is up to date.
             * @default false
             */
            force: boolean;
            /**
             * Source Key
             * @description Name that identifies the document within the tenant; an upload with the same one replaces it. Paths are reduced to their last component. Default: the file name.
             * @example pro-014-control-sellado.md
             */
            source_key?: string | null;
            /**
             * Tenant
             * @description Tenant (plant or customer) the document belongs to: lowercase letters, digits and hyphens, 2 to 63 characters.
             * @example acme
             */
            tenant: string;
            /**
             * Title
             * @description Title to store. Default: the first `# ` heading, else the file name.
             * @example PRO-014 Control de sellado
             */
            title?: string | null;
        };
        /**
         * Chunk
         * @description One stored chunk of a document.
         */
        Chunk: {
            /**
             * Char Count
             * @description Length of `chunk_text` in characters (not bytes).
             * @example 86
             */
            char_count: number;
            /**
             * Chunk Index
             * @description Position of the chunk in the document, from 0.
             * @example 2
             */
            chunk_index: number;
            /**
             * Chunk Text
             * @description The chunk's text. The text that was embedded is `heading`, a blank line and this text (only this text when `heading` is null).
             * @example Comprobar la presión de la junta antes de cada turno y anotar el valor en el registro.
             */
            chunk_text: string;
            /**
             * Embedding
             * @description The stored vector, one float per dimension of the embedding model. Null unless `include_embedding=true`.
             * @example null
             */
            embedding: number[] | null;
            /**
             * Heading
             * @description Path of the Markdown headings the chunk sits under, joined with ` > `; null before the first heading.
             * @example PRO-014 Control de sellado > 3. Pasos
             */
            heading: string | null;
        };
        /**
         * ChunkPage
         * @description A page of a document's chunks.
         */
        ChunkPage: {
            /**
             * Items
             * @description The items of this page, possibly empty.
             */
            items: components["schemas"]["Chunk"][];
            /**
             * Limit
             * @description Page size requested.
             * @example 50
             */
            limit: number;
            /**
             * Offset
             * @description Number of matching items skipped.
             * @example 0
             */
            offset: number;
            /**
             * Total
             * @description Number of items matching the filters, across all pages.
             * @example 42
             */
            total: number;
        };
        /**
         * ChunkingSettings
         * @description How new uploads and reprocesses are chunked.
         */
        ChunkingSettings: {
            /**
             * Chunk Overlap
             * @description Characters shared by consecutive chunks of a split section (`CHUNK_OVERLAP`).
             * @example 80
             */
            chunk_overlap: number;
            /**
             * Chunk Size
             * @description Target chunk size in characters (`CHUNK_SIZE`).
             * @example 800
             */
            chunk_size: number;
            /**
             * Chunker Config
             * @description All of the above as one string: a document whose `chunker_config` differs is outdated (`chunker_changed`).
             * @example md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1
             */
            chunker_config: string;
            /**
             * Chunker Version
             * @description Version of the chunking algorithm and of the embedded text format.
             * @example md-header+recursive@v3
             */
            chunker_version: string;
            /**
             * Min Chunk Size
             * @description Chunks shorter than this are merged into a neighbour (`MIN_CHUNK_SIZE`).
             * @example 100
             */
            min_chunk_size: number;
        };
        /**
         * CopilotMessageRequest
         * @description One message from the plant team to the copilot.
         * @example {
         *       "session_id": "3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14",
         *       "tenant": "cliente-acme",
         *       "text": "Tenemos un 4 % de merma en la llenadora de la línea 2.",
         *       "user_id": "operario-17"
         *     }
         */
        CopilotMessageRequest: {
            /**
             * Session Id
             * Format: uuid
             * @description The conversation, generated by the client (a UUID). The first message of a session opens a case; the next ones continue it.
             * @example 3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14
             */
            session_id: string;
            /**
             * Tenant
             * @description The customer. A session belongs to the tenant of its first message; another tenant gets `422 tenant_mismatch`.
             * @example cliente-acme
             */
            tenant: string;
            /**
             * Text
             * @description The message. Surrounding whitespace is removed; 1 to `MAX_USER_MESSAGE_CHARS` (default 4000) characters remain. Never logged.
             * @example Tenemos un 4 % de merma en la llenadora de la línea 2.
             */
            text: string;
            /**
             * User Id
             * @description Who writes, 1 to 200 characters; optional. Recorded as the case's creator on the first message.
             * @example operario-17
             */
            user_id?: string | null;
        };
        /**
         * CopilotMessageResponse
         * @description The copilot's reply and where the case stands after the turn.
         * @example {
         *       "phase": "challenge",
         *       "phase_changed": true,
         *       "previous_phase": "understand",
         *       "reply": "Entendido. ¿Qué datos tenéis de la llenadora desde el lunes?",
         *       "session_id": "3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14",
         *       "tools_used": [
         *         {
         *           "name": "record_field",
         *           "ok": true
         *         },
         *         {
         *           "name": "propose_transition",
         *           "ok": true
         *         }
         *       ],
         *       "turn": 3
         *     }
         */
        CopilotMessageResponse: {
            /**
             * Phase
             * @description The phase after the turn: `understand` (the four facts), `challenge` (evidence), `analyse` (the cause), `action` (actions with owner and date), `followup` (tracking them) or `closed`.
             * @example challenge
             * @enum {string}
             */
            phase: "understand" | "challenge" | "analyse" | "action" | "followup" | "closed";
            /**
             * Phase Changed
             * @description Whether the turn moved the case to another phase.
             * @example true
             */
            phase_changed: boolean;
            /**
             * Previous Phase
             * @description The phase before the turn.
             * @example understand
             * @enum {string}
             */
            previous_phase: "understand" | "challenge" | "analyse" | "action" | "followup" | "closed";
            /**
             * Reply
             * @description The copilot's answer, in Spanish. When a phase changed, it already opens the new phase.
             * @example Entendido. ¿Qué datos tenéis de la llenadora desde el lunes?
             */
            reply: string;
            /**
             * Session Id
             * Format: uuid
             * @description The session, as sent.
             * @example 3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14
             */
            session_id: string;
            /**
             * Tools Used
             * @description The tool calls of the turn, in order; empty when the copilot only wrote.
             */
            tools_used: components["schemas"]["ToolUse"][];
            /**
             * Turn
             * @description The turn's number in the case, from 1.
             * @example 3
             */
            turn: number;
        };
        /**
         * CopilotSession
         * @description A session's case, for inspection while testing. No prompts, traces or retrieved
         *     text.
         */
        CopilotSession: {
            /**
             * Actions
             * @description The actions, oldest first.
             */
            actions: components["schemas"]["CopilotSessionAction"][];
            /**
             * Events
             * @description The annotations, oldest first.
             */
            events: components["schemas"]["CopilotSessionEvent"][];
            /** @description The four facts. */
            fields: components["schemas"]["CopilotSessionFields"];
            /**
             * Messages
             * @description The conversation, oldest first.
             */
            messages: components["schemas"]["CopilotSessionMessage"][];
            /**
             * Phase
             * @description The current phase: `understand` (the four facts), `challenge` (evidence), `analyse` (the cause), `action` (actions with owner and date), `followup` (tracking them) or `closed`.
             * @example analyse
             * @enum {string}
             */
            phase: "understand" | "challenge" | "analyse" | "action" | "followup" | "closed";
            /**
             * Session Id
             * Format: uuid
             * @description The session.
             * @example 3f1c2a9e-7b4d-4e8a-9c61-0d5b2f7a8e14
             */
            session_id: string;
            /**
             * Tenant
             * @description The case's tenant.
             * @example cliente-acme
             */
            tenant: string;
            /**
             * Turns
             * @description Committed turns.
             * @example 4
             */
            turns: number;
            /**
             * Version
             * @description Bumped by every committed turn.
             * @example 7
             */
            version: number;
        };
        /**
         * CopilotSessionAction
         * @description An agreed action.
         */
        CopilotSessionAction: {
            /**
             * Description
             * @description What to do.
             * @example Recalibrar el sensor de nivel de la llenadora
             */
            description: string;
            /**
             * Due Date
             * Format: date
             * @description By when.
             * @example 2026-11-20
             */
            due_date: string;
            /**
             * Id
             * @description The action's id.
             * @example 3
             */
            id: number;
            /**
             * Overdue
             * @description Pending and past its due date, in `APP_TIMEZONE` (computed, not stored).
             * @example false
             */
            overdue: boolean;
            /**
             * Owner
             * @description Who does it.
             * @example Ana (mantenimiento)
             */
            owner: string;
            /**
             * Status
             * @description `pending` or `done`.
             * @example pending
             * @enum {string}
             */
            status: "pending" | "done";
        };
        /**
         * CopilotSessionEvent
         * @description An annotation the copilot recorded: evidence, a hypothesis, a discarded hypothesis or
         *     the validated cause.
         */
        CopilotSessionEvent: {
            /**
             * Content
             * @description The annotation, as recorded.
             * @example El sensor de nivel marca 3 mm de más desde el cambio de formato
             */
            content: string;
            /**
             * Created At
             * Format: date-time
             * @description When it was recorded (UTC).
             * @example 2026-11-12T09:31:04Z
             */
            created_at: string;
            /**
             * Event Type
             * @description What kind of annotation it is.
             * @example evidence
             * @enum {string}
             */
            event_type: "evidence" | "hypothesis" | "hypothesis_discarded" | "validated_cause";
            /**
             * Id
             * @description The annotation's id, in recording order.
             * @example 12
             */
            id: number;
            /**
             * State At Time
             * @description The phase it was recorded in.
             * @example challenge
             * @enum {string}
             */
            state_at_time: "understand" | "challenge" | "analyse" | "action" | "followup" | "closed";
        };
        /**
         * CopilotSessionFields
         * @description The four facts of the problem; null until recorded.
         */
        CopilotSessionFields: {
            /**
             * Since
             * @description Since when.
             * @example Desde el lunes 9
             */
            since: string | null;
            /**
             * Standard
             * @description What should happen instead (the standard).
             * @example Merma máxima del 1,5 %
             */
            standard: string | null;
            /**
             * What
             * @description What happens.
             * @example Merma del 4 % en el envasado
             */
            what: string | null;
            /**
             * Where
             * @description Where it happens.
             * @example Línea 2, llenadora
             */
            where: string | null;
        };
        /**
         * CopilotSessionMessage
         * @description One message of the conversation.
         */
        CopilotSessionMessage: {
            /**
             * Content
             * @description The message.
             * @example Tenemos un 4 % de merma en la llenadora de la línea 2.
             */
            content: string;
            /**
             * Created At
             * Format: date-time
             * @description When it was stored (UTC).
             * @example 2026-11-12T09:30:58Z
             */
            created_at: string;
            /**
             * Role
             * @description `user` (the plant team) or `assistant` (the copilot).
             * @example user
             * @enum {string}
             */
            role: "user" | "assistant";
            /**
             * State At Time
             * @description The phase when it was sent: a user message carries the phase its turn started in, a reply the phase it ended in.
             * @example understand
             * @enum {string}
             */
            state_at_time: "understand" | "challenge" | "analyse" | "action" | "followup" | "closed";
        };
        /**
         * DatabaseHealth
         * @description One query through the connection pool, run on every request. Where the database
         *     runs is given as a category only: never its host or URL.
         */
        DatabaseHealth: {
            /**
             * Error
             * @description `timeout` (no answer, or no free connection, within 2 s) or `connection failed`; null when up.
             * @example timeout
             */
            error: string | null;
            /**
             * Latency Ms
             * @description How long the check took, waiting for a connection included.
             * @example 4
             */
            latency_ms: number;
            /**
             * Location
             * @description Where it runs, from `DATABASE_URL`: `local` (localhost or a Unix socket), `neon` (a `*.neon.tech` host, pooled or direct) or `remote` (any other host). Known even when it is down.
             * @example neon
             * @enum {string}
             */
            location: "local" | "neon" | "remote";
            /**
             * Pgvector Version
             * @description Version of the `vector` extension; null when down or not installed.
             * @example 0.8.1
             */
            pgvector_version: string | null;
            /**
             * Postgres Version
             * @description PostgreSQL server version, its number only; null when down.
             * @example 18.1
             */
            postgres_version: string | null;
            /**
             * Status
             * @description `up` if the query answered in time.
             * @example up
             * @enum {string}
             */
            status: "up" | "down";
        };
        /**
         * DeletedDocument
         * @description A document that was deleted, with its chunks.
         */
        DeletedDocument: {
            /**
             * Chunk Count
             * @description Chunks deleted with it.
             * @example 12
             */
            chunk_count: number;
            /**
             * Doc Id
             * @description Id of the deleted document.
             * @example upload-1890b5dc5335
             */
            doc_id: string;
            /**
             * Tenant
             * @description Tenant it belonged to.
             * @example acme
             */
            tenant: string;
        };
        /**
         * Document
         * @description A stored document, the same in the listing and on its own. `status` compares it with
         *     the current settings.
         */
        Document: {
            /**
             * Chunk Count
             * @description Number of stored chunks.
             * @example 12
             */
            chunk_count: number;
            /**
             * Chunk Signature
             * @description Hash of the content and `chunker_config`.
             * @example 4e1b9c0d7a2f5e8b3c6d9a0f1e4b7c2d5a8f3e6b9c0d1a4f7e2b5c8d3a6f9e0b
             */
            chunk_signature: string;
            /**
             * Chunked At
             * @description When the current chunks were made (UTC).
             * @example 2026-10-15T09:30:01Z
             */
            chunked_at: string | null;
            /**
             * Chunker Config
             * @description Chunking settings the document was processed with (null if indexed before they were recorded).
             * @example md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1
             */
            chunker_config: string | null;
            /**
             * Content Hash
             * @description SHA-256 (hex) of the stored Markdown; equal hashes mean equal content.
             * @example 9f2c1a7e5b0d4c3a8e6f1b2d7c9a0e4f3b5d8c1a2e7f6b9d0c4a3e8f5b1d2c7a
             */
            content_hash: string;
            /**
             * Created At
             * Format: date-time
             * @description First upload (UTC).
             * @example 2026-10-15T09:30:00Z
             */
            created_at: string;
            /**
             * Doc Id
             * @description Stable id of the document, derived from the tenant and the source key.
             * @example upload-1890b5dc5335
             */
            doc_id: string;
            /**
             * Embed Signature
             * @description Hash of `chunk_signature` and `embedder_config`. An upload whose signature equals it is `up_to_date`.
             * @example 17047d562b7e9a3c0f5d8b1e4a7c2f6d9b0e3a8c5f1d4b7e2a9c6f0d3b8e5a1c
             */
            embed_signature: string;
            /**
             * Embedded At
             * @description When the current chunks were embedded (UTC).
             * @example 2026-10-15T09:30:04Z
             */
            embedded_at: string | null;
            /**
             * Embedder Config
             * @description Embedding model and dimensions the document was processed with (null if indexed before they were recorded).
             * @example voyage-4/document/1024
             */
            embedder_config: string | null;
            /**
             * Outdated Reason
             * @description Why it is `outdated` (null when `indexed`): the chunking settings changed, the embedding model changed, or `unknown` (indexed before the settings were recorded). The chunker wins when both changed.
             * @example null
             */
            outdated_reason: ("chunker_changed" | "embedder_changed" | "unknown") | null;
            /**
             * Size Bytes
             * @description Size of the stored Markdown in bytes (UTF-8, after normalization).
             * @example 8421
             */
            size_bytes: number | null;
            /**
             * Source Key
             * @description Name that identifies the document within the tenant. Uploading with the same `tenant` and `source_key` replaces it.
             * @example pro-014-control-sellado.md
             */
            source_key: string;
            /**
             * Status
             * @description `indexed`: processed with the current chunking and embedding settings. `outdated`: the current settings would index it differently; reprocess or upload it again.
             * @example indexed
             * @enum {string}
             */
            status: "indexed" | "outdated";
            /**
             * Tenant
             * @description Tenant the document belongs to.
             * @example acme
             */
            tenant: string;
            /**
             * Title
             * @description Display title: given at upload, else the first `# ` heading, else the file name.
             * @example PRO-014 Control de sellado
             */
            title: string | null;
            /**
             * Updated At
             * Format: date-time
             * @description Last change: upload or rename (UTC).
             * @example 2026-10-15T09:30:00Z
             */
            updated_at: string;
        };
        /**
         * DocumentDeleteRequest
         * @description The documents to delete at once.
         */
        DocumentDeleteRequest: {
            /**
             * Doc Ids
             * @description Ids of the documents to delete: 1 to 100, no repeats.
             * @example [
             *       "upload-1890b5dc5335",
             *       "upload-4be0c2a91d7f"
             *     ]
             */
            doc_ids: string[];
        };
        /**
         * DocumentDeleteResult
         * @description What a bulk delete did. Both lists keep the order of the request.
         */
        DocumentDeleteResult: {
            /**
             * Deleted
             * @description The documents deleted, with their chunks.
             * @example [
             *       {
             *         "chunk_count": 12,
             *         "doc_id": "upload-1890b5dc5335",
             *         "tenant": "acme"
             *       }
             *     ]
             */
            deleted: components["schemas"]["DeletedDocument"][];
            /**
             * Not Found
             * @description Requested ids with no document (never stored, or already deleted).
             * @example [
             *       "upload-4be0c2a91d7f"
             *     ]
             */
            not_found: string[];
        };
        /**
         * DocumentPage
         * @description A page of documents.
         */
        DocumentPage: {
            /**
             * Items
             * @description The items of this page, possibly empty.
             */
            items: components["schemas"]["Document"][];
            /**
             * Limit
             * @description Page size requested.
             * @example 25
             */
            limit: number;
            /**
             * Offset
             * @description Number of matching items skipped.
             * @example 0
             */
            offset: number;
            /**
             * Total
             * @description Number of items matching the filters, across all pages.
             * @example 42
             */
            total: number;
        };
        /**
         * DocumentStatusCounts
         * @description How the stored documents compare with the current settings, across all tenants.
         */
        DocumentStatusCounts: {
            /**
             * Indexed
             * @description Documents the current settings would index the same way.
             * @example 9
             */
            indexed: number;
            /** @description The other documents, by reason; reprocessing brings them up to date. */
            outdated: components["schemas"]["OutdatedCounts"];
            /**
             * Total
             * @description Stored documents.
             * @example 12
             */
            total: number;
        };
        /**
         * DocumentUpdate
         * @description Changes to a document that need no reprocessing. Only the title, for now.
         */
        DocumentUpdate: {
            /**
             * Title
             * @description New display title. Surrounding whitespace is removed; 1 to 200 characters remain.
             * @example PRO-014 Control de sellado (rev. 3)
             */
            title: string;
        };
        /**
         * EmbeddingHealth
         * @description The embedding provider: a check embedding one short word (cached for 60 s), and the
         *     outcome of the last real embedding calls since the service started.
         */
        EmbeddingHealth: {
            /**
             * Cached
             * @description Whether this is the result of an earlier check (up to 60 s old). `refresh=true` always checks again.
             * @example true
             */
            cached: boolean;
            /**
             * Checked At
             * Format: date-time
             * @description When the check ran (UTC); older than this request when `cached`.
             * @example 2026-11-05T10:14:03Z
             */
            checked_at: string;
            /**
             * Error
             * @description Why the check failed; null when up.
             * @example Embedding provider unreachable (ReadTimeout)
             */
            error: string | null;
            /**
             * Last Error
             * @description Why that call failed.
             * @example Embedding provider returned HTTP 503
             */
            last_error: string | null;
            /**
             * Last Error At
             * @description Last failed embedding call by an upload, a reprocess or a search (UTC); null if none since the service started.
             * @example 2026-11-05T10:12:10Z
             */
            last_error_at: string | null;
            /**
             * Last Success At
             * @description Last successful embedding call by an upload, a reprocess or a search (UTC); null if none since the service started.
             * @example 2026-11-05T09:58:41Z
             */
            last_success_at: string | null;
            /**
             * Latency Ms
             * @description How long the check took.
             * @example 180
             */
            latency_ms: number;
            /**
             * Provider
             * @description Embedding provider (`EMBEDDING_PROVIDER`); `fake` is always up.
             * @example voyage
             * @enum {string}
             */
            provider: "voyage" | "fake";
            /**
             * Status
             * @description `up` if the check embedded its word within 5 s, without retries.
             * @example up
             * @enum {string}
             */
            status: "up" | "down";
        };
        /**
         * EmbeddingSettings
         * @description How chunks are embedded. No keys or URLs.
         */
        EmbeddingSettings: {
            /**
             * Batch Size
             * @description Texts per provider request (`EMBEDDING_BATCH_SIZE`).
             * @example 128
             */
            batch_size: number;
            /**
             * Dimensions
             * @description Vector size (`EMBEDDING_DIMENSIONS`); the database column must match.
             * @example 1024
             */
            dimensions: number;
            /**
             * Embedder Config
             * @description Model and dimensions as one string: a document whose `embedder_config` differs is outdated (`embedder_changed`).
             * @example voyage-4/document/1024
             */
            embedder_config: string;
            /**
             * Model
             * @description Embedding model (`EMBEDDING_MODEL`).
             * @example voyage-4
             */
            model: string;
            /**
             * Provider
             * @description Embedding provider (`EMBEDDING_PROVIDER`); `fake` is for tests and local runs.
             * @example voyage
             * @enum {string}
             */
            provider: "voyage" | "fake";
        };
        /**
         * ErrorItem
         * @description One error. The items of FastAPI's `HTTPValidationError` have this shape too.
         */
        ErrorItem: {
            /**
             * Ctx
             * @description Extra details, such as the expected pattern. Request validation errors only.
             */
            ctx?: {
                [key: string]: unknown;
            } | null;
            /**
             * Input
             * @description The rejected value. Request validation errors only.
             */
            input?: unknown;
            /**
             * Loc
             * @description Where the error is: `["body", "<field>"]`, `["header", "x-api-key"]`, or `[]` when no single input is at fault.
             * @example [
             *       "body",
             *       "file"
             *     ]
             */
            loc: (string | number)[];
            /**
             * Msg
             * @description Human-readable explanation.
             * @example file is empty
             */
            msg: string;
            /**
             * Type
             * @description Stable, machine-readable error code: branch on this, not on `msg`.
             * @example file_empty
             */
            type: string;
        };
        /**
         * ErrorResponse
         * @description The body of every error response.
         * @example {
         *       "detail": [
         *         {
         *           "loc": [
         *             "body",
         *             "file"
         *           ],
         *           "msg": "file is empty",
         *           "type": "file_empty"
         *         }
         *       ]
         *     }
         */
        ErrorResponse: {
            /**
             * Detail
             * @description One or more errors.
             */
            detail: components["schemas"]["ErrorItem"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /**
             * Status
             * @description Always `ok` when the process is serving.
             * @example ok
             * @constant
             */
            status: "ok";
        };
        /**
         * IndexingSettings
         * @description The settings new uploads and reprocesses use, and the documents' status against
         *     them.
         */
        IndexingSettings: {
            /** @description Chunking settings. */
            chunking: components["schemas"]["ChunkingSettings"];
            /** @description Document counts by status. */
            documents: components["schemas"]["DocumentStatusCounts"];
            /** @description Embedding settings. */
            embedding: components["schemas"]["EmbeddingSettings"];
            /** @description Upload limits. */
            uploads: components["schemas"]["UploadSettings"];
        };
        /**
         * IngestResponse
         * @description The outcome of an upload or a reprocess. Sent without the optional fields when
         *     `up_to_date`.
         * @example {
         *       "chunk_count": 12,
         *       "doc_id": "upload-1890b5dc5335",
         *       "embed_signature": "17047d562b7e9a3c0f5d8b1e4a7c2f6d9b0e3a8c5f1d4b7e2a9c6f0d3b8e5a1c",
         *       "embedding_model": "voyage-4",
         *       "status": "indexed"
         *     }
         */
        IngestResponse: {
            /**
             * Chunk Count
             * @description Number of chunks stored. Only when `indexed`.
             * @example 12
             */
            chunk_count?: number | null;
            /**
             * Doc Id
             * @description Stable id of the document, derived from the tenant and the source key.
             * @example upload-1890b5dc5335
             */
            doc_id: string;
            /**
             * Embed Signature
             * @description Signature that decides whether a later upload is `up_to_date`: the document's `embed_signature`. Only when `indexed`.
             * @example 17047d562b7e9a3c0f5d8b1e4a7c2f6d9b0e3a8c5f1d4b7e2a9c6f0d3b8e5a1c
             */
            embed_signature?: string | null;
            /**
             * Embedding Model
             * @description Embedding model used for the chunks. Only when `indexed`.
             * @example voyage-4
             */
            embedding_model?: string | null;
            /**
             * Status
             * @description `indexed`: chunked, embedded and stored (HTTP 201 on upload, 200 on reprocess). `up_to_date`: the stored version has the same content and settings, nothing was done (HTTP 200).
             * @example indexed
             * @enum {string}
             */
            status: "indexed" | "up_to_date";
        };
        /**
         * OutdatedCounts
         * @description Outdated documents by reason, as `outdated_reason` reports them. A document whose
         *     chunker and embedder configs both differ counts as `chunker_changed` only.
         */
        OutdatedCounts: {
            /**
             * Chunker Changed
             * @description Chunked with other chunking settings.
             * @example 2
             */
            chunker_changed: number;
            /**
             * Embedder Changed
             * @description Same chunking, embedded with another model or vector size.
             * @example 1
             */
            embedder_changed: number;
            /**
             * Unknown
             * @description Indexed before configs were stored: their settings are not known.
             * @example 0
             */
            unknown: number;
        };
        /**
         * SearchDebug
         * @description How the search ran, for diagnosis.
         */
        SearchDebug: {
            /**
             * Chunker Config
             * @description Current chunking settings (documents chunked otherwise are still searched).
             * @example md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1
             */
            chunker_config: string;
            /**
             * Embedded Query
             * @description The text sent to the embedding provider: the trimmed query. The provider adds its own retrieval prompt for `input_type`.
             * @example ¿Qué herramienta uso si tengo muchos tipos de defecto?
             */
            embedded_query: string;
            /**
             * Embedder Config
             * @description Embedding model and dimensions searched with; documents with another value are skipped unless `include_outdated`.
             * @example voyage-4/document/1024
             */
            embedder_config: string;
            /**
             * Input Type
             * @description How the query was embedded (documents are embedded as `document`).
             * @example query
             * @constant
             */
            input_type: "query";
            /** @description Durations of the stages. */
            timings_ms: components["schemas"]["SearchTimings"];
        };
        /**
         * SearchHitResult
         * @description One chunk found, with what a result list shows of its document.
         */
        SearchHitResult: {
            /**
             * Char Count
             * @description Length of `chunk_text` in characters (not bytes).
             * @example 148
             */
            char_count: number;
            /**
             * Chunk Id
             * Format: uuid
             * @description Stable id of the chunk until its document is reprocessed or replaced.
             * @example 0b9f6c1e-3d2a-4f5b-8c7d-9e0a1b2c3d4e
             */
            chunk_id: string;
            /**
             * Chunk Index
             * @description Position of the chunk in its document, from 0 (as in the chunks listing).
             * @example 3
             */
            chunk_index: number;
            /**
             * Chunk Text
             * @description The chunk's text (without the heading path that was embedded with it).
             * @example Usa el diagrama de Pareto cuando tengas muchos tipos de defecto y necesites decidir cuáles atacar primero: el 20% de las causas suele explicar el 80%.
             */
            chunk_text: string;
            /**
             * Doc Id
             * @description The document the chunk belongs to (link to its detail).
             * @example upload-3f9a1c2b7d4e
             */
            doc_id: string;
            /**
             * Document Title
             * @description The document's display title.
             * @example Método Pareto
             */
            document_title: string | null;
            /**
             * Embedder Outdated
             * @description The document was embedded with another (or an unknown) embedding model: its similarity is not comparable. Only true with `include_outdated`; reprocess the document to fix it.
             * @example false
             */
            embedder_outdated: boolean;
            /**
             * Heading
             * @description Path of the Markdown headings the chunk sits under, joined with ` > `; null before the first heading.
             * @example Método Pareto > Cuándo aplicarlo
             */
            heading: string | null;
            /**
             * Rank
             * @description Position in the results, from 1.
             * @example 1
             */
            rank: number;
            /**
             * Similarity
             * @description Cosine similarity between the query and the chunk, rounded to 4 decimals: 1 for the same direction, 0 for unrelated, negative for opposite. Results are ordered by it, highest first; ties by `chunk_id`.
             * @example 0.8734
             */
            similarity: number;
            /**
             * Source Key
             * @description Name that identifies the document within its tenant.
             * @example pareto.md
             */
            source_key: string;
            /**
             * Tenant
             * @description Tenant the document belongs to.
             * @example ayo
             */
            tenant: string;
        };
        /**
         * SearchRequest
         * @description A question to find the nearest chunks for, and where to look.
         */
        SearchRequest: {
            /**
             * Debug
             * @description Add `debug` to the answer: the text embedded, the configs and timings.
             * @default false
             * @example false
             */
            debug: boolean;
            /**
             * Doc Ids
             * @description Search only these documents, 1 to 50 ids, no repeats; null searches every document. Useful to debug one document. Unknown ids add no results.
             * @example [
             *       "upload-1890b5dc5335"
             *     ]
             */
            doc_ids?: string[] | null;
            /**
             * Include Outdated
             * @description Also search documents embedded with another embedding model (or an unknown one), flagged with `embedder_outdated`. Their vectors live in another space, so their similarities are not comparable; by default they are skipped and counted in `skipped`. A chunking change alone never skips a document.
             * @default false
             * @example false
             */
            include_outdated: boolean;
            /**
             * Min Similarity
             * @description Drop results whose `similarity` is below this, 0 to 1; null keeps them all. Not calibrated yet: the evaluation harness reports the similarities of answerable and unanswerable questions to choose it.
             * @example 0.5
             */
            min_similarity?: number | null;
            /**
             * Query
             * @description The question, in the plant team's words. Surrounding whitespace is removed; 1 to 2000 characters remain. Never logged.
             * @example ¿Qué herramienta uso si tengo muchos tipos de defecto?
             */
            query: string;
            /**
             * Tenants
             * @description Tenants to search, 1 to 50, no repeats; null searches every tenant. A tenant without documents is not an error, it just adds no results. The production agent will always search one customer's tenant plus the shared `ayo` tenant, never across customers; searching every tenant is for administrators.
             * @example [
             *       "cliente-acme",
             *       "ayo"
             *     ]
             */
            tenants?: string[] | null;
            /**
             * Top K
             * @description How many chunks to return at most, 1 to 50.
             * @default 5
             * @example 5
             */
            top_k: number;
        };
        /**
         * SearchResponse
         * @description The nearest chunks, what was skipped and, on request, how the search ran.
         */
        SearchResponse: {
            /**
             * @description Present (not null) only with `debug=true`.
             * @example {
             *       "chunker_config": "md-header+recursive@v3/size=800/overlap=80/min=100/merge=fwd,back1.5x,keep/breadcrumb=1",
             *       "embedded_query": "¿Qué herramienta uso si tengo muchos tipos de defecto?",
             *       "embedder_config": "voyage-4/document/1024",
             *       "input_type": "query",
             *       "timings_ms": {
             *         "embed": 41.2,
             *         "search": 6.3,
             *         "total": 47.5
             *       }
             *     }
             */
            debug: components["schemas"]["SearchDebug"] | null;
            /**
             * Query
             * @description The query as searched (trimmed).
             * @example ¿Qué herramienta uso si tengo muchos tipos de defecto?
             */
            query: string;
            /**
             * Results
             * @description The nearest chunks, best first; empty when nothing matches the filters or passes `min_similarity`.
             */
            results: components["schemas"]["SearchHitResult"][];
            /** @description Documents left out of the search. */
            skipped: components["schemas"]["SearchSkipped"];
        };
        /**
         * SearchSkipped
         * @description Documents matching the filters that were not searched.
         */
        SearchSkipped: {
            /**
             * Embedder Mismatch
             * @description Documents embedded with another embedding model, or an unknown one, and so skipped (0 with `include_outdated`). Reprocess them to make them searchable again.
             * @example 2
             */
            embedder_mismatch: number;
        };
        /**
         * SearchTimings
         * @description Where the time went, in milliseconds rounded to 0.1.
         */
        SearchTimings: {
            /**
             * Embed
             * @description Embedding the query (the provider call).
             * @example 41.2
             */
            embed: number;
            /**
             * Search
             * @description The database search.
             * @example 6.3
             */
            search: number;
            /**
             * Total
             * @description Both, as measured around them.
             * @example 47.5
             */
            total: number;
        };
        /**
         * ServiceHealth
         * @description Whether the services the API depends on work.
         */
        ServiceHealth: {
            /** @description The database. */
            database: components["schemas"]["DatabaseHealth"];
            /** @description The embedding provider. */
            embeddings: components["schemas"]["EmbeddingHealth"];
            /**
             * Status
             * @description `ok` when the database and the embedding provider are both up.
             * @example ok
             * @enum {string}
             */
            status: "ok" | "degraded";
        };
        /**
         * TenantSummary
         * @description A tenant with stored documents.
         */
        TenantSummary: {
            /**
             * Chunk Count
             * @description Total chunks of those documents (the sum of their `chunk_count`).
             * @example 57
             */
            chunk_count: number;
            /**
             * Document Count
             * @description Number of the tenant's stored documents, whatever their status.
             * @example 4
             */
            document_count: number;
            /**
             * Tenant
             * @description Tenant id, as given on upload.
             * @example acme
             */
            tenant: string;
        };
        /**
         * ToolUse
         * @description One tool call the copilot made in the turn: what it tried to record, not the values.
         * @example {
         *       "name": "record_field",
         *       "ok": true
         *     }
         */
        ToolUse: {
            /**
             * Name
             * @description The tool: `record_field`, `log_event`, `add_action`, `update_action` or `propose_transition` (any other name was refused).
             * @example record_field
             */
            name: string;
            /**
             * Ok
             * @description Whether it was accepted. A refused call (invalid values, criteria not met) changed nothing; the copilot was told why.
             * @example true
             */
            ok: boolean;
        };
        /**
         * UploadSettings
         * @description Limits on uploads.
         */
        UploadSettings: {
            /**
             * Max Upload Bytes
             * @description Largest accepted file in bytes (`MAX_UPLOAD_BYTES`); larger ones get `413`.
             * @example 5242880
             */
            max_upload_bytes: number;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_documents: {
        parameters: {
            query?: {
                /** @description Only this tenant's documents. */
                tenant?: string | null;
                /** @description Case-insensitive substring of the title or the source key. */
                q?: string | null;
                /** @description Only documents with this `status` against the current settings. */
                status?: ("indexed" | "outdated") | null;
                /** @description Sort key; prefix `-` for descending. Ties are broken by an internal id, so the order is stable. */
                sort?: "updated_at" | "-updated_at" | "created_at" | "-created_at" | "title" | "-title" | "chunk_count" | "-chunk_count";
                /** @description Page size, 1 to 100. */
                limit?: number;
                /** @description Number of matching documents to skip. */
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description A page of documents. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentPage"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description A query parameter is not acceptable. `type` is a FastAPI validation code such as `literal_error` (unknown `sort` or `status`), `greater_than_equal` or `less_than_equal` (`limit`, `offset`) or `string_pattern_mismatch` (`tenant`). */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    upload_document: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_document"];
            };
        };
        responses: {
            /** @description Already up to date: same content and settings, nothing was done. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IngestResponse"];
                };
            };
            /** @description Indexed: the document was chunked, embedded and stored. */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IngestResponse"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The file is larger than `MAX_UPLOAD_BYTES`. */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The file or a field is not acceptable. `type` is one of `file_extension`, `file_encoding`, `file_empty`, `file_no_content`, `source_key_invalid`, or a FastAPI validation code such as `missing` or `string_pattern_mismatch`. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The embedding provider failed after retries. Nothing was stored; retrying later is safe. */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_documents: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DocumentDeleteRequest"];
            };
        };
        responses: {
            /** @description The deleted documents and the ids that were not found. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentDeleteResult"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The body is not acceptable. `type` is a FastAPI validation code such as `too_short` (no ids), `too_long` (more than 100), `string_pattern_mismatch` (an id, `loc` ends with its index), `duplicate_doc_ids`, `missing`, `extra_forbidden` or `json_invalid`. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_document: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`. */
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The document. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No document has this `doc_id`. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `doc_id` is not a document id (FastAPI validation): it never matches a document. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_document: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`. */
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Deleted, with its chunks. */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No document has this `doc_id`. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `doc_id` is not a document id (FastAPI validation): it never matches a document. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_document: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`. */
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DocumentUpdate"];
            };
        };
        responses: {
            /** @description The document, renamed. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No document has this `doc_id`. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `doc_id` is not a document id, or the body is not acceptable. `type` is a FastAPI validation code such as `string_too_short` or `string_too_long` (`title`), `missing`, `extra_forbidden` (a field other than `title`), `json_invalid` or `string_pattern_mismatch` (`doc_id`). */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_document_chunks: {
        parameters: {
            query?: {
                /** @description Page size, 1 to 200. */
                limit?: number;
                /** @description Number of chunks to skip. */
                offset?: number;
                /** @description Also return each chunk's vector. Heavy: one float per dimension. */
                include_embedding?: boolean;
            };
            header?: never;
            path: {
                /** @description Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`. */
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description A page of chunks. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChunkPage"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No document has this `doc_id`. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `doc_id` is not a document id, or a query parameter is not acceptable. `type` is a FastAPI validation code such as `string_pattern_mismatch` (`doc_id`), `greater_than_equal` or `less_than_equal` (`limit`, `offset`) or `bool_parsing` (`include_embedding`). */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_document_content: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`. */
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The stored Markdown. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/markdown; charset=utf-8": string;
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No document has this `doc_id`. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `doc_id` is not a document id (FastAPI validation): it never matches a document. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    reprocess_document: {
        parameters: {
            query?: {
                /** @description Reprocess even when the document is up to date. */
                force?: boolean;
            };
            header?: never;
            path: {
                /** @description Id of the document, as returned by the upload and the listing: `<source type>-<12 hex>`. */
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Reprocessed, or already up to date. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IngestResponse"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No document has this `doc_id`. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description A newer upload replaced the document while it was being reprocessed. Nothing was written; the newer version stays. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `doc_id` is not a document id (`string_pattern_mismatch`) or `force` is not a boolean (`bool_parsing`); FastAPI validation. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The embedding provider failed after retries. Nothing was stored; retrying later is safe. */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_service_health: {
        parameters: {
            query?: {
                /** @description Check the embedding provider again instead of using the result of a check in the last 60 s. */
                refresh?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The status of each service. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ServiceHealth"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `refresh` is not a boolean (`bool_parsing`). */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    search_documents: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SearchRequest"];
            };
        };
        responses: {
            /** @description The nearest chunks, the documents skipped and, with `debug`, how the search ran. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchResponse"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The body is not acceptable. `type` is a FastAPI validation code such as `string_too_short` (blank `query`), `string_too_long` (over 2000 characters), `greater_than_equal` / `less_than_equal` (`top_k`, `min_similarity`), `string_pattern_mismatch` (a tenant or doc id; `loc` ends with its index), `too_short` (an empty list: send null instead), `too_long`, `duplicate_tenants`, `duplicate_doc_ids`, `missing`, `extra_forbidden` or `json_invalid`. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The embedding provider failed after retries. Nothing was searched; retrying later is safe. */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_settings: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The current settings and the document counts by status. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexingSettings"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_tenants: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The tenants, ordered by tenant. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantSummary"][];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    send_copilot_message: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CopilotMessageRequest"];
            };
        };
        responses: {
            /** @description The copilot's reply and the case's phase after the turn. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CopilotMessageResponse"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The case is closed (`case_closed`), or another turn of the session was committed while this one ran (`case_changed`: nothing was stored, send the message again). */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The body is not acceptable. `type` is `tenant_mismatch` (the session belongs to another tenant; nothing was stored), `string_too_long` (`text` over `MAX_USER_MESSAGE_CHARS`, default 4000) or a FastAPI validation code: `string_too_short` (blank `text` or `user_id`), `uuid_parsing` (`session_id`), `string_pattern_mismatch` (`tenant`), `missing`, `extra_forbidden` or `json_invalid`. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The language model failed after retries. Nothing was stored; sending the message again later is safe. One fixed message per `type`, never the provider's details. */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No language model is configured (`OPENROUTER_API_KEY` is unset). Nothing was stored. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_copilot_session: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description The session id (a UUID) sent with the session's messages. */
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The session's case. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CopilotSession"];
                };
            };
            /** @description `X-API-Key` is missing or wrong. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No session has this id. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description `session_id` is not a UUID: `type` is `uuid_parsing`. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
}
