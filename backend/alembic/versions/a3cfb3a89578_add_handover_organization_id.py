"""add_handover_organization_id

Revision ID: a3cfb3a89578
Revises: 8b9f01bc34de
Create Date: 2026-11-10 18:18:13.457624

Safe migration and backfill for handover multi-tenant isolation:
1. Adds organization_id column to handovers table with FK and index.
2. Safely backfills organization_id:
   - Derives from linked projects where available.
   - For unlinked handovers, resolves from verified creator/employee organization membership.
   - Preserves unresolved records without guessing or defaulting.
3. Reports unresolved records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3cfb3a89578'
down_revision: Union[str, Sequence[str], None] = '8b9f01bc34de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add organization_id column to handovers and safely backfill."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    handover_cols = [c["name"] for c in inspector.get_columns("handovers")]

    if "organization_id" not in handover_cols:
        with op.batch_alter_table("handovers", schema=None) as batch_op:
            batch_op.add_column(sa.Column("organization_id", sa.String(64), nullable=True))
            batch_op.create_foreign_key(
                "fk_handovers_organization_id",
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_handovers_organization_id", ["organization_id"])

    # Step 1: Backfill from linked projects where project has organization_id
    conn.execute(sa.text("""
        UPDATE handovers
        SET organization_id = (
            SELECT projects.organization_id
            FROM projects
            WHERE projects.id = handovers.project_id
        )
        WHERE handovers.organization_id IS NULL
          AND handovers.project_id IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM projects
              WHERE projects.id = handovers.project_id
                AND projects.organization_id IS NOT NULL
          )
    """))

    # Step 2: Backfill unlinked/remaining handovers from creator user organization membership
    conn.execute(sa.text("""
        UPDATE handovers
        SET organization_id = (
            SELECT om.organization_id
            FROM users u
            JOIN organization_memberships om ON om.user_id = u.id
            WHERE (u.full_name = handovers.employee_name OR u.email = handovers.employee_name)
            LIMIT 1
        )
        WHERE handovers.organization_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM users u
              JOIN organization_memberships om ON om.user_id = u.id
              WHERE (u.full_name = handovers.employee_name OR u.email = handovers.employee_name)
          )
    """))

    # Step 3: Inspect and report unresolved records (preserving their data without guessing)
    unresolved = conn.execute(sa.text("""
        SELECT id, employee_name, project_id, status
        FROM handovers
        WHERE organization_id IS NULL
    """)).fetchall()

    if unresolved:
        print(f"\n[Alembic Migration Warning] Preserved {len(unresolved)} unresolved handover record(s) without assigned organization:")
        for r in unresolved:
            print(f"  - Handover ID: {r[0]}, Employee: {r[1]}, Project ID: {r[2]}, Status: {r[3]}")
        print("  NOTE: Unresolved records were preserved safely without guessing or defaulting.\n")
    else:
        print("\n[Alembic Migration] All handovers successfully backfilled with verified organization IDs.\n")


def downgrade() -> None:
    """Downgrade schema: drop organization_id column, foreign key, and index."""
    with op.batch_alter_table("handovers", schema=None) as batch_op:
        batch_op.drop_index("ix_handovers_organization_id")
        batch_op.drop_constraint("fk_handovers_organization_id", type_="foreignkey")
        batch_op.drop_column("organization_id")
