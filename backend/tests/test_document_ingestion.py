import io
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app
from app.core.database import SessionLocal
from app.models import Document, DocumentChunk, Handover, Project
from app.core.security import create_access_token

manager_token = create_access_token({"sub": "usr-mgr-01", "email": "marcus.vance@acme.corp", "role": "manager", "org_id": "org-acme-01"})
client = TestClient(app, headers={"Authorization": f"Bearer {manager_token}"})


@pytest.fixture(autouse=True)
def clean_test_documents():
    """Ensure a clean document state before and after running each test."""
    db = SessionLocal()
    db.query(DocumentChunk).delete()
    db.query(Document).delete()
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(DocumentChunk).delete()
    db.query(Document).delete()
    db.commit()
    db.close()


def create_sample_pdf_bytes() -> bytes:
    """Helper to generate a valid multi-page PDF in memory."""
    writer = PdfWriter()
    # Add page 1
    writer.add_blank_page(width=612, height=792)
    # Write some stream text onto pages
    # To have extractable text in pure pypdf, we can use annotation or create text object
    # Or write a minimal PDF structure with text stream
    # A standard minimal PDF with text:
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 55 >> stream\n"
        b"BT /F1 12 Tf 72 712 Td (Synora Raft Consensus Architecture Runbook) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000244 00000 n \n0000000350 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n425\n%%EOF"
    )
    return pdf_content


def test_markdown_document_upload_and_chunking():
    """Test uploading a Markdown technical runbook, text extraction, and chunk generation."""
    md_content = """# Payment Settlement Consensus Runbook

## Overview
This runbook describes the Raft consensus replication protocol used by the Core Infrastructure.

### Operational Guidance
1. If cross-region latency exceeds 120ms, do not restart Raft leader pods.
2. Webhook replay tokens are stored in the Vault namespace `/prod/settlement`.
3. In case of split-brain scenario, run the emergency quorum verification script.
"""
    files = {
        "file": ("consensus_runbook.md", io.BytesIO(md_content.encode("utf-8")), "text/markdown"),
    }
    data = {
        "handover_id": "ho-101",
        "uploader_name": "Alex Mercer",
    }

    response = client.post("/api/v1/documents/upload", files=files, data=data)
    assert response.status_code == 201
    doc_data = response.json()

    assert doc_data["filename"] == "consensus_runbook.md"
    assert doc_data["content_type"] == "text/markdown"
    assert doc_data["handover_id"] == "ho-101"
    assert doc_data["processing_status"] == "processed"
    assert doc_data["chunk_count"] >= 1
    assert "Raft consensus" in doc_data["raw_text"]
    assert doc_data["file_hash"] is not None

    doc_id = doc_data["id"]

    # Verify chunks endpoint
    chunks_resp = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert len(chunks) == doc_data["chunk_count"]
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["document_id"] == doc_id
    assert "consensus" in chunks[0]["chunk_text"].lower()


def test_plain_text_document_upload():
    """Test uploading a plain text file."""
    txt_content = "Database connection pool settings:\nMax connections: 100\nTimeout: 30s\nSSL Mode: require"
    files = {
        "file": ("db_config.txt", io.BytesIO(txt_content.encode("utf-8")), "text/plain"),
    }
    data = {
        "handover_id": "ho-101",
    }

    response = client.post("/api/v1/documents/upload", files=files, data=data)
    assert response.status_code == 201
    doc_data = response.json()
    assert doc_data["filename"] == "db_config.txt"
    assert doc_data["processing_status"] == "processed"
    assert "SSL Mode: require" in doc_data["raw_text"]


def test_pdf_document_upload_and_extraction():
    """Test uploading a valid PDF document with page number tracking."""
    pdf_bytes = create_sample_pdf_bytes()
    files = {
        "file": ("consensus_arch.pdf", io.BytesIO(pdf_bytes), "application/pdf"),
    }
    data = {
        "handover_id": "ho-102",
    }

    response = client.post("/api/v1/documents/upload", files=files, data=data)
    assert response.status_code == 201
    doc_data = response.json()
    assert doc_data["filename"] == "consensus_arch.pdf"
    assert doc_data["content_type"] == "application/pdf"
    assert doc_data["processing_status"] == "processed"
    assert "Synora Raft Consensus Architecture Runbook" in doc_data["raw_text"]

    # Verify chunk has page_number
    chunks_resp = client.get(f"/api/v1/documents/{doc_data['id']}/chunks")
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert len(chunks) >= 1
    assert chunks[0]["page_number"] == 1


def test_duplicate_file_rejection():
    """Uploading an identical file twice to the same handover should return 409 Conflict."""
    content = "Unique file content for duplicate testing: 981273918237198237"
    files1 = {
        "file": ("dup_test.txt", io.BytesIO(content.encode("utf-8")), "text/plain"),
    }
    resp1 = client.post("/api/v1/documents/upload", files=files1, data={"handover_id": "ho-101"})
    assert resp1.status_code == 201

    # Upload exact same content again
    files2 = {
        "file": ("dup_test.txt", io.BytesIO(content.encode("utf-8")), "text/plain"),
    }
    resp2 = client.post("/api/v1/documents/upload", files=files2, data={"handover_id": "ho-101"})
    assert resp2.status_code == 409
    err = resp2.json()["detail"]
    assert "identical file" in err["message"].lower()


def test_invalid_file_extension_rejection():
    """Test that unauthorized executable extensions are rejected with 400."""
    sh_content = "#!/bin/bash\necho 'malicious script'"
    files = {
        "file": ("deploy.sh", io.BytesIO(sh_content.encode("utf-8")), "application/x-sh"),
    }
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 400
    assert "unsupported file format" in response.json()["detail"].lower()


def test_empty_file_rejection():
    """Test that empty 0-byte files are rejected."""
    files = {
        "file": ("empty.txt", io.BytesIO(b""), "text/plain"),
    }
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_document_list_and_filter():
    """Test listing documents with filtering by handover_id."""
    client.post(
        "/api/v1/documents/upload",
        files={"file": ("list_test_101.txt", io.BytesIO(b"Doc for 101"), "text/plain")},
        data={"handover_id": "ho-101"},
    )
    client.post(
        "/api/v1/documents/upload",
        files={"file": ("list_test_102.txt", io.BytesIO(b"Doc for 102"), "text/plain")},
        data={"handover_id": "ho-102"},
    )

    resp = client.get("/api/v1/documents/?handover_id=ho-101")
    assert resp.status_code == 200
    docs = resp.json()
    assert isinstance(docs, list)
    assert len(docs) == 1
    assert docs[0]["handover_id"] == "ho-101"
    assert docs[0]["filename"] == "list_test_101.txt"


def test_document_get_and_delete_lifecycle():
    """Test fetching a document by ID and deleting it along with chunks and storage."""
    temp_content = "Ephemeral document content for deletion test."
    files = {
        "file": ("temp_delete.txt", io.BytesIO(temp_content.encode("utf-8")), "text/plain"),
    }
    create_resp = client.post("/api/v1/documents/upload", files=files, data={"handover_id": "ho-101"})
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    # Verify detail
    get_resp = client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["raw_text"] == temp_content

    # Delete document
    del_resp = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Confirm 404 on subsequent get
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/chunks").status_code == 404
