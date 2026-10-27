"""Hand-written SQL for documents and chunks.

Every function takes a connection and never commits: the caller owns the transaction, so
the document upsert and the chunk replacement can share one.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from pgvector import Vector
from psycopg import Connection
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    tenant: str
    source_key: str
    title: str | None
    markdown_path: str
    content_hash: str
    chunk_signature: str
    embed_signature: str
    source_type: str = "upload"


@dataclass(frozen=True)
class ChunkRecord:
    index: int
    heading: str | None
    text: str
    embedding: Sequence[float]
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SimilarChunk:
    doc_id: str
    chunk_index: int
    heading: str | None
    chunk_text: str
    distance: float


def upsert_document(conn: Connection, document: DocumentRecord) -> UUID:
    """Insert the document, or update the row with the same tenant, source type and key.

    The upsert locks the row until the transaction ends, so a concurrent upload of the
    same document waits here and its chunk replacement runs after this one commits.
    """
    (document_id,) = conn.execute(
        """
        insert into documents (doc_id, tenant, source_type, source_key, title, markdown_path,
                               content_hash, chunk_signature, embed_signature,
                               chunked_at, embedded_at)
        values (%(doc_id)s, %(tenant)s, %(source_type)s, %(source_key)s, %(title)s,
                %(markdown_path)s, %(content_hash)s, %(chunk_signature)s, %(embed_signature)s,
                now(), now())
        on conflict (tenant, source_type, source_key) do update set
          title = excluded.title,
          markdown_path = excluded.markdown_path,
          content_hash = excluded.content_hash,
          chunk_signature = excluded.chunk_signature,
          embed_signature = excluded.embed_signature,
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
            "markdown_path": document.markdown_path,
            "content_hash": document.content_hash,
            "chunk_signature": document.chunk_signature,
            "embed_signature": document.embed_signature,
        },
    ).fetchone()
    return document_id


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
