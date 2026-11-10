"""
Migration Script: Local Document Storage to Supabase Storage

Supports:
- --dry-run: Inspects migration plan without uploading or committing changes.
- Live migration: Safely uploads existing local documents to Supabase Storage,
  preserves original local files, and updates database metadata.
"""
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Document, Project
from app.services.storage import get_storage_provider, SupabaseStorageProvider, LocalStorageProvider


def migrate_local_documents_to_supabase_storage(dry_run: bool = False) -> int:
    print("=" * 70)
    mode_str = "DRY-RUN INSPECTION" if dry_run else "LIVE MIGRATION"
    print(f" SYNORA STORAGE MIGRATION ({mode_str})")
    print("=" * 70)

    storage = get_storage_provider()
    is_supabase = isinstance(storage, SupabaseStorageProvider)

    print(f"Active Storage Provider: {'Supabase Storage (Cloud)' if is_supabase else 'Local Storage'}")
    if not is_supabase:
        print("[NOTICE] SupabaseStorageProvider is not active. Configure STORAGE_PROVIDER=supabase and SUPABASE_SERVICE_ROLE_KEY first.")
        return 0

    local_storage = LocalStorageProvider()
    db = SessionLocal()
    migrated_count = 0

    try:
        docs = db.query(Document).all()
        print(f"Total documents found in database: {len(docs)}")

        for doc in docs:
            meta = doc.metadata_tags or {}
            old_path = doc.storage_path or ""

            # Check if document is already in Supabase Storage
            if meta.get("storage_backend") == "supabase" and old_path and not old_path.startswith("uploads"):
                print(f"  [SKIPPED] Doc {doc.id} ('{doc.filename}') already recorded in Supabase Storage ({old_path}).")
                continue

            # Check local file existence
            if not old_path or not local_storage.exists(old_path):
                # Check default fallback location
                candidate = f"projects/{doc.project_id}/{doc.file_hash[:12] if doc.file_hash else 'file'}_{doc.filename}"
                if local_storage.exists(candidate):
                    old_path = candidate
                else:
                    print(f"  [SKIPPED] Local file not found on disk for Doc {doc.id} ('{doc.filename}').")
                    continue

            # Read content bytes
            try:
                content_bytes = local_storage.read(old_path)
            except Exception as e:
                print(f"  [WARNING] Could not read local file for Doc {doc.id}: {e}")
                continue

            # Determine target hierarchical path
            proj = db.query(Project).filter(Project.id == doc.project_id).first()
            org_id = proj.organization_id if proj and proj.organization_id else "default-org"
            new_path = f"{org_id}/{doc.project_id}/{doc.id}/{doc.filename}"

            if dry_run:
                print(f"  [DRY-RUN] Would migrate Doc {doc.id} ('{doc.filename}') -> '{new_path}' ({len(content_bytes)} bytes)")
                migrated_count += 1
            else:
                try:
                    saved_path = storage.save(new_path, content_bytes, content_type=doc.content_type)
                    doc.storage_path = saved_path
                    meta["storage_backend"] = "supabase"
                    meta["migrated_from_local"] = True
                    doc.metadata_tags = meta
                    db.commit()
                    print(f"  [MIGRATED] Doc {doc.id} ('{doc.filename}') -> '{saved_path}' in Supabase Storage.")
                    migrated_count += 1
                except Exception as e:
                    db.rollback()
                    print(f"  [ERROR] Failed to migrate Doc {doc.id}: {e}")

        print("\n" + "=" * 70)
        action_word = "would be migrated" if dry_run else "migrated successfully"
        print(f" RESULT: {migrated_count} document(s) {action_word}.")
        print("=" * 70)
        return migrated_count

    finally:
        db.close()


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    count = migrate_local_documents_to_supabase_storage(dry_run=is_dry)
    sys.exit(0)
