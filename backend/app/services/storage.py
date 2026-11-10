import os
import re
import socket
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict, Any
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fallback Cloudflare anycast IPs for Supabase API gateway in case of local network DNS resolution failure
SUPABASE_CLOUDFLARE_IPS = ["104.18.38.10", "172.64.149.246"]


class StorageProvider(ABC):
    """Abstract storage provider interface supporting Local and Supabase Storage."""

    @abstractmethod
    def save(self, destination_path: str, content: bytes, content_type: Optional[str] = None) -> str:
        """Saves raw bytes and returns the stored relative path or object key."""
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Reads raw bytes from the given path or object key."""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Deletes the stored file or object."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Checks if the stored file or object exists."""
        pass

    @abstractmethod
    def create_signed_url(self, path: str, expires_in: int = 3600) -> str:
        """Generates a secure, short-lived signed URL for downloading the object."""
        pass

    @abstractmethod
    def list_objects(self, prefix: str = "") -> List[str]:
        """Lists stored object keys matching the prefix."""
        pass


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage implementation with directory traversal protection."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.UPLOAD_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        clean_path = relative_path.lstrip("/\\")
        full_path = (self.base_dir / clean_path).resolve()
        if not full_path.is_relative_to(self.base_dir):
            raise ValueError("Directory traversal attempt detected.")
        return full_path

    def save(self, destination_path: str, content: bytes, content_type: Optional[str] = None) -> str:
        target_path = self._resolve_safe_path(destination_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(content)
        return str(target_path.relative_to(self.base_dir).as_posix())

    def read(self, path: str) -> bytes:
        target_path = self._resolve_safe_path(path)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(target_path, "rb") as f:
            return f.read()

    def delete(self, path: str) -> bool:
        try:
            target_path = self._resolve_safe_path(path)
            if target_path.exists():
                target_path.unlink()
                return True
            return False
        except Exception:
            return False

    def exists(self, path: str) -> bool:
        try:
            target_path = self._resolve_safe_path(path)
            return target_path.is_file()
        except Exception:
            return False

    def create_signed_url(self, path: str, expires_in: int = 3600) -> str:
        # For local development, point to the authenticated API download endpoint
        clean = path.lstrip("/\\").replace("\\", "/")
        return f"/api/v1/documents/download-stream?path={clean}"

    def list_objects(self, prefix: str = "") -> List[str]:
        results = []
        clean_prefix = prefix.lstrip("/\\").replace("\\", "/")
        for root, _, files in os.walk(self.base_dir):
            for file in files:
                full_path = Path(root) / file
                rel = full_path.relative_to(self.base_dir).as_posix()
                if not clean_prefix or rel.startswith(clean_prefix):
                    results.append(rel)
        return results


def derive_supabase_project_ref(db_url: str) -> Optional[str]:
    """Extracts the 20-character Supabase project reference from DATABASE_URL."""
    if not db_url:
        return None
    # Check for user pattern: postgres.PROJECT_REF
    match_user = re.search(r"postgres\.([a-z0-9]{15,30})", db_url)
    if match_user:
        return match_user.group(1)
    # Check for host pattern: db.PROJECT_REF.supabase.co
    match_host = re.search(r"db\.([a-z0-9]{15,30})\.supabase\.co", db_url)
    if match_host:
        return match_host.group(1)
    return None


class SupabaseStorageProvider(StorageProvider):
    """
    Cloud persistent document storage powered by Supabase Storage REST API.
    Enforces private bucket isolation and signed token generation.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        raw_db_url = getattr(settings, "DATABASE_URL", "")
        project_ref = derive_supabase_project_ref(raw_db_url)

        # Resolve and normalize Supabase origin URL
        raw_url = supabase_url or getattr(settings, "SUPABASE_URL", None) or (f"https://{project_ref}.supabase.co" if project_ref else "http://localhost:8000")
        clean_url = raw_url.split("/rest/")[0].split("/rest")[0].split("/storage/")[0].rstrip("/")
        self.supabase_url = clean_url

        self.service_role_key = service_role_key or getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket_name = bucket_name or getattr(settings, "SUPABASE_STORAGE_BUCKET", "synora-documents")
        self.project_ref = project_ref

        # DNS resolver hook to guarantee resolution of Cloudflare SNI on Windows networks
        self._ensure_dns_resolution()

        # Build reusable HTTP client with pool limits and timeout
        self.client = httpx.Client(
            base_url=self.supabase_url,
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers=self._auth_headers(),
        )

        # Ensure private bucket exists
        self._ensure_bucket()

    def _ensure_dns_resolution(self):
        """Ensures that the Supabase domain resolves even when local ISP/LAN DNS caches negatively."""
        if not self.project_ref:
            return
        domain = f"{self.project_ref}.supabase.co"
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            # Install fallback resolver hook
            orig_getaddrinfo = socket.getaddrinfo

            def _patched_getaddrinfo(host, port, *args, **kwargs):
                if host == domain:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (SUPABASE_CLOUDFLARE_IPS[0], port))]
                return orig_getaddrinfo(host, port, *args, **kwargs)

            socket.getaddrinfo = _patched_getaddrinfo

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.service_role_key:
            headers["Authorization"] = f"Bearer {self.service_role_key}"
            headers["apikey"] = self.service_role_key
        return headers

    def _ensure_bucket(self):
        """Idempotently creates the private bucket if it does not already exist."""
        # 1. Try via SQL if we have a direct PostgreSQL connection
        try:
            from app.core.database import SessionLocal, is_sqlite
            if not is_sqlite:
                from sqlalchemy import text
                db = SessionLocal()
                try:
                    db.execute(text(
                        f"INSERT INTO storage.buckets (id, name, public) VALUES ('{self.bucket_name}', '{self.bucket_name}', false) ON CONFLICT (id) DO NOTHING;"
                    ))
                    db.commit()
                finally:
                    db.close()
        except Exception as e:
            logger.debug(f"Direct SQL bucket initialization note: {e}")

        # 2. Try via Storage REST API if service_role_key is configured
        if self.service_role_key:
            try:
                res = self.client.get(f"/storage/v1/bucket/{self.bucket_name}")
                if res.status_code == 404:
                    self.client.post(
                        "/storage/v1/bucket",
                        json={"id": self.bucket_name, "name": self.bucket_name, "public": False},
                    )
            except Exception as e:
                logger.warning(f"Supabase REST bucket check warning: {e}")

    def save(self, destination_path: str, content: bytes, content_type: Optional[str] = None) -> str:
        clean_path = destination_path.lstrip("/\\").replace("\\", "/")
        c_type = content_type or "application/octet-stream"

        if not self.service_role_key:
            raise RuntimeError("Cannot upload to Supabase Storage: SUPABASE_SERVICE_ROLE_KEY is not configured.")

        url = f"/storage/v1/object/{self.bucket_name}/{clean_path}"
        headers = {
            "Content-Type": c_type,
            "x-upsert": "true",
        }

        res = self.client.post(url, content=content, headers=headers)
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Supabase Storage upload failed ({res.status_code}): {res.text}")

        return clean_path

    def read(self, path: str) -> bytes:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        if not self.service_role_key:
            raise RuntimeError("Cannot download from Supabase Storage: SUPABASE_SERVICE_ROLE_KEY is not configured.")

        url = f"/storage/v1/object/authenticated/{self.bucket_name}/{clean_path}"
        res = self.client.get(url)
        if res.status_code == 404:
            raise FileNotFoundError(f"Supabase Storage object not found: {clean_path}")
        if res.status_code != 200:
            raise RuntimeError(f"Supabase Storage download failed ({res.status_code}): {res.text}")

        return res.content

    def delete(self, path: str) -> bool:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        if not self.service_role_key:
            return False

        url = f"/storage/v1/object/{self.bucket_name}/{clean_path}"
        res = self.client.delete(url)
        return res.status_code in (200, 204)

    def exists(self, path: str) -> bool:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        if not self.service_role_key:
            return False

        url = f"/storage/v1/object/info/authenticated/{self.bucket_name}/{clean_path}"
        res = self.client.get(url)
        return res.status_code == 200

    def create_signed_url(self, path: str, expires_in: int = 3600) -> str:
        clean_path = path.lstrip("/\\").replace("\\", "/")
        if not self.service_role_key:
            raise RuntimeError("Cannot sign URL: SUPABASE_SERVICE_ROLE_KEY is not configured.")

        url = f"/storage/v1/object/sign/{self.bucket_name}/{clean_path}"
        res = self.client.post(url, json={"expiresIn": expires_in})
        if res.status_code != 200:
            raise RuntimeError(f"Supabase Storage signed URL creation failed ({res.status_code}): {res.text}")

        data = res.json()
        signed_rel = data.get("signedURL")
        if not signed_rel:
            raise RuntimeError(f"Signed URL missing in Supabase response: {data}")

        if not signed_rel.startswith("/storage/v1"):
            signed_rel = "/storage/v1" + (signed_rel if signed_rel.startswith("/") else f"/{signed_rel}")

        return f"{self.supabase_url}{signed_rel}"

    def list_objects(self, prefix: str = "") -> List[str]:
        clean_prefix = prefix.lstrip("/\\").replace("\\", "/")
        if not self.service_role_key:
            return []

        url = f"/storage/v1/object/list/{self.bucket_name}"
        res = self.client.post(url, json={"prefix": clean_prefix, "limit": 100})
        if res.status_code != 200:
            return []

        items = res.json()
        return [item.get("name") for item in items if isinstance(item, dict) and item.get("name")]


_storage_instance: Optional[StorageProvider] = None


def get_storage_provider() -> StorageProvider:
    global _storage_instance
    if _storage_instance is None:
        provider_type = getattr(settings, "STORAGE_PROVIDER", "supabase").lower()
        has_supabase_key = bool(getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None))

        if provider_type == "supabase":
            if not has_supabase_key:
                raise RuntimeError(
                    "STORAGE_PROVIDER is configured as 'supabase', but SUPABASE_SERVICE_ROLE_KEY is missing from environment. "
                    "Refusing to silently fall back to local storage in production."
                )
            # Explicit failure on error: Never silently fall back to local storage in production
            _storage_instance = SupabaseStorageProvider()
        else:
            _storage_instance = LocalStorageProvider()

    return _storage_instance
