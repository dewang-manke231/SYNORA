"""Secure ZIP intake and evidence-based project inventory analysis."""
import io
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any, Dict, List, Tuple


MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 2000
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

INDEXABLE_EXTENSIONS = {
    ".pdf", ".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss", ".sql",
    ".java", ".go", ".rs", ".c", ".h", ".cpp",
    ".hpp", ".cs", ".php", ".rb", ".swift", ".kt", ".vue", ".svelte", ".xml",
    ".ini", ".cfg", ".conf", ".dockerfile",
}
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "target",
    ".venv", "venv", "env", "__pycache__", ".next", "coverage", "uploads",
}
SECRET_FILENAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "credentials.json",
    "secrets.json", "service-account.json", "private.key", "server.key",
}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|private[_-]?key|authorization)\b[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\"'\s,;]+)(?P=quote)"
)
TOKEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
]
SECRET_NAME = re.compile(r"(^|[._-])(secret|secrets|credential|credentials|private[-_]?key|id_rsa|id_dsa|token)([._-]|$)")


class ProjectArchiveError(ValueError):
    pass


def _redact_source(text: str) -> str:
    text = SECRET_ASSIGNMENT.sub(lambda m: f"{m.group('prefix')}{m.group('quote')}[REDACTED]{m.group('quote')}", text)
    text = re.sub(r"(?i)(://[^:/\s]+:)[^@/\s]+(@)", r"\1[REDACTED]\2", text)
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub("[REDACTED SECRET]", text)
    return text


def inspect_project_archive(archive_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]:
    """Validate a ZIP without extracting to disk; return redacted, indexable files and findings."""
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ProjectArchiveError("ZIP archive must be non-empty and no larger than 50 MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except (zipfile.BadZipFile, OSError):
        raise ProjectArchiveError("Uploaded file is not a valid ZIP archive.")

    files: List[Dict[str, Any]] = []
    skipped = 0
    total_expanded = 0
    inventory: List[str] = []
    todos: List[Dict[str, str]] = []
    manifests: set[str] = set()
    technologies: set[str] = set()
    try:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ProjectArchiveError("ZIP archive contains too many entries (maximum 2000).")
        for info in infos:
            raw_name = info.filename.replace("\\", "/")
            path = PurePosixPath(raw_name)
            if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
                raise ProjectArchiveError("ZIP contains an unsafe path; no files were imported.")
            if info.is_dir():
                continue
            total_expanded += info.file_size
            if total_expanded > MAX_EXPANDED_BYTES:
                raise ProjectArchiveError("ZIP expands beyond the 100 MB uncompressed limit.")
            if info.file_size > MAX_FILE_BYTES:
                skipped += 1
                continue
            if info.file_size and (info.compress_size == 0 or info.file_size / max(1, info.compress_size) > MAX_COMPRESSION_RATIO):
                raise ProjectArchiveError("ZIP contains an entry with an unsafe compression ratio.")
            parts = tuple(p.lower() for p in path.parts)
            name = path.name.lower()
            if any(p in EXCLUDED_DIRS for p in parts[:-1]) or name in SECRET_FILENAMES or SECRET_NAME.search(name):
                skipped += 1
                continue
            if name.startswith(".env") and name != ".env.example":
                skipped += 1
                continue
            if name.endswith((".pem", ".p12", ".pfx", ".keystore", ".jks")) or name.endswith(".key"):
                skipped += 1
                continue
            ext = path.suffix.lower()
            if name == "dockerfile":
                ext = ".dockerfile"
            if ext not in INDEXABLE_EXTENSIONS:
                skipped += 1
                continue
            # Reject symbolic links; ZIP external attributes encode Unix file type.
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode and (unix_mode & 0o170000) == 0o120000:
                raise ProjectArchiveError("ZIP contains a symbolic link; no files were imported.")
            content = archive.read(info)
            if len(content) != info.file_size:
                raise ProjectArchiveError("ZIP entry size mismatch; archive was rejected.")
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                skipped += 1
                continue
            text = _redact_source(text)
            rel_path = path.as_posix()
            inventory.append(rel_path)
            base = path.name.lower()
            if base in {"readme", "readme.md", "readme.txt", "readme.rst"} or base.startswith("readme."):
                manifests.add("README")
            if base in {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
                manifests.add(base)
                if base == "package.json": technologies.add("Node.js manifest")
            if base in {"requirements.txt", "pyproject.toml", "poetry.lock", "pipfile"}:
                manifests.add(base)
                if base in {"requirements.txt", "pyproject.toml"}: technologies.add("Python manifest")
            if base in {"dockerfile", "docker-compose.yml", "compose.yaml", "compose.yml"}:
                manifests.add(base)
                technologies.add("Docker configuration")
            for line_no, line in enumerate(text.splitlines(), 1):
                if re.search(r"\b(TODO|FIXME|XXX)\b", line, re.IGNORECASE):
                    todos.append({"path": rel_path, "line": str(line_no), "evidence": line.strip()[:300]})
            # Existing document ingestion supplies validation, storage, chunking and embeddings.
            files.append({"path": rel_path, "filename": rel_path, "content": text.encode("utf-8"), "extension": ext})
    finally:
        archive.close()

    if not files:
        raise ProjectArchiveError("ZIP contains no supported, text-readable project files to index.")

    findings: List[Dict[str, str]] = []
    readme_exists = "README" in manifests or any(PurePosixPath(p).name.lower().startswith("readme.") for p in inventory)
    if not readme_exists:
        findings.append({"category": "MISSING_DOCUMENTATION", "severity": "high", "evidence_type": "observed", "source": "ZIP file inventory", "evidence": "No README file was present in the uploaded archive."})
    setup_terms = re.compile(r"(?i)\b(install|installation|setup|getting started|quickstart|run locally)\b")
    setup_documented = any(
        setup_terms.search(entry["content"].decode("utf-8", errors="ignore"))
        for entry in files if PurePosixPath(entry["path"]).suffix.lower() in {".md", ".markdown", ".txt"}
    )
    if not setup_documented:
        findings.append({"category": "MISSING_SETUP_INSTRUCTIONS", "severity": "high", "evidence_type": "observed", "source": "ZIP file inventory", "evidence": "No setup, installation, getting-started, or quickstart instructions were found in indexed documentation."})
    for todo in todos:
        findings.append({"category": "INCOMPLETE_TASK", "severity": "medium", "evidence_type": "observed", "source": f"{todo['path']}:{todo['line']}", "evidence": todo["evidence"]})
    if not any(m in manifests for m in ("package.json", "requirements.txt", "pyproject.toml", "Dockerfile", "docker-compose.yml", "compose.yaml", "compose.yml")):
        findings.append({"category": "DEPENDENCIES_UNKNOWN", "severity": "medium", "evidence_type": "inference", "source": "ZIP file inventory", "evidence": "No recognized dependency or container manifest was found; required dependencies cannot be determined from the uploaded files."})
    elif not any(PurePosixPath(path).name.lower() in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock", "uv.lock"} for path in inventory):
        findings.append({"category": "DEPENDENCIES_UNPINNED", "severity": "low", "evidence_type": "observed", "source": "ZIP file inventory", "evidence": "A dependency manifest exists, but no recognized lockfile was found; exact resolved dependency versions are not established."})
    if not any(p.lower().endswith((".md", ".rst", ".pdf")) for p in inventory):
        findings.append({"category": "ARCHITECTURE_UNKNOWN", "severity": "medium", "evidence_type": "inference", "source": "ZIP file inventory", "evidence": "No architecture or design document was found; component responsibilities and relationships remain unverified."})
    return files, findings, {"indexed_files": inventory, "skipped_files": skipped, "manifests": sorted(manifests), "technologies": sorted(technologies), "todo_count": len(todos)}
