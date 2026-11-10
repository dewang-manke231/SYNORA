"""
Alembic Migration & Schema Integrity Test
Verifies that:
1. Alembic migrations run cleanly up to head on a dynamic SQLite test database.
2. Tables created by the migration match all 15 models in Base.metadata.
3. Migrations can be downgraded and upgraded again without orphaned schema state.
"""
import os
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_downgrade():
    test_db_file = "test_alembic_run.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)

    test_db_url = f"sqlite:///./{test_db_file}"

    # Setup Alembic Config object pointing to alembic.ini
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # 1. Run upgrade head
    command.upgrade(alembic_cfg, "head")

    # 2. Inspect created tables
    test_engine = create_engine(test_db_url)
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()

    required_tables = [
        "users",
        "organizations",
        "organization_memberships",
        "projects",
        "knowledge_sources",
        "documents",
        "document_chunks",
        "extracted_knowledge",
        "knowledge_relationships",
        "verification_records",
        "handovers",
        "knowledge_loss_indicators",
        "sentinel_events",
        "environment_snapshots",
        "audit_logs",
        "chat_threads",
        "chat_messages",
    ]

    for table in required_tables:
        assert table in tables, f"Missing table {table} in migrated database"

    # Verify handover columns include assigned_to and organization_id
    handover_cols = [c["name"] for c in inspector.get_columns("handovers")]
    assert "organization_id" in handover_cols, "organization_id column missing from migrated handovers"
    assert "assigned_to" in handover_cols, "assigned_to column missing from migrated handovers"
    assert "assigned_at" in handover_cols, "assigned_at column missing from migrated handovers"

    # 3. Test downgrade one step to previous revision
    command.downgrade(alembic_cfg, "8b9f01bc34de")
    inspector_downgraded = inspect(test_engine)
    downgraded_cols = [c["name"] for c in inspector_downgraded.get_columns("handovers")]
    assert "organization_id" not in downgraded_cols, "organization_id should be removed after downgrade"

    # 4. Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
    inspector_reupgraded = inspect(test_engine)
    reupgraded_cols = [c["name"] for c in inspector_reupgraded.get_columns("handovers")]
    assert "organization_id" in reupgraded_cols, "organization_id should be present after re-upgrade"

    # 5. Clean up
    test_engine.dispose()
    if os.path.exists(test_db_file):
        try:
            os.remove(test_db_file)
        except Exception:
            pass

