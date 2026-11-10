"""add_extraction_metadata_and_verification_fields

Revision ID: 5033ca3bd58a
Revises: 3710b2e53e9e
Create Date: 2026-11-09 23:26:43.367758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5033ca3bd58a'
down_revision: Union[str, Sequence[str], None] = '3710b2e53e9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    kn_cols = [c["name"] for c in inspector.get_columns("extracted_knowledge")]
    ver_cols = [c["name"] for c in inspector.get_columns("verification_records")]

    with op.batch_alter_table("extracted_knowledge", schema=None) as batch_op:
        if "document_id" not in kn_cols:
            batch_op.add_column(sa.Column("document_id", sa.String(length=64), nullable=True))
            batch_op.create_foreign_key("fk_extracted_knowledge_doc", "documents", ["document_id"], ["id"], ondelete="CASCADE")
            batch_op.create_index("ix_extracted_knowledge_document_id", ["document_id"])
        if "source_quote" not in kn_cols:
            batch_op.add_column(sa.Column("source_quote", sa.Text(), nullable=True))
        if "metadata_tags" not in kn_cols:
            batch_op.add_column(sa.Column("metadata_tags", sa.JSON(), nullable=True))

    with op.batch_alter_table("verification_records", schema=None) as batch_op:
        if "reviewer_name" not in ver_cols:
            batch_op.add_column(sa.Column("reviewer_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("verification_records", schema=None) as batch_op:
        batch_op.drop_column("reviewer_name")

    with op.batch_alter_table("extracted_knowledge", schema=None) as batch_op:
        batch_op.drop_index("ix_extracted_knowledge_document_id")
        batch_op.drop_column("metadata_tags")
        batch_op.drop_column("source_quote")
        batch_op.drop_column("document_id")
