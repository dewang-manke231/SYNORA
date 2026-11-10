"""add_handover_assigned_to

Revision ID: 8b9f01bc34de
Revises: 7a8e9f01bc23
Create Date: 2026-11-10 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b9f01bc34de'
down_revision: Union[str, Sequence[str], None] = '7a8e9f01bc23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add assigned_to and assigned_at columns to handovers table with foreign key and index."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    handover_cols = [c["name"] for c in inspector.get_columns("handovers")]

    with op.batch_alter_table("handovers", schema=None) as batch_op:
        if "assigned_to" not in handover_cols:
            batch_op.add_column(sa.Column("assigned_to", sa.String(64), nullable=True))
            batch_op.create_foreign_key("fk_handovers_assigned_to", "users", ["assigned_to"], ["id"], ondelete="SET NULL")
            batch_op.create_index("ix_handovers_assigned_to", ["assigned_to"])
        if "assigned_at" not in handover_cols:
            batch_op.add_column(sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("handovers", schema=None) as batch_op:
        batch_op.drop_index("ix_handovers_assigned_to")
        batch_op.drop_constraint("fk_handovers_assigned_to", type_="foreignkey")
        batch_op.drop_column("assigned_at")
        batch_op.drop_column("assigned_to")

