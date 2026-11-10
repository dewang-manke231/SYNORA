"""add_chat_threads_and_messages

Revision ID: e4a8f9c1b2d3
Revises: a3cfb3a89578
Create Date: 2026-11-10 20:25:00.000000

Adds chat_threads and chat_messages tables for specialized AI agents.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a8f9c1b2d3'
down_revision: Union[str, Sequence[str], None] = 'a3cfb3a89578'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "chat_threads" not in tables:
        op.create_table(
            "chat_threads",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("agent_type", sa.String(50), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("context_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_chat_threads_organization_id", "chat_threads", ["organization_id"])
        op.create_index("ix_chat_threads_project_id", "chat_threads", ["project_id"])
        op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])
        op.create_index("ix_chat_threads_agent_type", "chat_threads", ["agent_type"])
        op.create_index("ix_chat_threads_context_id", "chat_threads", ["context_id"])

    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("thread_id", sa.String(64), sa.ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender_role", sa.String(50), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("citations", sa.JSON(), nullable=True),
            sa.Column("recommended_actions", sa.JSON(), nullable=True),
            sa.Column("tool_calls", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])
        op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
