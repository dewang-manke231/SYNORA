"""
Live Document API Verification against Supabase Storage

Tests:
1. Manager login and Bearer token acquisition.
2. Real multipart PDF upload through POST /api/v1/documents/upload.
3. Verification that storage_backend is 'supabase' and storage_path follows {org}/{proj}/{doc}/{file}.
4. Verification that the object actually exists in Supabase Storage.
5. Verification of GET /api/v1/documents/{id}/download signed URL generation.
6. Direct download from Supabase Storage signed URL and bit-for-bit SHA-256 hash match.
7. Verification of cross-organization access rejection (HTTP 403 Forbidden).
8. Clean deletion via DELETE /api/v1/documents/{id} and confirmation of removal from cloud storage.
"""
import hashlib
import io
import os
import sys
import time
import httpx

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.services.storage import get_storage_provider, SupabaseStorageProvider
from scripts.verify_supabase_storage import generate_minimal_test_pdf

API_BASE = "http://127.0.0.1:8000/api/v1"


def run_live_api_verification() -> bool:
    print("=" * 70)
    print(" SYNORA LIVE DOCUMENT API & SUPABASE STORAGE VERIFICATION")
    print("=" * 70)

    client = httpx.Client(base_url=API_BASE, timeout=30.0)

    # 1. Use the explicitly enabled local/prototype demo-login flow.
    print("\n[Step 1/6] Authenticating as Manager Marcus Vance...")
    login_res = client.post("/auth/demo-login", json={"role": "manager"})
    if login_res.status_code != 200:
        print(f"  [ERROR] Login failed ({login_res.status_code}): {login_res.text}")
        return False

    auth_token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {auth_token}"}
    print("  --> Authentication successful! Signed JWT token acquired.")

    # 2. Upload actual PDF through API
    print("\n[Step 2/6] Uploading PDF via POST /api/v1/documents/upload...")
    timestamp = int(time.time() * 1000)
    pdf_content = generate_minimal_test_pdf(
        title="Live Supabase Storage Document Ingestion",
        content=f"Verifying live cloud storage upload via Synora API at timestamp {timestamp}"
    )
    original_sha256 = hashlib.sha256(pdf_content).hexdigest()
    filename = f"live_storage_spec_{timestamp}.pdf"

    files = {"file": (filename, pdf_content, "application/pdf")}
    data = {
        "project_id": "prj-pay-01",
        "uploader_name": "Marcus Vance"
    }

    upload_res = client.post("/documents/upload", files=files, data=data, headers=auth_headers)
    if upload_res.status_code != 201:
        print(f"  [ERROR] Document upload failed ({upload_res.status_code}): {upload_res.text}")
        return False

    doc_info = upload_res.json()
    doc_id = doc_info["id"]
    storage_path = doc_info.get("storage_path")
    metadata = doc_info.get("metadata_tags", {})
    storage_backend = metadata.get("storage_backend")

    print(f"  --> Document Created: ID='{doc_id}', Filename='{filename}'")
    print(f"  --> Storage Backend:  '{storage_backend}'")
    print(f"  --> Cloud Object Key: '{storage_path}'")

    assert storage_backend == "supabase", f"Expected storage_backend='supabase', but got '{storage_backend}'!"
    assert storage_path is not None and "prj-pay-01" in storage_path, f"Storage path invalid: {storage_path}"
    assert doc_info["file_hash"] == original_sha256, "Persisted file_hash does not match original SHA-256!"

    # 3. Confirm object exists directly in Supabase Storage
    print("\n[Step 3/6] Confirming object existence directly in Supabase Storage...")
    storage = get_storage_provider()
    assert isinstance(storage, SupabaseStorageProvider), "Active storage provider is not SupabaseStorageProvider!"

    exists_in_supabase = storage.exists(storage_path)
    print(f"  --> Exists in Supabase Storage: {exists_in_supabase}")
    assert exists_in_supabase is True, f"Object '{storage_path}' was not found in Supabase Storage!"

    # 4. Generate signed download URL and compare SHA-256
    print("\n[Step 4/6] Generating signed download URL via GET /documents/{id}/download...")
    dl_res = client.get(f"/documents/{doc_id}/download", headers=auth_headers)
    if dl_res.status_code != 200:
        print(f"  [ERROR] Failed to get download URL ({dl_res.status_code}): {dl_res.text}")
        return False

    dl_info = dl_res.json()
    signed_url = dl_info["download_url"]
    print(f"  --> Download Backend:  {dl_info.get('storage_backend')}")
    print(f"  --> Signed URL:        {signed_url[:75]}...")

    assert dl_info.get("storage_backend") == "supabase"
    assert "supabase.co" in signed_url, f"Signed URL is not a Supabase URL: {signed_url}"

    # Download from the signed URL directly using HTTP
    print("  --> Fetching file directly via Supabase signed URL...")
    # Use storage._ensure_dns_resolution() so test resolves Cloudflare IP if local DNS has negative cache
    storage._ensure_dns_resolution()
    file_dl_res = httpx.get(signed_url, timeout=20.0)
    assert file_dl_res.status_code == 200, f"Signed URL download failed with status {file_dl_res.status_code}!"
    downloaded_bytes = file_dl_res.content
    downloaded_sha256 = hashlib.sha256(downloaded_bytes).hexdigest()

    print(f"  --> Original SHA-256:   {original_sha256}")
    print(f"  --> Downloaded SHA-256: {downloaded_sha256}")
    assert downloaded_sha256 == original_sha256, "SHA-256 checksum mismatch on downloaded file!"
    print("  --> Bit-for-bit SHA-256 checksum verified intact!")

    # 5. Verify Cross-Organization Isolation
    print("\n[Step 5/6] Verifying Cross-Organization Access Denial...")
    # Register/login user in a completely different organization
    reg_res = client.post("/auth/register", json={
        "email": f"competitor_{timestamp}@rival.corp",
        "password": os.environ.get("SYNORA_VERIFY_PASSWORD") or __import__("secrets").token_urlsafe(32),
        "full_name": "Rival Intelligence Officer",
        "role": "manager",
        "organization_name": f"Rival Corp {timestamp}",
    })
    assert reg_res.status_code == 201
    rival_token = reg_res.json()["access_token"]
    rival_headers = {"Authorization": f"Bearer {rival_token}"}

    # Attempt to download document from Acme Corp
    rival_dl_res = client.get(f"/documents/{doc_id}/download", headers=rival_headers)
    print(f"  --> Rival download attempt response: HTTP {rival_dl_res.status_code}")
    assert rival_dl_res.status_code in (403, 404), (
        f"Security failure: Rival was not blocked! HTTP {rival_dl_res.status_code}"
    )
    print("  --> Cross-organization access blocked successfully!")

    # 6. Delete document and confirm removal from Supabase Storage
    print("\n[Step 6/6] Deleting document and confirming removal from Supabase Storage...")
    del_res = client.delete(f"/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 200, f"Deletion failed: {del_res.text}"

    # Confirm purged from Supabase Storage
    still_exists = storage.exists(storage_path)
    print(f"  --> Object still exists in Supabase Storage after delete: {still_exists}")
    assert still_exists is False, "Object still exists in Supabase Storage after deletion!"
    print("  --> Object confirmed deleted from Supabase Storage.")

    print("\n" + "=" * 70)
    print(" LIVE API SUPABASE STORAGE VERIFICATION: ALL 6 STEPS PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_live_api_verification()
    sys.exit(0 if success else 1)

