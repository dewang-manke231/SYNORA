import hashlib
import io
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from sqlalchemy.orm import Session
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import settings
from app.core.embeddings import get_embedding_provider
from app.models import Document, DocumentChunk, Handover, Project, AuditLog, User
from app.services.storage import get_storage_provider


# File configuration & security constraints
ALLOWED_EXTENSIONS = {
    ".pdf", ".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss",
    ".sql", ".java", ".go", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift", ".kt",
    ".vue", ".svelte", ".xml", ".ini", ".cfg", ".conf", ".dockerfile",
}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/markdown",
    "text/x-markdown",
    "text/plain",
    "application/json",
    "application/x-yaml",
    "text/yaml",
    "text/x-python",
    "text/javascript",
    "application/javascript",
    "text/html",
    "text/css",
    "application/octet-stream",  # Often sent for .md/.txt on Windows/macOS
}
MAX_FILE_SIZE = settings.MAX_UPLOAD_SIZE_BYTES  # 25 MB


class IngestionError(Exception):
    """Base exception for document ingestion failures."""
    pass


class UnsupportedFileError(IngestionError):
    """Raised when file extension or MIME type is not allowed."""
    pass


class FileSizeLimitError(IngestionError):
    """Raised when file exceeds size threshold."""
    pass


class DuplicateDocumentError(IngestionError):
    """Raised when an identical file already exists."""
    def __init__(self, message: str, existing_document_id: str):
        super().__init__(message)
        self.existing_document_id = existing_document_id


class IngestionService:
    def __init__(
        self,
        chunk_size_words: int = 350,
        chunk_overlap_words: int = 50,
    ):
        self.chunk_size_words = chunk_size_words
        self.chunk_overlap_words = chunk_overlap_words
        self.storage = get_storage_provider()

    @staticmethod
    def validate_file(filename: str, content_type: str, file_bytes: bytes) -> None:
        """Validates extension, MIME type, and size. Rejects executable/suspicious files."""
        if not filename or "." not in filename:
            raise UnsupportedFileError("File name is missing or has no extension.")

        ext = ".txt" if filename.lower() == ".env.example" else Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileError(
                f"Unsupported file format '{ext}'. Only PDF, Markdown (.md), and Text (.txt) files are supported."
            )

        # Enforce file size limit
        file_size = len(file_bytes)
        if file_size == 0:
            raise UnsupportedFileError("Uploaded file is empty (0 bytes).")
        if file_size > MAX_FILE_SIZE:
            max_mb = MAX_FILE_SIZE // (1024 * 1024)
            raise FileSizeLimitError(f"File size exceeds the {max_mb} MB limit (received {file_size / (1024*1024):.2f} MB).")

        # Sanitize filename (prevent directory traversal in uploaded filename)
        safe_name = os.path.basename(filename)
        if safe_name != filename and not (filename.startswith("C:\\") or "/" in filename):
            # Only flag if suspicious traversal chars
            if ".." in filename:
                raise UnsupportedFileError("Invalid characters in filename.")

    @staticmethod
    def compute_sha256(file_bytes: bytes) -> str:
        """Computes SHA-256 hash of file content."""
        return hashlib.sha256(file_bytes).hexdigest()

    def extract_text_from_pdf(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """Extracts text page by page from PDF using pypdf."""
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                try:
                    # Attempt decrypt with empty password
                    reader.decrypt("")
                except Exception:
                    raise IngestionError("PDF is password protected and cannot be extracted.")

            pages: List[Dict[str, Any]] = []
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                # Sanitize null bytes
                page_text = page_text.replace("\x00", "").strip()
                pages.append({
                    "page_number": idx + 1,
                    "text": page_text,
                })
            return pages
        except PdfReadError as e:
            raise IngestionError(f"Corrupt or malformed PDF file: {str(e)}")
        except Exception as e:
            raise IngestionError(f"PDF extraction failed: {str(e)}")

    def extract_text_from_text(self, file_bytes: bytes) -> str:
        """Extracts raw text from Markdown or plain text files."""
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = file_bytes.decode("latin-1")
            except Exception as e:
                raise IngestionError(f"Failed to decode text file with UTF-8 / Latin-1: {str(e)}")
        return text.replace("\x00", "").strip()

    def chunk_text(
        self,
        document_id: str,
        filename: str,
        pages_or_text: Any,
        is_pdf: bool,
    ) -> List[Dict[str, Any]]:
        """
        Splits text into chunks preserving page number for PDF and order index.
        Uses sliding window word chunking with overlap.
        """
        chunks: List[Dict[str, Any]] = []
        chunk_idx = 0

        if is_pdf:
            # pages_or_text is List[Dict[str, Any]] with page_number and text
            for page_info in pages_or_text:
                page_num = page_info["page_number"]
                raw_page_text = page_info["text"]
                if not raw_page_text:
                    continue

                words = raw_page_text.split()
                if not words:
                    continue

                if len(words) <= self.chunk_size_words:
                    chunk_text = " ".join(words)
                    chunks.append({
                        "chunk_index": chunk_idx,
                        "chunk_text": chunk_text,
                        "token_count": int(len(words) * 1.3),
                        "page_number": page_num,
                        "metadata_tags": {
                            "source_filename": filename,
                            "document_id": document_id,
                            "chunk_index": chunk_idx,
                            "page_number": page_num,
                            "word_count": len(words),
                        },
                    })
                    chunk_idx += 1
                else:
                    # Sliding window inside the page
                    step = max(1, self.chunk_size_words - self.chunk_overlap_words)
                    for start in range(0, len(words), step):
                        end = min(start + self.chunk_size_words, len(words))
                        chunk_words = words[start:end]
                        if not chunk_words:
                            break
                        chunk_text = " ".join(chunk_words)
                        chunks.append({
                            "chunk_index": chunk_idx,
                            "chunk_text": chunk_text,
                            "token_count": int(len(chunk_words) * 1.3),
                            "page_number": page_num,
                            "metadata_tags": {
                                "source_filename": filename,
                                "document_id": document_id,
                                "chunk_index": chunk_idx,
                                "page_number": page_num,
                                "word_count": len(chunk_words),
                            },
                        })
                        chunk_idx += 1
                        if end >= len(words):
                            break
        else:
            # Markdown / TXT: chunk across whole document
            raw_text = str(pages_or_text)
            words = raw_text.split()
            if not words:
                return []

            step = max(1, self.chunk_size_words - self.chunk_overlap_words)
            for start in range(0, len(words), step):
                end = min(start + self.chunk_size_words, len(words))
                chunk_words = words[start:end]
                if not chunk_words:
                    break
                chunk_text = " ".join(chunk_words)
                chunks.append({
                    "chunk_index": chunk_idx,
                    "chunk_text": chunk_text,
                    "token_count": int(len(chunk_words) * 1.3),
                    "page_number": None,
                    "metadata_tags": {
                        "source_filename": filename,
                        "document_id": document_id,
                        "chunk_index": chunk_idx,
                        "page_number": None,
                        "word_count": len(chunk_words),
                    },
                })
                chunk_idx += 1
                if end >= len(words):
                    break

        return chunks

    def process_and_store_document(
        self,
        db: Session,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        project_id: Optional[str] = None,
        handover_id: Optional[str] = None,
        uploaded_by_id: Optional[str] = None,
        allow_duplicate_link: bool = True,
    ) -> Document:
        """
        Validates, saves file safely to disk/storage, extracts raw text,
        generates chunks, and creates Document + DocumentChunk records.
        """
        # 1. Validation
        self.validate_file(filename, content_type, file_bytes)

        # 2. SHA-256 hash
        file_hash = self.compute_sha256(file_bytes)

        # 3. Resolve project_id and handover relationship
        target_project_id = project_id
        if not target_project_id and handover_id:
            handover = db.query(Handover).filter(Handover.id == handover_id).first()
            if handover and handover.project_id:
                target_project_id = handover.project_id

        if not target_project_id:
            # Fallback to the first available project in system
            first_project = db.query(Project).first()
            if first_project:
                target_project_id = first_project.id
            else:
                raise IngestionError("Cannot upload document: No project found to associate with.")

        # 4. Check duplicate hash
        existing_doc = db.query(Document).filter(Document.file_hash == file_hash).first()
        if existing_doc:
            if existing_doc.handover_id == handover_id:
                raise DuplicateDocumentError(
                    f"An identical file '{existing_doc.filename}' has already been uploaded for this handover.",
                    existing_document_id=existing_doc.id,
                )
            elif allow_duplicate_link and handover_id and not existing_doc.handover_id:
                # Associate existing document with this handover if it wasn't linked
                existing_doc.handover_id = handover_id
                db.commit()
                db.refresh(existing_doc)
                return existing_doc

        # 5. Resolve user FK if valid
        user_fk = None
        if uploaded_by_id:
            user_rec = db.query(User).filter(
                (User.id == uploaded_by_id) | (User.full_name == uploaded_by_id)
            ).first()
            if user_rec:
                user_fk = user_rec.id

        # 6. Resolve organization ID from project for strict multi-tenant storage hierarchy
        project_rec = db.query(Project).filter(Project.id == target_project_id).first()
        org_id = project_rec.organization_id if project_rec and project_rec.organization_id else "default-org"
        doc_uuid = f"doc-{file_hash[:8]}-{int(db.query(Document).count()) + 1}"

        clean_filename = os.path.basename(filename)
        ext = Path(clean_filename).suffix.lower()
        # Storage path organized hierarchically: {organization_id}/{project_id}/{document_id}/{filename}
        storage_rel_path = f"{org_id}/{target_project_id}/{doc_uuid}/{clean_filename}"

        # 7. Save raw bytes to storage provider (Supabase Storage or Local)
        is_supabase = getattr(self.storage, "__class__", None).__name__ == "SupabaseStorageProvider"
        saved_storage_path = self.storage.save(storage_rel_path, file_bytes, content_type=content_type)

        # 8. Create Document record in processing state
        doc = Document(
            id=doc_uuid,
            project_id=target_project_id,
            handover_id=handover_id,
            uploaded_by_id=user_fk,
            filename=clean_filename,
            content_type=content_type,
            file_size=len(file_bytes),
            file_hash=file_hash,
            storage_path=saved_storage_path,
            processing_status="processing",
            raw_text="",
            metadata_tags={
                "original_filename": filename,
                "file_extension": ext,
                "storage_backend": "supabase" if is_supabase else "local",
                "organization_id": org_id,
                "uploader_name": uploaded_by_id,
            },
        )
        db.add(doc)
        db.flush()

        # 9. Extract text and generate chunks
        try:
            is_pdf = ext == ".pdf"
            if is_pdf:
                pages_data = self.extract_text_from_pdf(file_bytes)
                extracted_full_text = "\n\n".join(
                    f"--- Page {p['page_number']} ---\n{p['text']}" for p in pages_data if p['text']
                )
                chunk_records = self.chunk_text(doc.id, clean_filename, pages_data, is_pdf=True)
                doc.metadata_tags["page_count"] = len(pages_data)
            else:
                raw_text = self.extract_text_from_text(file_bytes)
                extracted_full_text = raw_text
                chunk_records = self.chunk_text(doc.id, clean_filename, raw_text, is_pdf=False)
                doc.metadata_tags["line_count"] = len(raw_text.splitlines())

            doc.raw_text = extracted_full_text
            doc.processing_status = "processed"
            doc.metadata_tags["chunk_count"] = len(chunk_records)
            doc.metadata_tags["total_words"] = len(extracted_full_text.split())

            # Insert chunks with embeddings
            embedder = get_embedding_provider()
            for c in chunk_records:
                emb = embedder.embed_text(c["chunk_text"])
                chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=c["chunk_index"],
                    chunk_text=c["chunk_text"],
                    token_count=c["token_count"],
                    page_number=c.get("page_number"),
                    metadata_tags=c["metadata_tags"],
                    embedding_json=emb,
                    embedding_vector=emb,
                )
                db.add(chunk)

            # Audit log
            audit = AuditLog(
                user_id=user_fk,
                action="document.uploaded",
                entity_type="document",
                entity_id=doc.id,
                details={
                    "actor_name": uploaded_by_id,
                    "filename": clean_filename,
                    "file_size": len(file_bytes),
                    "chunks_created": len(chunk_records),
                    "handover_id": handover_id,
                    "project_id": target_project_id,
                },
            )
            db.add(audit)
            db.commit()
            db.refresh(doc)
            return doc

        except Exception as exc:
            # Gracefully handle extraction failure
            db.rollback()
            # Mark document as failed
            doc.processing_status = "failed"
            doc.error_message = str(exc)
            db.add(doc)
            db.commit()
            db.refresh(doc)
            raise IngestionError(f"Document text extraction failed: {str(exc)}")

    def delete_document(self, db: Session, document_id: str, actor_id: Optional[str] = None) -> bool:
        """Deletes raw file from storage, document and all cascaded chunks from DB."""
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return False

        # Delete raw file from storage
        if doc.storage_path:
            self.storage.delete(doc.storage_path)

        # Resolve user FK if valid
        user_fk = None
        if actor_id:
            user_rec = db.query(User).filter(
                (User.id == actor_id) | (User.full_name == actor_id)
            ).first()
            if user_rec:
                user_fk = user_rec.id

        # Audit log before deletion
        audit = AuditLog(
            user_id=user_fk,
            action="document.deleted",
            entity_type="document",
            entity_id=doc.id,
            details={
                "actor_name": actor_id,
                "filename": doc.filename,
                "project_id": doc.project_id,
                "handover_id": doc.handover_id,
            },
        )
        db.add(audit)

        # Cascading deletes chunks
        db.delete(doc)
        db.commit()
        return True
