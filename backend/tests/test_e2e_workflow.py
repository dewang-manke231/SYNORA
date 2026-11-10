import pytest
import io
import time
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Organization,
    OrganizationMembership,
    Project,
    User,
    Handover,
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    KnowledgeRelationship,
    AuditLog,
)
from app.core.security import create_access_token
from app.services.recreator import RecreatorService


def test_full_synora_lifecycle_e2e(client: TestClient, db_session: Session):
    """
    End-to-End Test covering the complete 8-module lifecycle:
    1. Organization & Project Setup
    2. Leaving Employee Handover Submission (Module 6)
    3. Document Ingestion & Chunking (Module 1)
    4. Knowledge Extraction & Human Verification (Module 2)
    5. Organizational Memory Graph & Vector RAG Assistant (Modules 3 & 4)
    6. Knowledge Loss Radar Scanning & Score Recalculation (Module 5)
    7. Synora Sentinel Handover Verification & Manager Review (Module 7 & 6)
    8. Environment Recreation, Readiness & Onboarding Checklist (Module 8)
    """
    suffix = str(int(time.time() * 1000))
    org_id = f"org-e2e-{suffix}"
    proj_id = f"prj-e2e-{suffix}"

    # -------------------------------------------------------------------------
    # STEP 1: Organization & Project Scaffolding
    # -------------------------------------------------------------------------
    org = Organization(id=org_id, name="Acme E2E Aerospace", slug=f"acme-{suffix}")
    project = Project(
        id=proj_id,
        organization_id=org_id,
        name="Telemetry Flight Control",
        slug=f"telemetry-{suffix}",
        description="Core flight telemetry processing with Raft consensus.",
        repository_url="https://github.com/acme/flight-telemetry",
    )
    user_leaving = User(
        id=f"usr-leaving-{suffix}",
        email=f"pilot_{suffix}@acme.corp",
        full_name="Capt. Scott Kelly",
        role="employee",
    )
    user_manager = User(
        id=f"usr-mgr-{suffix}",
        email=f"director_{suffix}@acme.corp",
        full_name="Director Gene Kranz",
        role="manager",
    )
    mem_leaving = OrganizationMembership(
        id=f"mem-l-{suffix}", organization_id=org_id, user_id=user_leaving.id, role="member"
    )
    mem_mgr = OrganizationMembership(
        id=f"mem-m-{suffix}", organization_id=org_id, user_id=user_manager.id, role="manager"
    )
    db_session.add_all([org, project, user_leaving, user_manager, mem_leaving, mem_mgr])
    db_session.commit()

    mgr_jwt = create_access_token({
        "sub": user_manager.id,
        "email": user_manager.email,
        "role": user_manager.role,
        "org_id": org_id,
    })
    client.headers["Authorization"] = f"Bearer {mgr_jwt}"

    # -------------------------------------------------------------------------
    # STEP 2: Leaving Employee Creates and Submits Handover (Module 6)
    # -------------------------------------------------------------------------
    handover_payload = {
        "project_id": proj_id,
        "employee_name": "Capt. Scott Kelly",
        "role": "Lead Flight Systems Engineer",
        "department": "Aerospace Operations",
        "transition_type": "retirement",
        "key_responsibilities": [
            "Maintain orbital telemetry ingest worker daemons.",
            "Manage failover protocols for cross-datacenter telemetry stream.",
        ],
        "critical_dependencies": [
            "NASA JPL Deep Space Network API Gateway v2",
            "Kafka streaming cluster telemetry-prd-01",
        ],
        "unresolved_blockers": [
            "Bandwidth throttle limit on Ku-band downlink channel.",
        ],
        "completed_tasks": [
            "Upgraded ground station ingestion pipeline to FastAPI async workers.",
            "Documented telemetry schema migration in ADR-109.",
        ],
        "pending_tasks": [
            "Pair with Marcus on antenna calibration procedure.",
        ],
        "important_notes": "Ground receiver buffers automatically drop frames if jitter exceeds 45ms.",
        "recommended_next_actions": [
            "Verify Ku-band encryption keys before launch window.",
        ],
        "repository_links": [
            "https://github.com/acme/flight-telemetry",
        ],
        "documentation_links": [
            "https://wiki.acme.corp/ops/telemetry-runbook",
        ],
        "database_references": [
            "telemetry_primary_pg (PostgreSQL 16)",
        ],
    }

    create_res = client.post("/api/v1/handovers/", json=handover_payload)
    assert create_res.status_code in (200, 201), create_res.text
    handover_data = create_res.json()
    handover_id = handover_data["id"]
    assert handover_data["status"] == "draft"

    # Submit the handover
    submit_res = client.post(f"/api/v1/handovers/{handover_id}/submit")
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "submitted"

    # -------------------------------------------------------------------------
    # STEP 3: Document Ingestion & Chunking Pipeline (Module 1)
    # -------------------------------------------------------------------------
    doc_content = (
        "# Telemetry Flight Control Runbook\n\n"
        "## Architecture Decision Record: ADR-109\n"
        "We decided to migrate the ground telemetry ingest layer from synchronous RabbitMQ "
        "to asynchronous Kafka event streams with Raft consensus.\n\n"
        "## Critical External Dependencies\n"
        "The telemetry pipeline depends on the NASA JPL Deep Space Network API Gateway v2 "
        "and Kafka streaming cluster telemetry-prd-01.\n\n"
        "## Operational Instructions & Setup\n"
        "To launch telemetry services in development, run:\n"
        "cd backend && .venv\\Scripts\\Activate.ps1 && python run.py\n"
        "The service listens on port 8000.\n"
    )

    upload_file = io.BytesIO(doc_content.encode("utf-8"))
    upload_res = client.post(
        "/api/v1/documents/upload",
        data={
            "project_id": proj_id,
            "handover_id": handover_id,
            "source_type": "handover_attachment",
        },
        files={"file": ("telemetry_runbook.md", upload_file, "text/markdown")},
    )
    assert upload_res.status_code in (200, 201), upload_res.text
    doc_data = upload_res.json()
    doc_id = doc_data["id"]
    assert doc_data["chunk_count"] > 0
    assert doc_data["file_hash"] is not None

    # Verify chunks exist
    chunks_res = client.get(f"/api/v1/documents/{doc_id}/chunks")
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()
    assert len(chunks) > 0
    chunk_id = chunks[0]["id"]

    # -------------------------------------------------------------------------
    # STEP 4: Knowledge Extraction & Verification Engine (Module 2)
    # -------------------------------------------------------------------------
    extract_res = client.post(f"/api/v1/knowledge/extract/{doc_id}")
    assert extract_res.status_code in (200, 201), extract_res.text
    extracted_nodes = extract_res.json()
    assert len(extracted_nodes) >= 1

    first_node = extracted_nodes[0]
    node_id = first_node["id"]
    assert first_node["confidence_score"] > 0.0

    # Human manager verifies the extracted knowledge
    verify_res = client.patch(
        f"/api/v1/knowledge/nodes/{node_id}/verify",
        json={
            "action": "verified",
            "reviewer_name": "Director Gene Kranz",
            "notes": "Verified against flight telemetry specification.",
        },
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["verification_status"] == "verified"

    # -------------------------------------------------------------------------
    # STEP 5: Organizational Memory Graph & Vector RAG (Modules 3 & 4)
    # -------------------------------------------------------------------------
    # Graph Retrieval
    graph_res = client.get(f"/api/v1/knowledge/graph?project_id={proj_id}")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert len(graph_data["nodes"]) >= 1
    assert "edges" in graph_data

    # RAG Assistant Question Answering
    query_res = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "What architecture decision was made for ground telemetry ingest?",
            "project_id": proj_id,
        },
    )
    assert query_res.status_code == 200
    answer_data = query_res.json()
    assert "answer" in answer_data
    assert len(answer_data["answer"]) > 10
    # Citations should be present or verified
    assert "citations" in answer_data

    # Out of domain / unsupported query should return honest uncertainty
    odd_res = client.post(
        "/api/v1/knowledge/query",
        json={
            "query": "What is the secret recipe for Martian sourdough bread?",
            "project_id": proj_id,
        },
    )
    assert odd_res.status_code == 200
    odd_data = odd_res.json()
    assert odd_data["confidence"] <= 0.65 or "insufficient" in odd_data["answer"].lower() or "not documented" in odd_data["answer"].lower()

    # -------------------------------------------------------------------------
    # STEP 6: Knowledge Loss Radar Scanning & Score Calculation (Module 5)
    # -------------------------------------------------------------------------
    radar_scan_res = client.post(
        "/api/v1/radar/scan",
        json={"project_id": proj_id, "actor_name": "Radar Auditor"},
    )
    assert radar_scan_res.status_code == 200

    overview_res = client.get(f"/api/v1/radar/overview?project_id={proj_id}")
    assert overview_res.status_code == 200
    radar_overview = overview_res.json()
    assert "average_coverage_score" in radar_overview
    assert "scoring_formula" in radar_overview

    # Retrieve risks and remediate one
    risks_res = client.get(f"/api/v1/radar/risks?project_id={proj_id}")
    assert risks_res.status_code == 200
    risks = risks_res.json()
    if risks:
        risk_to_fix = risks[0]
        rem_res = client.patch(
            f"/api/v1/radar/risks/{risk_to_fix['id']}",
            json={
                "resolution_notes": "Assigned Marcus Vance as secondary maintainer.",
                "resolved_by": "Director Gene Kranz",
            },
        )
        assert rem_res.status_code == 200
        rem_data = rem_res.json()
        assert rem_data["risk"]["is_resolved"] is True
        assert "updated_coverage_score" in rem_data

    # -------------------------------------------------------------------------
    # STEP 7: Synora Sentinel Audit & Manager Approval (Modules 7 & 6)
    # -------------------------------------------------------------------------
    sentinel_scan_res = client.post(
        "/api/v1/sentinel/scan",
        json={"project_id": proj_id, "handover_id": handover_id},
    )
    assert sentinel_scan_res.status_code == 200

    sentinel_overview_res = client.get("/api/v1/sentinel/overview")
    assert sentinel_overview_res.status_code == 200
    sentinel_data = sentinel_overview_res.json()
    assert "average_integrity_score" in sentinel_data

    # Manager approves the handover
    approve_res = client.post(
        f"/api/v1/handovers/{handover_id}/approve",
        json={
            "actor_name": "Director Gene Kranz",
            "notes": "All telemetry specs verified, shadow onboarding completed.",
        },
    )
    assert approve_res.status_code == 200
    approved_handover = approve_res.json()
    assert approved_handover["status"] == "verified"
    assert approved_handover["reviewed_by"] == "Director Gene Kranz"

    # Export Handover Dossier as clean Markdown
    export_res = client.get(f"/api/v1/handovers/{handover_id}/export")
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "markdown_content" in export_data
    assert "Capt. Scott Kelly" in export_data["markdown_content"]
    assert "Director Gene Kranz" in export_data["markdown_content"]

    # -------------------------------------------------------------------------
    # STEP 8: Environment Recreator, Readiness & Onboarding Checklist (Module 8)
    # -------------------------------------------------------------------------
    req_upload = client.post(
        "/api/v1/documents/upload",
        data={"project_id": proj_id},
        files={"file": ("requirements.txt", f"fastapi>=0.110  # e2e-{suffix}\n".encode(), "text/plain")},
    )
    assert req_upload.status_code == 201, req_upload.text
    pkg_upload = client.post(
        "/api/v1/documents/upload",
        data={"project_id": proj_id},
        files={"file": ("package.json", f'{{"version":"{suffix}","dependencies":{{"react":"19"}},"devDependencies":{{"vite":"8"}},"scripts":{{"dev":"vite"}}}}'.encode(), "application/json")},
    )
    assert pkg_upload.status_code == 201, pkg_upload.text
    env_example_upload = client.post(
        "/api/v1/documents/upload",
        data={"project_id": proj_id},
        files={"file": (".env.example", f"GEMINI_API_KEY=example-{suffix}\n".encode(), "text/plain")},
    )
    assert env_example_upload.status_code == 201, env_example_upload.text
    # Uploaded-project manifest inspection
    inspect_res = client.get(f"/api/v1/recreator/inspect?project_id={proj_id}")
    assert inspect_res.status_code == 200
    inspect_data = inspect_res.json()
    assert "detected_frameworks" in inspect_data
    assert len(inspect_data["manifest_files_found"]) > 0

    # Generate development blueprint
    gen_res = client.post(
        "/api/v1/recreator/generate",
        json={"project_id": proj_id, "actor_name": "Incoming Onboarding Engineer"},
    )
    assert gen_res.status_code == 200
    blueprint_data = gen_res.json()
    assert len(blueprint_data["powershell_quickstart"]) > 0
    assert len(blueprint_data["bash_quickstart"]) > 0

    # Readiness assessment
    readiness_res = client.get(f"/api/v1/recreator/readiness?project_id={proj_id}")
    assert readiness_res.status_code == 200
    readiness_data = readiness_res.json()
    assert readiness_data["readiness_score"] >= 80.0
    assert len(readiness_data["prerequisites"]) >= 2

    # Checklist retrieval and step completion
    chk_res = client.get(f"/api/v1/recreator/checklist?project_id={proj_id}")
    assert chk_res.status_code == 200
    checklist_data = chk_res.json()
    assert checklist_data["total_steps"] == 7
    first_step_id = checklist_data["steps"][0]["id"]

    # Incoming engineer marks first step completed
    step_update_res = client.post(
        "/api/v1/recreator/checklist",
        json={
            "project_id": proj_id,
            "step_id": first_step_id,
            "is_completed": True,
            "actor_name": "Incoming Engineer Marcus",
            "notes": "Verified local Python 3.12 and git repository state.",
        },
    )
    assert step_update_res.status_code == 200
    updated_chk = step_update_res.json()
    assert updated_chk["completed_steps"] == 1
    assert updated_chk["steps"][0]["is_completed"] is True
    assert updated_chk["steps"][0]["completed_by"] == "Incoming Engineer Marcus"

    # Secret redaction check on export
    env_export_res = client.get(f"/api/v1/recreator/export/env?project_id={proj_id}")
    assert env_export_res.status_code == 200
    env_text = env_export_res.text
    # Guarantee no actual secrets or API keys are exposed
    assert "your_gemini_api_key_here" in env_text or "default_value" in env_text
    assert "AIzaSy" not in env_text  # Real Google API key prefix must never be present

    # Docker compose export check
    docker_export_res = client.get(f"/api/v1/recreator/export/docker?project_id={proj_id}")
    assert docker_export_res.status_code == 200
    assert "services:" in docker_export_res.text
    assert "synora-backend" in docker_export_res.text
