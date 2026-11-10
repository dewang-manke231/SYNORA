import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.models import (
    Project,
    Handover,
    Document,
    SentinelEvent,
    AuditLog,
    utc_now,
)
from app.services.sentinel import SentinelService

from app.core.security import create_access_token

mgr_token = create_access_token({
    "sub": "usr-mgr-01",
    "email": "marcus.vance@acme.corp",
    "role": "manager",
    "org_id": "org-acme-01",
})
client = TestClient(app, headers={"Authorization": f"Bearer {mgr_token}"})


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_sentinel_overview_endpoint():
    """Verify GET /api/v1/sentinel/overview returns aggregate statistics and transparent formula."""
    response = client.get("/api/v1/sentinel/overview")
    assert response.status_code == 200
    data = response.json()
    assert "average_integrity_score" in data
    assert "overall_grade" in data
    assert "total_active_findings" in data
    assert "critical_findings" in data
    assert "projects" in data
    assert "formula" in data
    assert "Sections" in data["formula"]
    assert len(data["projects"]) > 0

    first_prj = data["projects"][0]
    assert "project_id" in first_prj
    assert "integrity_score" in first_prj
    assert "grade" in first_prj


def test_sentinel_risks_listing_and_filtering():
    """Verify GET /api/v1/sentinel/risks supports filtering by project, severity, and category."""
    response = client.get("/api/v1/sentinel/risks")
    assert response.status_code == 200
    risks = response.json()
    assert isinstance(risks, list)
    assert len(risks) >= 3

    # Filter by severity
    res_crit = client.get("/api/v1/sentinel/risks?severity=critical")
    assert res_crit.status_code == 200
    for r in res_crit.json():
        assert r["risk_level"] == "critical"

    # Alias /findings
    alias_res = client.get("/api/v1/sentinel/findings")
    assert alias_res.status_code == 200
    assert len(alias_res.json()) == len(risks)


def test_missing_document_and_section_detection(db_session: Session):
    """
    Verify Sentinel detects:
    - MISSING_DOCUMENTATION when a handover has 0 attached docs
    - INCOMPLETE_HANDOVER_SECTION when mandatory sections are empty
    """
    proj_id = f"prj-sentinel-test-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Telemetry Pipeline Alpha",
        slug="telemetry-alpha",
        bus_factor=2.0,
    )
    db_session.add(project)

    # Handover with 0 docs and empty critical_dependencies
    ho = Handover(
        id=f"ho-incomplete-{int(utc_now().timestamp())}",
        project_id=proj_id,
        employee_name="Jordan Bell",
        role="Senior SRE",
        department="Operations",
        transition_type="resignation",
        status="submitted",
        key_responsibilities=["Maintain telemetry agent collectors."],
        critical_dependencies=[],  # EMPTY SECTION
        completed_tasks=["Upgraded agent daemon to v4."],
        pending_tasks=[],
        unresolved_blockers=[],
    )
    db_session.add(ho)
    db_session.commit()

    # Trigger scan via API
    scan_res = client.post(
        "/api/v1/sentinel/scan",
        json={"handover_id": ho.id, "actor_name": "QA Auditor"},
    )
    assert scan_res.status_code == 200
    data = scan_res.json()
    assert data["new_findings_created"] >= 2

    findings = data["detected_findings"]
    categories = [f["category"] for f in findings]
    assert "MISSING_DOCUMENTATION" in categories
    assert "INCOMPLETE_HANDOVER_SECTION" in categories

    doc_finding = next(f for f in findings if f["category"] == "MISSING_DOCUMENTATION")
    assert "0 attached" in doc_finding["description"]
    assert "Jordan Bell" in doc_finding["description"]

    # Idempotence: scanning again should not duplicate findings
    rescan = client.post("/api/v1/sentinel/scan", json={"handover_id": ho.id})
    assert rescan.status_code == 200
    assert rescan.json()["new_findings_created"] == 0

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_unsupported_completion_and_contradictory_tasks(db_session: Session):
    """
    Verify Sentinel detects:
    - UNSUPPORTED_COMPLETION_CLAIM when a task is claimed complete without evidence
    - CONTRADICTORY_HANDOVER_INFO when a task is in completed AND pending/blockers
    """
    proj_id = f"prj-contradict-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Billing Settlement Gateway",
        slug="billing-gateway",
        bus_factor=2.0,
    )
    db_session.add(project)

    # Handover with contradiction: "Kafka offset migration" is completed AND unresolved blocker
    ho = Handover(
        id=f"ho-contradict-{int(utc_now().timestamp())}",
        project_id=proj_id,
        employee_name="Elena Rostova",
        role="Principal Backend Engineer",
        department="Finance Eng",
        transition_type="internal_transition",
        status="under_review",
        key_responsibilities=["Manage settlement idempotency ledger."],
        critical_dependencies=["Stripe Connect Webhook API"],
        completed_tasks=[
            "Completed multi-region Kafka offset migration to cluster B.",
            "Decommissioned legacy payment bridge.",
        ],
        pending_tasks=[],
        unresolved_blockers=[
            "Kafka offset migration is blocked by missing security certificates in cluster B.",
        ],
        repository_links=["https://github.com/org/billing-gateway"],
    )
    db_session.add(ho)
    db_session.commit()

    # Trigger scan
    scan_res = client.post(
        "/api/v1/sentinel/scan",
        json={"handover_id": ho.id},
    )
    assert scan_res.status_code == 200
    findings = scan_res.json()["detected_findings"]
    categories = [f["category"] for f in findings]

    assert "CONTRADICTORY_HANDOVER_INFO" in categories
    assert "UNSUPPORTED_COMPLETION_CLAIM" in categories

    contradiction = next(f for f in findings if f["category"] == "CONTRADICTORY_HANDOVER_INFO")
    assert "Contradiction detected" in contradiction["description"]
    assert "Kafka offset migration" in contradiction["description"]
    assert contradiction["risk_level"] == "critical"

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_missing_environment_setup_detection(db_session: Session):
    """Verify Sentinel flags handovers lacking environment setup/runbook instructions."""
    proj_id = f"prj-env-test-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Order Fulfillment Microservice",
        slug="order-fulfillment",
        bus_factor=2.0,
    )
    db_session.add(project)

    ho = Handover(
        id=f"ho-env-{int(utc_now().timestamp())}",
        project_id=proj_id,
        employee_name="Carlos Vega",
        role="Software Engineer",
        department="Logistics",
        transition_type="resignation",
        status="draft",
        key_responsibilities=["Fulfillment routing rules."],
        critical_dependencies=["Warehouse Service"],
        completed_tasks=["Refactored routing algorithm."],
        pending_tasks=[],
        unresolved_blockers=[],
        important_notes="Please reach out on Slack for questions.",  # NO ENVIRONMENT SETUP
        repository_links=["https://github.com/org/order-service"],
    )
    db_session.add(ho)
    db_session.commit()

    scan_res = client.post("/api/v1/sentinel/scan", json={"handover_id": ho.id})
    assert scan_res.status_code == 200
    findings = scan_res.json()["detected_findings"]
    categories = [f["category"] for f in findings]

    assert "MISSING_ENVIRONMENT_SETUP" in categories
    env_finding = next(f for f in findings if f["category"] == "MISSING_ENVIRONMENT_SETUP")
    assert "environment setup instructions" in env_finding["description"]

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_remediation_and_change_request_workflow(db_session: Session):
    """
    Verify Sentinel remediation:
    - Resolving finding marks it resolved and updates integrity score
    - Requesting changes transitions submitted handover to changes_requested
    - Audit log entry is recorded
    """
    proj_id = f"prj-rem-test-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Crypto Key Management Service",
        slug="kms-service",
        bus_factor=2.0,
    )
    db_session.add(project)

    ho = Handover(
        id=f"ho-rem-{int(utc_now().timestamp())}",
        project_id=proj_id,
        employee_name="Devon Miller",
        role="Security Architect",
        department="InfraSec",
        transition_type="resignation",
        status="submitted",
        key_responsibilities=["Hardware Security Module (HSM) rotation."],
        critical_dependencies=["AWS CloudHSM Cluster"],
        completed_tasks=["Rotated master root key."],
        pending_tasks=[],
        unresolved_blockers=[],
        repository_links=["https://github.com/org/kms-service"],
    )
    db_session.add(ho)
    db_session.commit()

    # Trigger scan
    scan_res = client.post("/api/v1/sentinel/scan", json={"project_id": proj_id})
    assert scan_res.status_code == 200
    findings = scan_res.json()["detected_findings"]
    assert len(findings) > 0

    target_finding = findings[0]

    # Action 1: Request changes via PATCH /sentinel/risks/{id}
    req_res = client.patch(
        f"/api/v1/sentinel/risks/{target_finding['id']}",
        json={
            "action": "request_changes",
            "actor_name": "Security Director Marcus",
            "notes": "Must provide verified HSM verification sign-off before handover approval.",
        },
    )
    assert req_res.status_code == 200
    db_session.refresh(ho)
    assert ho.status == "changes_requested"
    assert "Security Director Marcus" in (ho.review_notes or "")

    # Action 2: Resolve finding
    res_res = client.patch(
        f"/api/v1/sentinel/risks/{target_finding['id']}",
        json={
            "action": "resolve",
            "actor_name": "Security Director Marcus",
            "notes": "HSM audit logs verified in Splunk dashboard.",
        },
    )
    assert res_res.status_code == 200
    resolved_data = res_res.json()
    assert resolved_data["risk"]["is_resolved"] is True
    assert "HSM audit logs verified" in resolved_data["risk"]["recommended_action"]

    # Verify AuditLog created
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_id == target_finding["id"],
            AuditLog.action == "RESOLVE_SENTINEL_FINDING",
        )
        .first()
    )
    assert audit is not None
    assert audit.details["actor_name"] == "Security Director Marcus"

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_project_isolation(db_session: Session):
    """Verify that Sentinel findings and scores remain strictly isolated between projects."""
    p1_id = f"prj-s-iso-1-{int(utc_now().timestamp())}"
    p2_id = f"prj-s-iso-2-{int(utc_now().timestamp())}"

    p1 = Project(id=p1_id, organization_id="org-acme-01", name="Project Shield", slug="proj-shield", bus_factor=2.0)
    p2 = Project(id=p2_id, organization_id="org-acme-01", name="Project Aegis", slug="proj-aegis", bus_factor=2.0)
    db_session.add_all([p1, p2])

    ev1 = SentinelEvent(
        id=f"risk-iso-{int(utc_now().timestamp())}",
        project_id=p1_id,
        project_name=p1.name,
        risk_level="high",
        category="UNSUPPORTED_COMPLETION_CLAIM",
        description="Shield specific task claim",
        recommended_action="Verify Shield task",
        is_resolved=False,
    )
    db_session.add(ev1)
    db_session.commit()

    # Query p1 vs p2
    res_p1 = client.get(f"/api/v1/sentinel/risks?project_id={p1_id}")
    assert res_p1.status_code == 200
    assert len(res_p1.json()) == 1
    assert res_p1.json()[0]["project_name"] == "Project Shield"

    res_p2 = client.get(f"/api/v1/sentinel/risks?project_id={p2_id}")
    assert res_p2.status_code == 200
    assert len(res_p2.json()) == 0

    # Clean up
    db_session.delete(p1)
    db_session.delete(p2)
    db_session.commit()

