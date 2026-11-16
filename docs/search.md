# Searching the knowledge base

`POST /admin/search` finds the chunks nearest to a question, as the copilot does when it
retrieves knowledge ([copilot.md](copilot.md#the-flow-of-a-turn)). The admin UI has a test
screen for it at `/search` ([ui/README.md](../ui/README.md#test-search)). Every route here needs the `X-API-Key` header (see [Endpoints](../README.md#endpoints));
`/docs` has every field, status and error `type`.

```sh
H="X-API-Key: $ADMIN_API_KEY"
curl -H "$H" -H "Content-Type: application/json" \
  -d '{"query": "¿Qué herramienta uso si tengo muchos tipos de defecto?",
       "tenants": ["cliente-acme", "ayo"], "top_k": 5, "debug": true}' \
  "http://127.0.0.1:8000/admin/search"
# {"query": "¿Qué herramienta uso si tengo muchos tipos de defecto?",
#  "results": [{"rank": 1, "similarity": 0.8734, "chunk_id": "0b9f6c1e-...",
#    "chunk_index": 3, "heading": "Método Pareto > Cuándo aplicarlo", "chunk_text": "...",
#    "char_count": 148, "doc_id": "upload-3f9a1c2b7d4e", "document_title": "Método Pareto",
#    "source_key": "pareto.md", "tenant": "ayo", "embedder_outdated": false}],
#  "skipped": {"embedder_mismatch": 0},
#  "debug": {"embedded_query": "...", "input_type": "query", "embedder_config": "...",
#    "chunker_config": "...", "timings_ms": {"embed": 41.2, "search": 6.3, "total": 47.5}}}
```

What the copilot would retrieve for a question. The query is embedded as a search query
(Voyage `input_type: "query"`), then compared by cosine similarity with every chunk that
passes the filters: an exact search, so the same request on the same data always gives
the same answer ([ADR 0002](decisions/0002-filtered-vector-search.md)). Results are ordered by
`similarity` (1 - cosine distance, 4 decimals), ties by chunk id.

| Field | Default | Meaning |
|---|---|---|
| `query` | required | 1 to 2000 characters after trimming |
| `tenants` | `null` (all) | 1 to 50 tenant ids. The production agent will search one customer plus `ayo`, never across customers |
| `top_k` | 5 | 1 to 50 |
| `min_similarity` | `null` | 0 to 1; weaker results are dropped |
| `doc_ids` | `null` (all) | 1 to 50 document ids, to debug one document |
| `include_outdated` | `false` | Also search documents embedded with another model, flagged `embedder_outdated` |
| `debug` | `false` | Fill `debug` (otherwise `null`) with the text embedded, the configs and timings |

Send `null`, not `[]`, for no filter: an empty list is a `422`. Unknown tenants or ids are
not errors; they just add no results.

Vectors of different embedding models are not comparable, so documents embedded with
another model (or an unknown one) are skipped and counted in `skipped.embedder_mismatch`:
reprocess them. A change of the chunking settings alone skips nothing. If the embedding
provider fails, the answer is `502 embedding_failed` and nothing is searched. Neither the
query nor the results are logged: only tenants, counts and durations.
