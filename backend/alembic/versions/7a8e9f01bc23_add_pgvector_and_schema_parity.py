"""add_pgvector_and_schema_parity

Revision ID: 7a8e9f01bc23
Revises: 5033ca3bd58a
Create Date: 2026-11-10 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '7a8e9f01bc23'
down_revision: Union[str, Sequence[str], None] = '5033ca3bd58a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with pgvector extension and embedding vector column."""
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    if dialect_name == "postgresql":
        try:
            op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))
        except Exception:
            pass

    inspector = sa.inspect(conn)
    chunk_cols = [c["name"] for c in inspector.get_columns("document_chunks")]

    with op.batch_alter_table("document_chunks", schema=None) as batch_op:
        if "embedding_vector" not in chunk_cols:
            batch_op.add_column(sa.Column("embedding_vector", Vector(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("document_chunks", schema=None) as batch_op:
        batch_op.drop_column("embedding_vector")

