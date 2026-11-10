import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.models import (
    Project,
    Document,
    ExtractedKnowledge,
    KnowledgeLossIndicator,
    Handover,
    AuditLog,
    utc_now,
    generate_uuid,
)
from app.services.radar import RadarService

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


def test_radar_overview_endpoint():
    """Verify GET /api/v1/radar/overview returns valid response and transparent formula."""
    response = client.get("/api/v1/radar/overview")
    assert response.status_code == 200
    data = response.json()
    assert "average_coverage_score" in data
    assert "overall_grade" in data
    assert "total_active_gaps" in data
    assert "critical_gaps" in data
    assert "projects" in data
    assert "scoring_formula" in data
    assert "Documentation" in data["scoring_formula"]
    assert len(data["projects"]) > 0

    first_prj = data["projects"][0]
    assert "bus_factor" in first_prj
    assert "knowledge_coverage_score" in first_prj
    assert "grade" in first_prj
    assert "explanation" in first_prj
    assert "breakdown" in first_prj["explanation"]


def test_radar_risks_listing_and_filtering():
    """Verify GET /api/v1/radar/risks supports filtering by project, severity, and status."""
    response = client.get("/api/v1/radar/risks")
    assert response.status_code == 200
    risks = response.json()
    assert isinstance(risks, list)
    assert len(risks) >= 3

    # Filter by severity
    res_crit = client.get("/api/v1/radar/risks?severity=critical")
    assert res_crit.status_code == 200
    crit_risks = res_crit.json()
    for r in crit_risks:
        assert r["severity"] == "critical"

    # Filter by gap_type
    res_adr = client.get("/api/v1/radar/risks?gap_type=ADR_MISSING")
    assert res_adr.status_code == 200
    for r in res_adr.json():
        assert r["gap_type"] == "ADR_MISSING"

    # Backward compatibility endpoint /api/v1/radar/gaps
    compat_res = client.get("/api/v1/radar/gaps")
    assert compat_res.status_code == 200
    assert len(compat_res.json()) == len(risks)


def test_missing_adr_and_secondary_owner_detection(db_session: Session):
    """
    Verify RadarService scans and identifies:
    - ADR_MISSING for architecture module without linked decision
    - SECONDARY_OWNER_MISSING for component with single owner
    """
    # Create isolated test project
    proj_id = f"prj-test-radar-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Test Autonomous Gateway",
        slug="test-gateway",
        description="Core gateway routing service",
        bus_factor=1.0,
        knowledge_coverage_score=0.0,
    )
    db_session.add(project)

    # Add an architectural component without linked decision, owned by a single engineer
    arch_item = ExtractedKnowledge(
        id=f"kn-arch-{int(utc_now().timestamp())}",
        project_id=proj_id,
        label="Distributed Ingress Proxy",
        category="architecture",
        details="Reverse proxy cluster terminating TLS and balancing downstream gRPC streams.",
        owner="Marcus Vance",
        confidence_score=0.95,
        verification_status="verified",
        source_quote="Ingress proxy is solely maintained by Marcus.",
    )
    db_session.add(arch_item)
    db_session.commit()

    # Trigger scan via API
    scan_res = client.post("/api/v1/radar/scan", json={"project_id": proj_id, "actor_name": "QA Auditor"})
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert scan_data["project_id"] == proj_id
    assert scan_data["new_gaps_created"] >= 2

    # Verify detected risks
    detected = scan_data["detected_risks"]
    gap_types = [g["gap_type"] for g in detected]
    assert "ADR_MISSING" in gap_types
    assert "SECONDARY_OWNER_MISSING" in gap_types

    # Verify evidence and description are grounded
    adr_gap = next(g for g in detected if g["gap_type"] == "ADR_MISSING")
    assert "Distributed Ingress Proxy" in adr_gap["module_name"]
    assert "Architecture Decision Record" in adr_gap["description"]

    owner_gap = next(g for g in detected if g["gap_type"] == "SECONDARY_OWNER_MISSING")
    assert "Marcus Vance" in owner_gap["description"]

    # Verify idempotence: scanning again should discover 0 new gaps
    rescan = client.post("/api/v1/radar/scan", json={"project_id": proj_id})
    assert rescan.status_code == 200
    assert rescan.json()["new_gaps_created"] == 0

    # Clean up test project
    db_session.delete(project)
    db_session.commit()


def test_stale_documentation_and_dependency_detection(db_session: Session):
    """
    Verify RadarService identifies:
    - STALE_DOCUMENTATION for documents older than 30 days
    - UNDOCUMENTED_DEPENDENCY for external dependencies mentioned in handovers without docs
    """
    proj_id = f"prj-stale-test-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Test Payment Webhook Engine",
        slug="test-webhooks",
        bus_factor=1.0,
    )
    db_session.add(project)

    # 1. Stale document (45 days old)
    old_date = utc_now() - timedelta(days=45)
    stale_doc = Document(
        id=f"doc-stale-{int(utc_now().timestamp())}",
        project_id=proj_id,
        filename="legacy_webhook_v1_architecture.md",
        content_type="text/markdown",
        file_size=2048,
        processing_status="completed",
        raw_text="Legacy architecture for processing HTTP postbacks.",
        uploaded_at=old_date,
    )
    db_session.add(stale_doc)

    # 2. Handover with undocumented external dependency
    handover = Handover(
        id=f"ho-stale-{int(utc_now().timestamp())}",
        project_id=proj_id,
        employee_name="Elena Rostova",
        role="Senior Infrastructure Engineer",
        department="Platform",
        transition_type="resignation",
        status="verified",
        critical_dependencies=["Fintech Core Banking Settlement API v4"],
    )
    db_session.add(handover)
    db_session.commit()

    # Trigger scan
    scan_res = client.post("/api/v1/radar/scan", json={"project_id": proj_id})
    assert scan_res.status_code == 200
    data = scan_res.json()
    gap_types = [g["gap_type"] for g in data["detected_risks"]]
    assert "STALE_DOCUMENTATION" in gap_types
    assert "UNDOCUMENTED_DEPENDENCY" in gap_types

    stale_gap = next(g for g in data["detected_risks"] if g["gap_type"] == "STALE_DOCUMENTATION")
    assert "legacy_webhook_v1_architecture.md" in stale_gap["module_name"]

    dep_gap = next(g for g in data["detected_risks"] if g["gap_type"] == "UNDOCUMENTED_DEPENDENCY")
    assert "Fintech Core Banking Settlement API v4" in dep_gap["module_name"]
    assert "Elena Rostova" in dep_gap["description"]

    # Clean up test project
    db_session.delete(project)
    db_session.commit()


def test_coverage_score_calculation_and_remediation(db_session: Session):
    """
    Verify Knowledge Coverage Score formula:
    - Penalties reduce score
    - Resolving a gap immediately increases the score
    - Audit log entry is generated
    """
    proj_id = f"prj-score-test-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Settlement Clearing Service",
        slug="settlement-clearing",
        bus_factor=2.0,
    )
    db_session.add(project)
    db_session.commit()

    # Initially calculate coverage
    initial_exp = RadarService.calculate_project_coverage(db_session, project)
    initial_score = initial_exp["score"]

    # Add a critical gap
    critical_gap = KnowledgeLossIndicator(
        id=f"rad-crit-{int(utc_now().timestamp())}",
        project_id=proj_id,
        module_name="Settlement Quorum Consensus",
        gap_type="ADR_MISSING",
        severity="critical",
        description="Missing ADR for multi-region quorum consensus.",
        is_resolved=False,
    )
    db_session.add(critical_gap)
    db_session.commit()

    # Recalculate - score must decrease by exactly 15 points (or reach 0)
    penalized_exp = RadarService.calculate_project_coverage(db_session, project)
    assert penalized_exp["score"] < initial_score or initial_score == 0.0
    assert any(p["gap_id"] == critical_gap.id and p["deduction"] == 15.0 for p in penalized_exp["penalty_breakdown"])

    # Remediate risk via PATCH API
    patch_res = client.patch(
        f"/api/v1/radar/risks/{critical_gap.id}",
        json={
            "action": "resolve",
            "actor_name": "Chief Architect",
            "notes": "ADR-042 published and committed in docs/adr/042-quorum.md.",
        },
    )
    assert patch_res.status_code == 200
    patch_data = patch_res.json()
    assert patch_data["risk"]["is_resolved"] is True
    assert patch_data["updated_coverage_score"] > penalized_exp["score"]
    assert "Remediated by Chief Architect" in patch_data["risk"]["recommended_remediation"]

    # Verify audit log was created
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_id == critical_gap.id,
            AuditLog.action == "RESOLVE_KNOWLEDGE_GAP",
        )
        .first()
    )
    assert audit is not None
    assert audit.details["resolved_by"] == "Chief Architect"

    # Clean up test project
    db_session.delete(project)
    db_session.commit()


def test_project_isolation(db_session: Session):
    """Verify that risks and coverage calculations are strictly isolated between projects."""
    p1_id = f"prj-iso-1-{int(utc_now().timestamp())}"
    p2_id = f"prj-iso-2-{int(utc_now().timestamp())}"

    p1 = Project(id=p1_id, organization_id="org-acme-01", name="Project Alpha", slug="proj-alpha", bus_factor=2.0)
    p2 = Project(id=p2_id, organization_id="org-acme-01", name="Project Beta", slug="proj-beta", bus_factor=1.0)
    db_session.add_all([p1, p2])

    gap1 = KnowledgeLossIndicator(
        id=f"rad-iso-{int(utc_now().timestamp())}",
        project_id=p1_id,
        module_name="Alpha Core Cache",
        gap_type="ADR_MISSING",
        severity="high",
        description="Alpha specific gap",
        is_resolved=False,
    )
    db_session.add(gap1)
    db_session.commit()

    # Query risks for p1 vs p2
    res_p1 = client.get(f"/api/v1/radar/risks?project_id={p1_id}")
    assert res_p1.status_code == 200
    assert len(res_p1.json()) == 1
    assert res_p1.json()[0]["module_name"] == "Alpha Core Cache"

    res_p2 = client.get(f"/api/v1/radar/risks?project_id={p2_id}")
    assert res_p2.status_code == 200
    assert len(res_p2.json()) == 0

    # Clean up
    db_session.delete(p1)
    db_session.delete(p2)
    db_session.commit()
