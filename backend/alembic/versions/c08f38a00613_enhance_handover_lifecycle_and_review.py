"""enhance_handover_lifecycle_and_review

Revision ID: c08f38a00613
Revises: 0ab674b0c6fe
Create Date: 2026-11-09 22:31:39.581477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c08f38a00613'
down_revision: Union[str, Sequence[str], None] = '0ab674b0c6fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema safely checking column existence in SQLite / Postgres."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c['name'] for c in inspector.get_columns('handovers')]

    with op.batch_alter_table('handovers', schema=None) as batch_op:
        if 'project_name' not in existing_cols:
            batch_op.add_column(sa.Column('project_name', sa.String(length=255), nullable=True))
        if 'project_description' not in existing_cols:
            batch_op.add_column(sa.Column('project_description', sa.Text(), nullable=True))
        if 'completed_tasks' not in existing_cols:
            batch_op.add_column(sa.Column('completed_tasks', sa.JSON(), nullable=False, server_default='[]'))
        if 'pending_tasks' not in existing_cols:
            batch_op.add_column(sa.Column('pending_tasks', sa.JSON(), nullable=False, server_default='[]'))
        if 'important_notes' not in existing_cols:
            batch_op.add_column(sa.Column('important_notes', sa.Text(), nullable=True))
        if 'recommended_next_actions' not in existing_cols:
            batch_op.add_column(sa.Column('recommended_next_actions', sa.JSON(), nullable=False, server_default='[]'))
        if 'repository_links' not in existing_cols:
            batch_op.add_column(sa.Column('repository_links', sa.JSON(), nullable=False, server_default='[]'))
        if 'documentation_links' not in existing_cols:
            batch_op.add_column(sa.Column('documentation_links', sa.JSON(), nullable=False, server_default='[]'))
        if 'database_references' not in existing_cols:
            batch_op.add_column(sa.Column('database_references', sa.JSON(), nullable=False, server_default='[]'))
        if 'reviewed_by' not in existing_cols:
            batch_op.add_column(sa.Column('reviewed_by', sa.String(length=255), nullable=True))
        if 'reviewed_at' not in existing_cols:
            batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        if 'review_decision' not in existing_cols:
            batch_op.add_column(sa.Column('review_decision', sa.String(length=50), nullable=True))
        if 'review_notes' not in existing_cols:
            batch_op.add_column(sa.Column('review_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('handovers', schema=None) as batch_op:
        batch_op.drop_column('review_notes')
        batch_op.drop_column('review_decision')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('database_references')
        batch_op.drop_column('documentation_links')
        batch_op.drop_column('repository_links')
        batch_op.drop_column('recommended_next_actions')
        batch_op.drop_column('important_notes')
        batch_op.drop_column('pending_tasks')
        batch_op.drop_column('completed_tasks')
        batch_op.drop_column('project_description')
        batch_op.drop_column('project_name')
