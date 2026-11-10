import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models import (
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    VerificationRecord,
    AuditLog,
)

from app.core.security import create_access_token

mgr_token = create_access_token({
    "sub": "usr-mgr-01",
    "email": "marcus.vance@acme.corp",
    "role": "manager",
    "org_id": "org-acme-01",
})
client = TestClient(app, headers={"Authorization": f"Bearer {mgr_token}"})


@pytest.fixture(autouse=True)
def clean_test_knowledge():
    """Ensure clean document and knowledge state before and after each test without destroying baseline seeds."""
    db = SessionLocal()
    db.query(VerificationRecord).filter(VerificationRecord.notes != "Baseline seed verification").delete()
    db.query(ExtractedKnowledge).filter(ExtractedKnowledge.document_id.isnot(None)).delete()
    db.query(DocumentChunk).delete()
    db.query(Document).delete()
    if db.query(ExtractedKnowledge).count() == 0:
        db.add(ExtractedKnowledge(
            id="kn-seed-01",
            project_id="prj-pay-01",
            label="Raft Consensus Failover Protocol",
            category="architecture",
            details="Core payments failover consensus mechanism requiring 150ms heartbeat interval.",
            confidence_score=1.0,
            verification_status="verified",
        ))
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(VerificationRecord).filter(VerificationRecord.notes != "Baseline seed verification").delete()
    db.query(ExtractedKnowledge).filter(ExtractedKnowledge.document_id.isnot(None)).delete()
    db.query(DocumentChunk).delete()
    db.query(Document).delete()
    if db.query(ExtractedKnowledge).count() == 0:
        db.add(ExtractedKnowledge(
            id="kn-seed-01",
            project_id="prj-pay-01",
            label="Raft Consensus Failover Protocol",
            category="architecture",
            details="Core payments failover consensus mechanism requiring 150ms heartbeat interval.",
            confidence_score=1.0,
            verification_status="verified",
        ))
    db.commit()
    db.close()


def test_llm_status_endpoint():
    """Verifies that the LLM status endpoint reports active configuration."""
    response = client.get("/api/v1/knowledge/llm-status")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "model" in data
    assert "status" in data
    assert "message" in data


def test_knowledge_extraction_and_grounding():
    """Test extracting tasks, decisions, blockers, dependencies and configs from an ingested runbook."""
    runbook_text = """# Payments Cluster Architecture Specification

## Completed Deliverables
- [x] Migrated payment settlement queue to Apache Kafka cluster
- [x] Configured mutual TLS authentication across validator nodes

## Pending Work
- [ ] Transfer Cloudflare DNS tokens to secondary SRE owner
- [ ] Maybe investigate tentative cross-region latency optimizations

## Architecture & Consensus Protocol
ADR-104: Decided to enforce Raft consensus protocol with a heartbeat interval of 150ms.

## Operational Dependencies
The ingress routing requires vault namespace /prod/settlement for API tokens.

## Known Outage Blockers
CRITICAL RISK: Alex Mercer is the sole engineer with write access to multi-region consensus failover scripts.
"""

    upload_resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("settlement_spec.md", io.BytesIO(runbook_text.encode("utf-8")), "text/markdown")},
        data={"handover_id": "ho-101", "uploader_name": "Alex Mercer"},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    # Trigger extraction
    extract_resp = client.post(
        f"/api/v1/knowledge/extract/{doc_id}",
        json={"actor_name": "Alex Mercer"},
    )
    assert extract_resp.status_code == 201
    nodes = extract_resp.json()
    assert len(nodes) >= 4

    categories = [n["category"] for n in nodes]
    assert "task" in categories
    assert "decision" in categories
    assert "blocker" in categories

    # Verify groundings and source references
    for node in nodes:
        assert node["document_id"] == doc_id
        assert node["chunk_id"] is not None
        assert node["source_quote"] is not None
        assert node["confidence_score"] > 0.0
        assert node["verification_status"] == "unverified"
        assert "metadata_tags" in node
        assert node["metadata_tags"]["source_filename"] == "settlement_spec.md"


def test_low_confidence_uncertainty_flag():
    """Items with ambiguous or tentative wording must have confidence < 0.65 and be flagged for review."""
    vague_text = """# Vague Technical Ideas
- [ ] Maybe investigate tentative cross-region latency optimizations
"""
    upload_resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("vague_ideas.md", io.BytesIO(vague_text.encode("utf-8")), "text/markdown")},
        data={"handover_id": "ho-101"},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    extract_resp = client.post(f"/api/v1/knowledge/extract/{doc_id}")
    assert extract_resp.status_code == 201
    nodes = extract_resp.json()
    assert len(nodes) >= 1

    low_conf_node = [n for n in nodes if n["confidence_score"] < 0.65]
    assert len(low_conf_node) >= 1
    flagged = low_conf_node[0]
    assert flagged["metadata_tags"]["is_flagged_for_review"] is True
    assert flagged["verification_status"] == "unverified"


def test_duplicate_extraction_idempotence():
    """Re-extracting the same document must replace/refresh entities and not duplicate them."""
    text = "ADR-101: Chose PostgreSQL with pgvector for persistent organizational knowledge."
    upload_resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("adr101.md", io.BytesIO(text.encode("utf-8")), "text/markdown")},
        data={"handover_id": "ho-101"},
    )
    doc_id = upload_resp.json()["id"]

    # Extract 1st time
    res1 = client.post(f"/api/v1/knowledge/extract/{doc_id}")
    assert res1.status_code == 201
    count1 = len(res1.json())

    # Extract 2nd time
    res2 = client.post(f"/api/v1/knowledge/extract/{doc_id}")
    assert res2.status_code == 201
    count2 = len(res2.json())

    assert count1 == count2

    # Verify database total matches
    list_resp = client.get(f"/api/v1/knowledge/nodes?document_id={doc_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == count1


def test_manager_verification_lifecycle():
    """Tests verify, modify, and reject transitions by reviewing manager."""
    text = """CRITICAL RISK: Alex Mercer is the sole engineer with write access to multi-region consensus failover scripts."""
    upload_resp = client.post(
        "/api/v1/documents/upload",
        files={"file": ("risk.md", io.BytesIO(text.encode("utf-8")), "text/markdown")},
        data={"handover_id": "ho-101"},
    )
    doc_id = upload_resp.json()["id"]
    extract_resp = client.post(f"/api/v1/knowledge/extract/{doc_id}")
    node = extract_resp.json()[0]
    node_id = node["id"]

    # 1. Action: Verified
    verify_resp = client.patch(
        f"/api/v1/knowledge/nodes/{node_id}/verify",
        json={
            "action": "verified",
            "reviewer_name": "Marcus Vance",
            "notes": "Verified against production AWS IAM roles.",
        },
    )
    assert verify_resp.status_code == 200
    verified_data = verify_resp.json()
    assert verified_data["verification_status"] == "verified"
    assert verified_data["metadata_tags"]["is_flagged_for_review"] is False

    # 2. Action: Modified
    modify_resp = client.patch(
        f"/api/v1/knowledge/nodes/{node_id}/verify",
        json={
            "action": "modified",
            "reviewer_name": "Marcus Vance",
            "notes": "Updated owner and tightened description.",
            "modified_label": "SPOF Risk: Consensus Script Access",
            "modified_details": "Alex Mercer holds exclusive keys to consensus scripts. Marcus Vance shadowed.",
        },
    )
    assert modify_resp.status_code == 200
    mod_data = modify_resp.json()
    assert mod_data["verification_status"] == "modified"
    assert mod_data["label"] == "SPOF Risk: Consensus Script Access"

    # 3. Action: Rejected
    reject_resp = client.patch(
        f"/api/v1/knowledge/nodes/{node_id}/verify",
        json={
            "action": "rejected",
            "reviewer_name": "Marcus Vance",
            "notes": "Access keys have already been rotated to vault.",
        },
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["verification_status"] == "rejected"

    # 4. Filter by status
    rej_list = client.get("/api/v1/knowledge/nodes?verification_status=rejected")
    assert rej_list.status_code == 200
    assert any(n["id"] == node_id for n in rej_list.json())
