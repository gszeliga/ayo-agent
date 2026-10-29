"""Document admin columns: chunk count, size, processing configs; list index.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The configs are the strings the chunk and embed signatures are built from; storing them
    # lets the admin list compute and filter `outdated` in SQL. Existing rows keep them null,
    # which reads as `outdated` with reason `unknown` until they are reprocessed.
    op.execute(
        """
        alter table documents
          add column chunk_count int not null default 0,
          add column size_bytes int,
          add column chunker_config text,
          add column embedder_config text
        """
    )
    op.execute(
        """
        update documents d set
          chunk_count = (select count(*) from chunks c where c.document_id = d.id),
          size_bytes = octet_length(d.markdown)
        """
    )
    # Serves the default listing: one tenant, newest first, `id` as the tiebreaker.
    op.execute(
        "create index documents_tenant_updated_at_id_idx on documents (tenant, updated_at desc, id)"
    )


def downgrade() -> None:
    op.execute("drop index documents_tenant_updated_at_id_idx")
    op.execute(
        """
        alter table documents
          drop column chunk_count,
          drop column size_bytes,
          drop column chunker_config,
          drop column embedder_config
        """
    )
