"""add_document_lifecycle_and_handover_link

Revision ID: 3710b2e53e9e
Revises: c08f38a00613
Create Date: 2026-11-09 22:51:47.588823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3710b2e53e9e'
down_revision: Union[str, Sequence[str], None] = 'c08f38a00613'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    doc_cols = [c["name"] for c in inspector.get_columns("documents")]
    chunk_cols = [c["name"] for c in inspector.get_columns("document_chunks")]

    with op.batch_alter_table("documents", schema=None) as batch_op:
        if "handover_id" not in doc_cols:
            batch_op.add_column(sa.Column("handover_id", sa.String(length=64), nullable=True))
            batch_op.create_foreign_key("fk_documents_handover_id", "handovers", ["handover_id"], ["id"], ondelete="SET NULL")
            batch_op.create_index("ix_documents_handover_id", ["handover_id"])
        if "storage_path" not in doc_cols:
            batch_op.add_column(sa.Column("storage_path", sa.String(length=512), nullable=True))
        if "processing_status" not in doc_cols:
            batch_op.add_column(sa.Column("processing_status", sa.String(length=50), nullable=False, server_default="uploaded"))
            batch_op.create_index("ix_documents_processing_status", ["processing_status"])
        if "error_message" not in doc_cols:
            batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))

    with op.batch_alter_table("document_chunks", schema=None) as batch_op:
        if "page_number" not in chunk_cols:
            batch_op.add_column(sa.Column("page_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("document_chunks", schema=None) as batch_op:
        batch_op.drop_column("page_number")

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index("ix_documents_processing_status")
        batch_op.drop_index("ix_documents_handover_id")
        batch_op.drop_column("error_message")
        batch_op.drop_column("processing_status")
        batch_op.drop_column("storage_path")
        batch_op.drop_column("handover_id")
