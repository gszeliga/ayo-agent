"""Initial schema: documents and chunks with pgvector embeddings.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create extension if not exists vector")
    op.execute(
        """
        create table documents (
          id uuid primary key default gen_random_uuid(),
          doc_id text not null unique,
          tenant text not null,
          source_type text not null default 'upload',
          source_key text not null,
          title text,
          markdown_path text not null,
          content_hash text not null,
          chunk_signature text not null,
          embed_signature text not null,
          chunked_at timestamptz,
          embedded_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          -- Its leading column also serves lookups by tenant, so no separate tenant index.
          unique (tenant, source_type, source_key)
        )
        """
    )
    # The dimension is fixed here on purpose: changing EMBEDDING_DIMENSIONS needs a new
    # migration, and the app refuses to start while the two disagree.
    op.execute(
        """
        create table chunks (
          id uuid primary key default gen_random_uuid(),
          document_id uuid not null references documents(id) on delete cascade,
          chunk_index int not null,
          heading text,
          chunk_text text not null,
          metadata jsonb not null default '{}',
          embedding vector(1024) not null,
          created_at timestamptz not null default now(),
          unique (document_id, chunk_index)
        )
        """
    )
    op.execute(
        "create index chunks_embedding_hnsw_idx on chunks using hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("drop table chunks")
    op.execute("drop table documents")
    # The `vector` extension stays: other schemas may use it, and keeping it is harmless.
