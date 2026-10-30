"""Hand-written SQL for documents and chunks.

Every function takes a connection and never commits: the caller owns the transaction, so
the document upsert and the chunk replacement can share one.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime
from uuid import UUID

from pgvector import Vector
from psycopg import Connection, sql
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

# Sort keys the documents list accepts, prefixed with `-` for descending. Each one is a
# column name; only these ever reach the SQL text.
SORT_KEYS = ("updated_at", "created_at", "title", "chunk_count")
DEFAULT_SORT = "-updated_at"


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    tenant: str
    source_key: str
    title: str | None
    markdown: str
    content_hash: str
    chunk_signature: str
    embed_signature: str
    chunk_count: int
    # The descriptors the signatures were built from; null on rows indexed before they
    # were stored, which the admin API reports as outdated.
    chunker_config: str | None
    embedder_config: str | None
    source_type: str = "upload"


@dataclass(frozen=True)
class ChunkRecord:
    index: int
    heading: str | None
    text: str
    embedding: Sequence[float]
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentRow:
    """A stored document without its Markdown, as the admin API reads it."""

    id: UUID
    doc_id: str
    tenant: str
    source_type: str
    source_key: str
    title: str | None
    content_hash: str
    chunk_signature: str
    embed_signature: str
    chunk_count: int
    size_bytes: int | None
    chunker_config: str | None
    embedder_config: str | None
    created_at: datetime
    updated_at: datetime
    chunked_at: datetime | None
    embedded_at: datetime | None


_DOCUMENT_COLUMNS = sql.SQL(", ").join(sql.Identifier(f.name) for f in fields(DocumentRow))


@dataclass(frozen=True)
class SimilarChunk:
    doc_id: str
    chunk_index: int
    heading: str | None
    chunk_text: str
    distance: float


def upsert_document(conn: Connection, document: DocumentRecord) -> UUID:
    """Insert the document, or update the row with the same tenant, source type and key.

    `size_bytes` is derived here from the Markdown, the same way migration 0002 backfills it.
    The upsert locks the row until the transaction ends, so a concurrent upload of the
    same document waits here and its chunk replacement runs after this one commits.
    """
    (document_id,) = conn.execute(
        """
        insert into documents (doc_id, tenant, source_type, source_key, title, markdown,
                               content_hash, chunk_signature, embed_signature,
                               chunk_count, size_bytes, chunker_config, embedder_config,
                               chunked_at, embedded_at)
        values (%(doc_id)s, %(tenant)s, %(source_type)s, %(source_key)s, %(title)s,
                %(markdown)s, %(content_hash)s, %(chunk_signature)s, %(embed_signature)s,
                %(chunk_count)s, octet_length(%(markdown)s), %(chunker_config)s,
                %(embedder_config)s, now(), now())
        on conflict (tenant, source_type, source_key) do update set
          title = excluded.title,
          markdown = excluded.markdown,
          content_hash = excluded.content_hash,
          chunk_signature = excluded.chunk_signature,
          embed_signature = excluded.embed_signature,
          chunk_count = excluded.chunk_count,
          size_bytes = excluded.size_bytes,
          chunker_config = excluded.chunker_config,
          embedder_config = excluded.embedder_config,
          chunked_at = excluded.chunked_at,
          embedded_at = excluded.embedded_at,
          updated_at = now()
        returning id
        """,
        {
            "doc_id": document.doc_id,
            "tenant": document.tenant,
            "source_type": document.source_type,
            "source_key": document.source_key,
            "title": document.title,
            "markdown": document.markdown,
            "content_hash": document.content_hash,
            "chunk_signature": document.chunk_signature,
            "embed_signature": document.embed_signature,
            "chunk_count": document.chunk_count,
            "chunker_config": document.chunker_config,
            "embedder_config": document.embedder_config,
        },
    ).fetchone()
    return document_id


def get_embed_signature(conn: Connection, doc_id: str) -> str | None:
    """The stored embed signature of the document, or None if it doesn't exist yet."""
    row = conn.execute(
        "select embed_signature from documents where doc_id = %s", (doc_id,)
    ).fetchone()
    return row[0] if row else None


def replace_chunks(conn: Connection, document_id: UUID, chunks: Sequence[ChunkRecord]) -> None:
    """Delete the document's chunks and insert these ones.

    Call it after `upsert_document`, in the same transaction: that row lock is what keeps
    two replacements of the same document from interleaving.
    """
    conn.execute("delete from chunks where document_id = %s", (document_id,))
    if not chunks:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into chunks (document_id, chunk_index, heading, chunk_text, metadata,
                                embedding)
            values (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    document_id,
                    chunk.index,
                    chunk.heading,
                    chunk.text,
                    Jsonb(dict(chunk.metadata)),
                    Vector(list(chunk.embedding)),
                )
                for chunk in chunks
            ],
        )


def parse_sort(sort: str) -> tuple[str, bool]:
    """`"-title"` -> `("title", True)`: the column and whether it is descending.

    Raises ValueError for anything outside SORT_KEYS.
    """
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    if key not in SORT_KEYS:
        raise ValueError(f"unknown sort key {sort!r}")
    return key, descending


def escape_like(text: str) -> str:
    """Escape `\\`, `%` and `_` so a LIKE pattern matches them literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_documents(
    conn: Connection,
    *,
    tenant: str | None = None,
    q: str | None = None,
    sort: str = DEFAULT_SORT,
    limit: int,
    offset: int,
) -> tuple[list[DocumentRow], int]:
    """One page of documents and the total number matching the filters.

    `q` is a case-insensitive substring of the title or the source key. Ordering always
    ends with `id`, so rows never repeat or vanish across pages. The page and the count are
    two statements: run them in a repeatable-read transaction for a consistent pair.
    """
    column, descending = parse_sort(sort)
    conditions: list[sql.Composable] = []
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if tenant is not None:
        conditions.append(sql.SQL("tenant = %(tenant)s"))
        params["tenant"] = tenant
    if q:
        conditions.append(
            sql.SQL(
                "(title ilike %(pattern)s escape '\\' or source_key ilike %(pattern)s escape '\\')"
            )
        )
        params["pattern"] = f"%{escape_like(q)}%"
    where = sql.SQL(" where ") + sql.SQL(" and ").join(conditions) if conditions else sql.SQL("")
    order = sql.SQL("{} {}, id").format(
        sql.Identifier(column), sql.SQL("desc" if descending else "asc")
    )

    with conn.cursor(row_factory=class_row(DocumentRow)) as cur:
        rows = cur.execute(
            sql.SQL(
                "select {} from documents{} order by {} limit %(limit)s offset %(offset)s"
            ).format(_DOCUMENT_COLUMNS, where, order),
            params,
        ).fetchall()
    (total,) = conn.execute(
        sql.SQL("select count(*) from documents{}").format(where), params
    ).fetchone()
    return rows, total


def get_document(conn: Connection, doc_id: str) -> DocumentRow | None:
    with conn.cursor(row_factory=class_row(DocumentRow)) as cur:
        return cur.execute(
            sql.SQL("select {} from documents where doc_id = %s").format(_DOCUMENT_COLUMNS),
            (doc_id,),
        ).fetchone()


def get_markdown(conn: Connection, doc_id: str) -> str | None:
    """The stored Markdown; the only read of that column, as `DocumentRow` leaves it out."""
    row = conn.execute("select markdown from documents where doc_id = %s", (doc_id,)).fetchone()
    return row[0] if row is not None else None


def similar_chunks(
    conn: Connection, *, tenant: str, embedding: Sequence[float], limit: int = 5
) -> list[SimilarChunk]:
    """The tenant's chunks closest to `embedding` by cosine distance, nearest first.

    No HTTP endpoint uses this yet; it shows that the stored vectors can be queried. With
    the HNSW index and many tenants, the tenant filter is applied after the index scan, so
    a real search endpoint should enable pgvector's iterative index scans.
    """
    rows = conn.execute(
        """
        select d.doc_id, c.chunk_index, c.heading, c.chunk_text,
               c.embedding <=> %(query)s as distance
        from chunks c
        join documents d on d.id = c.document_id
        where d.tenant = %(tenant)s
        order by c.embedding <=> %(query)s
        limit %(limit)s
        """,
        {"query": Vector(list(embedding)), "tenant": tenant, "limit": limit},
    ).fetchall()
    return [SimilarChunk(*row) for row in rows]


def embedding_dimensions(conn: Connection) -> int | None:
    """The `n` of the `chunks.embedding vector(n)` column; None if the table is missing."""
    row = conn.execute(
        "select atttypmod from pg_attribute"
        " where attrelid = to_regclass('chunks') and attname = 'embedding' and not attisdropped"
    ).fetchone()
    return row[0] if row else None
