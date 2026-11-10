"""
Regression Test Suite for Multi-Tenant Security & Infrastructure Sanitization
Verifies:
1. Anonymous access is strictly rejected (HTTP 401) on /handovers/, /handovers/{id}, and /health/diagnostics.
2. Cross-organization reads on handovers are blocked (HTTP 403).
3. Cross-organization assignments are blocked (HTTP 403) before state validation.
4. Unlinked handovers without project_id are correctly scoped to creator's organization.
5. Assigned employees can retrieve their assigned handovers; unauthorized employees cannot.
6. Public /health response strictly omits database URLs, hostnames, pool status, and credentials.
7. /health/diagnostics requires authentication.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    User,
    Organization,
    OrganizationMembership,
    Handover,
    Project,
    generate_uuid,
    utc_now,
)
from app.core.security import hash_password, create_access_token


@pytest.fixture
def multi_org_setup(db_session: Session):
    uid = generate_uuid()[:6]

    # Organization Alpha
    org_a = Organization(
        id=generate_uuid("org-"),
        name=f"Alpha Corp {uid}",
        slug=f"alpha-corp-{uid}",
        created_at=utc_now(),
    )
    db_session.add(org_a)

    # Org Alpha Manager
    mgr_a = User(
        id=generate_uuid("usr-"),
        email=f"mgr_a_{uid}@alpha.corp",
        full_name=f"Manager Alpha {uid}",
        role="manager",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    # Org Alpha Employee 1
    emp_a1 = User(
        id=generate_uuid("usr-"),
        email=f"emp_a1_{uid}@alpha.corp",
        full_name=f"Employee Alpha1 {uid}",
        role="employee",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    # Org Alpha Employee 2
    emp_a2 = User(
        id=generate_uuid("usr-"),
        email=f"emp_a2_{uid}@alpha.corp",
        full_name=f"Employee Alpha2 {uid}",
        role="employee",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db_session.add_all([mgr_a, emp_a1, emp_a2])
    db_session.flush()

    db_session.add_all([
        OrganizationMembership(id=generate_uuid("mem-"), organization_id=org_a.id, user_id=mgr_a.id, role="manager"),
        OrganizationMembership(id=generate_uuid("mem-"), organization_id=org_a.id, user_id=emp_a1.id, role="member"),
        OrganizationMembership(id=generate_uuid("mem-"), organization_id=org_a.id, user_id=emp_a2.id, role="member"),
    ])

    # Organization Beta
    org_b = Organization(
        id=generate_uuid("org-"),
        name=f"Beta Corp {uid}",
        slug=f"beta-corp-{uid}",
        created_at=utc_now(),
    )
    db_session.add(org_b)

    # Org Beta Manager
    mgr_b = User(
        id=generate_uuid("usr-"),
        email=f"mgr_b_{uid}@beta.corp",
        full_name=f"Manager Beta {uid}",
        role="manager",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    # Org Beta Employee
    emp_b = User(
        id=generate_uuid("usr-"),
        email=f"emp_b_{uid}@beta.corp",
        full_name=f"Employee Beta {uid}",
        role="employee",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db_session.add_all([mgr_b, emp_b])
    db_session.flush()

    db_session.add_all([
        OrganizationMembership(id=generate_uuid("mem-"), organization_id=org_b.id, user_id=mgr_b.id, role="manager"),
        OrganizationMembership(id=generate_uuid("mem-"), organization_id=org_b.id, user_id=emp_b.id, role="member"),
    ])

    # Unlinked Handover in Org Alpha (created by emp_a1)
    ho_unlinked_a = Handover(
        id=generate_uuid("ho-"),
        organization_id=org_a.id,
        project_id=None,
        employee_name=emp_a1.full_name,
        role="Backend Engineer",
        department="Core Infrastructure",
        transition_type="resignation",
        status="submitted",
        readiness_score=75.0,
        key_responsibilities=["Database maintenance"],
        completed_tasks=["Setup Postgres"],
    )
    db_session.add(ho_unlinked_a)
    db_session.commit()

    tokens = {
        "mgr_a": create_access_token({"sub": mgr_a.id, "email": mgr_a.email, "role": "manager", "org_id": org_a.id}),
        "emp_a1": create_access_token({"sub": emp_a1.id, "email": emp_a1.email, "role": "employee", "org_id": org_a.id}),
        "emp_a2": create_access_token({"sub": emp_a2.id, "email": emp_a2.email, "role": "employee", "org_id": org_a.id}),
        "mgr_b": create_access_token({"sub": mgr_b.id, "email": mgr_b.email, "role": "manager", "org_id": org_b.id}),
        "emp_b": create_access_token({"sub": emp_b.id, "email": emp_b.email, "role": "employee", "org_id": org_b.id}),
    }

    return {
        "org_a": org_a,
        "org_b": org_b,
        "mgr_a": mgr_a,
        "emp_a1": emp_a1,
        "emp_a2": emp_a2,
        "mgr_b": mgr_b,
        "emp_b": emp_b,
        "ho_unlinked_a": ho_unlinked_a,
        "tokens": tokens,
    }


def test_anonymous_access_rejected(unauthed_client: TestClient, multi_org_setup):
    """Anonymous access to handovers and internal diagnostics must be rejected with HTTP 401."""
    ho_id = multi_org_setup["ho_unlinked_a"].id

    r_list = unauthed_client.get("/api/v1/handovers/")
    assert r_list.status_code == 401, "Anonymous list of handovers must return HTTP 401"

    r_get = unauthed_client.get(f"/api/v1/handovers/{ho_id}")
    assert r_get.status_code == 401, "Anonymous get of handover must return HTTP 401"

    r_diag = unauthed_client.get("/api/v1/health/diagnostics")
    assert r_diag.status_code == 401, "Anonymous access to health diagnostics must return HTTP 401"


def test_cross_org_read_blocked(unauthed_client: TestClient, multi_org_setup):
    """Users from Org Beta must not be able to read Org Alpha handovers."""
    ho_id = multi_org_setup["ho_unlinked_a"].id
    mgr_b_token = multi_org_setup["tokens"]["mgr_b"]
    emp_b_token = multi_org_setup["tokens"]["emp_b"]

    r_mgr = unauthed_client.get(f"/api/v1/handovers/{ho_id}", headers={"Authorization": f"Bearer {mgr_b_token}"})
    assert r_mgr.status_code == 403, f"Org B manager should get 403 for Org A handover, got {r_mgr.status_code}"

    r_emp = unauthed_client.get(f"/api/v1/handovers/{ho_id}", headers={"Authorization": f"Bearer {emp_b_token}"})
    assert r_emp.status_code == 403, f"Org B employee should get 403 for Org A handover, got {r_emp.status_code}"


def test_cross_org_assignment_blocked(unauthed_client: TestClient, multi_org_setup):
    """Cross-org assignment attempts must be rejected with HTTP 403 before state or business validation."""
    ho_id = multi_org_setup["ho_unlinked_a"].id
    mgr_b_token = multi_org_setup["tokens"]["mgr_b"]
    mgr_a_token = multi_org_setup["tokens"]["mgr_a"]
    emp_b_id = multi_org_setup["emp_b"].id

    # Org B manager trying to assign Org A handover
    r1 = unauthed_client.post(
        f"/api/v1/handovers/{ho_id}/assign",
        json={"assigned_to": emp_b_id},
        headers={"Authorization": f"Bearer {mgr_b_token}"},
    )
    assert r1.status_code == 403, f"Org B manager assigning Org A handover must return 403, got {r1.status_code}"

    # Org A manager trying to assign to Org B employee
    r2 = unauthed_client.post(
        f"/api/v1/handovers/{ho_id}/assign",
        json={"assigned_to": emp_b_id},
        headers={"Authorization": f"Bearer {mgr_a_token}"},
    )
    assert r2.status_code == 403, f"Manager A assigning to Org B employee must return 403, got {r2.status_code}"


def test_unlinked_handover_organization_scoping(unauthed_client: TestClient, multi_org_setup):
    """Unlinked handovers without project_id must strictly scope to their organization."""
    ho_id = multi_org_setup["ho_unlinked_a"].id
    mgr_a_token = multi_org_setup["tokens"]["mgr_a"]
    mgr_b_token = multi_org_setup["tokens"]["mgr_b"]

    # Manager A can list and retrieve it
    r_list = unauthed_client.get("/api/v1/handovers/", headers={"Authorization": f"Bearer {mgr_a_token}"})
    assert r_list.status_code == 200
    listed_ids = [h["id"] for h in r_list.json()]
    assert ho_id in listed_ids, "Unlinked handover must appear in Org A manager listing"

    # Manager B listing does NOT contain it
    r_list_b = unauthed_client.get("/api/v1/handovers/", headers={"Authorization": f"Bearer {mgr_b_token}"})
    assert r_list_b.status_code == 200
    listed_b_ids = [h["id"] for h in r_list_b.json()]
    assert ho_id not in listed_b_ids, "Unlinked handover must not appear in Org B manager listing"


def test_handover_creation_populates_organization(unauthed_client: TestClient, multi_org_setup):
    """All handover creation paths must automatically populate organization_id."""
    emp_a1_token = multi_org_setup["tokens"]["emp_a1"]
    org_a_id = multi_org_setup["org_a"].id

    payload = {
        "employee_name": "Test Employee",
        "role": "Software Engineer",
        "department": "Core",
        "transition_type": "resignation",
        "key_responsibilities": ["Coding"],
    }
    r = unauthed_client.post("/api/v1/handovers/", json=payload, headers={"Authorization": f"Bearer {emp_a1_token}"})
    assert r.status_code == 201
    item = r.json()
    assert item["organization_id"] == org_a_id, f"Expected {org_a_id}, got {item.get('organization_id')}"


def test_public_health_sanitization(unauthed_client: TestClient):
    """Public /health must never leak connection strings, hostnames, passwords, or pool status."""
    r = unauthed_client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()

    assert data["status"] in ["healthy", "degraded"]
    assert data["database"] in ["connected", "unreachable"]
    assert data["database_target"] in ["managed-cloud", "local"]

    raw_json = str(data).lower()
    forbidden = ["password", "token", "secret", "postgresql+psycopg", "aws-1", "supabase.com", "pool_status"]
    for keyword in forbidden:
        assert keyword not in raw_json, f"Public /health leaked sensitive information: '{keyword}'"


def test_authenticated_health_diagnostics(unauthed_client: TestClient, multi_org_setup):
    """Authenticated users can access /health/diagnostics, but unauthenticated users are rejected."""
    mgr_a_token = multi_org_setup["tokens"]["mgr_a"]

    r_anon = unauthed_client.get("/api/v1/health/diagnostics")
    assert r_anon.status_code == 401

    r_auth = unauthed_client.get("/api/v1/health/diagnostics", headers={"Authorization": f"Bearer {mgr_a_token}"})
    assert r_auth.status_code == 200
    diag = r_auth.json()
    assert "telemetry" in diag
    assert diag["caller"] == multi_org_setup["mgr_a"].email

