"""
Synora Phase 8 Security Test Suite: Server-Side Authentication & Role-Based Authorization (RBAC)

Verifies:
1. Registration with bcrypt password hashing and input validation (email format, password length, uniqueness)
2. Login credential verification, active status check, and JWT token issuance
3. Token validation, subject/role claims, and GET /api/v1/auth/me
4. Unauthenticated requests to protected manager/employee actions return 401 Unauthorized
5. Invalid or expired JWT tokens return 401 Unauthorized
6. Employee tokens attempting manager-only operations return 403 Forbidden
7. Legitimate manager tokens succeed on protected actions
8. Organization-level data isolation: cross-tenant access returns 403 Forbidden or 404 Not Found
9. Plaintext passwords are never stored and cannot be queried
"""
import time
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    User,
    Organization,
    OrganizationMembership,
    Project,
    Handover,
    ExtractedKnowledge,
    SentinelEvent,
    KnowledgeLossIndicator,
    utc_now,
)
from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)


def test_auth_registration_validation(unauthed_client: TestClient):
    """Verifies user registration validation rules (email format, password length, uniqueness)."""
    # 1. Invalid email
    res_bad_email = unauthed_client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "Password123!",
            "full_name": "Test User",
            "role": "employee",
        },
    )
    assert res_bad_email.status_code == 400
    assert "Invalid email" in res_bad_email.json()["detail"]

    # 2. Short password (< 8 chars) rejected by schema validation (422) or endpoint check (400)
    res_short_pw = unauthed_client.post(
        "/api/v1/auth/register",
        json={
            "email": "valid.user@acme.corp",
            "password": "123",
            "full_name": "Test User",
            "role": "employee",
        },
    )
    assert res_short_pw.status_code in (400, 422)

    # 3. Successful registration
    suffix = str(int(time.time() * 1000))
    email = f"engineer_{suffix}@testorg.com"
    res_reg = unauthed_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SuperSecurePassword123!",
            "full_name": "Devin Security",
            "role": "employee",
            "organization_name": "Fintech Global",
        },
    )
    assert res_reg.status_code == 201
    data = res_reg.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "employee"
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]

    # 4. Duplicate email rejection
    res_dup = unauthed_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "AnotherPassword123!",
            "full_name": "Devin Clone",
            "role": "employee",
        },
    )
    assert res_dup.status_code == 409
    assert "already exists" in res_dup.json()["detail"]


def test_auth_login_lifecycle(unauthed_client: TestClient, db_session: Session):
    """Verifies authenticating with bcrypt-hashed credentials and rejection of bad credentials."""
    suffix = str(int(time.time() * 1000))
    email = f"lead_{suffix}@acme.corp"
    plain_pw = "EnterpriseStrengthPass123!"

    # Create user with bcrypt hashed password
    user = User(
        id=f"usr-{suffix}",
        email=email,
        full_name="Lead Engineer",
        role="employee",
        hashed_password=hash_password(plain_pw),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # 1. Successful login
    login_res = unauthed_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": plain_pw},
    )
    assert login_res.status_code == 200
    body = login_res.json()
    assert "access_token" in body
    assert body["user"]["email"] == email

    # 2. Wrong password returns 401
    bad_pw_res = unauthed_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert bad_pw_res.status_code == 401
    assert "Invalid email or password" in bad_pw_res.json()["detail"]

    # 3. Nonexistent user returns 401
    bad_user_res = unauthed_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@acme.corp", "password": plain_pw},
    )
    assert bad_user_res.status_code == 401


def test_auth_me_endpoint_and_token_validation(unauthed_client: TestClient):
    """Verifies GET /api/v1/auth/me behavior under valid, missing, expired, and tampered tokens."""
    # 1. Missing token -> 401
    res_no_token = unauthed_client.get("/api/v1/auth/me")
    assert res_no_token.status_code == 401

    # 2. Invalid / tampered token -> 401
    res_tampered = unauthed_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer this-is-not-a-valid-jwt-token"},
    )
    assert res_tampered.status_code == 401

    # 3. Expired token -> 401
    expired_token = create_access_token(
        {"sub": "usr-mgr-01", "email": "marcus.vance@acme.corp", "role": "manager"},
        expires_delta=timedelta(seconds=-10),
    )
    res_expired = unauthed_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json()["detail"].lower()

    # 4. Valid token -> 200 with user profile
    valid_token = create_access_token(
        {"sub": "usr-mgr-01", "email": "marcus.vance@acme.corp", "role": "manager"},
    )
    res_valid = unauthed_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert res_valid.status_code == 200
    profile = res_valid.json()
    assert profile["email"] == "marcus.vance@acme.corp"
    assert profile["role"] == "manager"


def test_unauthenticated_requests_to_protected_endpoints_return_401(unauthed_client: TestClient):
    """
    Verifies that unauthenticated requests to protected endpoints return HTTP 401.
    Protected actions:
    - Handover approval: POST /api/v1/handovers/{id}/approve
    - Handover change request: POST /api/v1/handovers/{id}/request-changes
    - Handover creation: POST /api/v1/handovers/
    - Sentinel risk remediation: PATCH /api/v1/sentinel/risks/{id}
    - Radar risk remediation: PATCH /api/v1/radar/risks/{id}
    - Knowledge node verification: PATCH /api/v1/knowledge/nodes/{id}/verify
    """
    # Handover approve
    res_app = unauthed_client.post("/api/v1/handovers/ho-101/approve", json={"actor_name": "Nobody"})
    assert res_app.status_code == 401

    # Handover request changes
    res_req = unauthed_client.post(
        "/api/v1/handovers/ho-101/request-changes",
        json={"reviewer_name": "Nobody", "reason": "Missing docs"},
    )
    assert res_req.status_code == 401

    # Handover create
    res_create = unauthed_client.post(
        "/api/v1/handovers/",
        json={"employee_name": "Nobody", "role": "Dev", "transition_type": "resignation"},
    )
    assert res_create.status_code == 401

    # Sentinel risk remediate
    res_sentinel = unauthed_client.patch(
        "/api/v1/sentinel/risks/any-id",
        json={"action": "resolve"},
    )
    assert res_sentinel.status_code == 401

    # Radar risk remediate
    res_radar = unauthed_client.patch(
        "/api/v1/radar/risks/any-id",
        json={"action": "resolve"},
    )
    assert res_radar.status_code == 401

    # Knowledge node verify
    res_kn = unauthed_client.patch(
        "/api/v1/knowledge/nodes/any-id/verify",
        json={"action": "verified", "reviewer_name": "Nobody"},
    )
    assert res_kn.status_code == 401


def test_employee_attempting_manager_actions_returns_403(unauthed_client: TestClient):
    """
    Verifies that an authenticated employee token attempting manager actions returns HTTP 403 Forbidden.
    Server-side role guards must fail closed regardless of any body content or persona toggles.
    """
    emp_token = create_access_token({
        "sub": "usr-dev-01",
        "email": "alex.mercer@acme.corp",
        "role": "employee",
        "org_id": "org-acme-01",
    })
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 1. Employee attempting handover approval -> 403
    res_app = unauthed_client.post(
        "/api/v1/handovers/ho-101/approve",
        headers=emp_headers,
        json={"actor_name": "Alex Mercer pretending to be Marcus", "notes": "Self approval"},
    )
    assert res_app.status_code == 403
    assert "Insufficient privileges" in res_app.json()["detail"]

    # 2. Employee attempting handover change request -> 403
    res_change = unauthed_client.post(
        "/api/v1/handovers/ho-101/request-changes",
        headers=emp_headers,
        json={"reviewer_name": "Alex Mercer", "reason": "Arbitrary change"},
    )
    assert res_change.status_code == 403
    assert "Insufficient privileges" in res_change.json()["detail"]

    # 3. Employee attempting Sentinel risk remediation -> 403
    res_sentinel = unauthed_client.patch(
        "/api/v1/sentinel/risks/any-risk/remediate",
        headers=emp_headers,
        json={"action": "resolve"},
    )
    # The route is /api/v1/sentinel/risks/{risk_id}
    res_sentinel2 = unauthed_client.patch(
        "/api/v1/sentinel/risks/any-risk",
        headers=emp_headers,
        json={"action": "resolve"},
    )
    assert res_sentinel2.status_code == 403
    assert "Insufficient privileges" in res_sentinel2.json()["detail"]

    # 4. Employee attempting Radar risk remediation -> 403
    res_radar = unauthed_client.patch(
        "/api/v1/radar/risks/any-risk",
        headers=emp_headers,
        json={"action": "resolve"},
    )
    assert res_radar.status_code == 403
    assert "Insufficient privileges" in res_radar.json()["detail"]

    # 5. Employee attempting knowledge verification -> 403
    res_kn = unauthed_client.patch(
        "/api/v1/knowledge/nodes/any-node/verify",
        headers=emp_headers,
        json={"action": "verified", "reviewer_name": "Alex Mercer"},
    )
    assert res_kn.status_code == 403
    assert "Insufficient privileges" in res_kn.json()["detail"]


def test_manager_token_succeeds_on_manager_actions(unauthed_client: TestClient, db_session: Session):
    """Verifies that an authentic manager token succeeds on manager actions."""
    mgr_token = create_access_token({
        "sub": "usr-mgr-01",
        "email": "marcus.vance@acme.corp",
        "role": "manager",
        "org_id": "org-acme-01",
    })
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

    # Create a draft handover in org-acme-01 and submit it
    ho_id = f"ho-mgr-test-{int(time.time() * 1000)}"
    ho = Handover(
        id=ho_id,
        project_id="prj-pay-01",
        project_name="Payments & Settlement Engine",
        employee_name="Sarah Chen",
        role="Distributed Systems Engineer",
        department="Core Engineering",
        transition_type="internal_transition",
        status="submitted",
        key_responsibilities=["Raft Consensus Maintenance"],
        critical_dependencies=["Vault lease"],
        completed_tasks=["Upgraded raft lib"],
        pending_tasks=[],
        unresolved_blockers=[],
        readiness_score=75.0,
    )
    db_session.add(ho)
    db_session.commit()

    # Manager requests changes
    change_res = unauthed_client.post(
        f"/api/v1/handovers/{ho_id}/request-changes",
        headers=mgr_headers,
        json={"reviewer_name": "Marcus Vance", "reason": "Please attach consensus logs."},
    )
    assert change_res.status_code == 200
    assert change_res.json()["status"] == "changes_requested"

    # Resubmit as employee
    emp_token = create_access_token({
        "sub": "usr-dev-02",
        "email": "sarah.chen@acme.corp",
        "role": "employee",
        "org_id": "org-acme-01",
    })
    emp_headers = {"Authorization": f"Bearer {emp_token}"}
    sub_res = unauthed_client.post(
        f"/api/v1/handovers/{ho_id}/submit",
        headers=emp_headers,
        json={"actor_name": "Sarah Chen"},
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "submitted"

    # Manager approves
    app_res = unauthed_client.post(
        f"/api/v1/handovers/{ho_id}/approve",
        headers=mgr_headers,
        json={"actor_name": "Marcus Vance", "notes": "Consensus logs verified. Approved."},
    )
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "verified"


def test_cross_organization_isolation_enforcement(unauthed_client: TestClient, db_session: Session):
    """
    Verifies that users from Organization A cannot access, modify, or approve
    projects and handovers belonging to Organization B. Fails closed with 403 or 404.
    """
    suffix = str(int(time.time() * 1000))
    org_b_id = f"org-competitor-{suffix}"
    proj_b_id = f"prj-classified-{suffix}"
    ho_b_id = f"ho-classified-{suffix}"

    # Setup Org B
    org_b = Organization(id=org_b_id, name="Competitor Corp", slug=f"comp-{suffix}")
    proj_b = Project(
        id=proj_b_id,
        organization_id=org_b_id,
        name="Proprietary Trading Engine",
        slug=f"trading-{suffix}",
    )
    user_b_mgr = User(
        id=f"usr-comp-mgr-{suffix}",
        email=f"mgr_{suffix}@competitor.com",
        full_name="Competitor Manager",
        role="manager",
    )
    mem_b = OrganizationMembership(
        id=f"mem-comp-{suffix}",
        organization_id=org_b_id,
        user_id=user_b_mgr.id,
        role="manager",
    )
    ho_b = Handover(
        id=ho_b_id,
        project_id=proj_b_id,
        project_name="Proprietary Trading Engine",
        employee_name="Departing Quant",
        role="Lead Quant",
        department="HFT",
        transition_type="resignation",
        status="submitted",
    )
    db_session.add_all([org_b, proj_b, user_b_mgr, mem_b, ho_b])
    db_session.commit()

    # User from Org A (Marcus Vance) attempts to access / approve Handover in Org B
    org_a_mgr_token = create_access_token({
        "sub": "usr-mgr-01",
        "email": "marcus.vance@acme.corp",
        "role": "manager",
        "org_id": "org-acme-01",
    })
    org_a_headers = {"Authorization": f"Bearer {org_a_mgr_token}"}

    # Attempt to approve Org B handover -> 403 Forbidden
    res_cross_approve = unauthed_client.post(
        f"/api/v1/handovers/{ho_b_id}/approve",
        headers=org_a_headers,
        json={"actor_name": "Marcus Vance", "notes": "Unauthorized external approval"},
    )
    assert res_cross_approve.status_code == 403
    assert "outside your organization" in res_cross_approve.json()["detail"]

    # Attempt to access Org B handover via GET -> 403 Forbidden
    res_cross_get = unauthed_client.get(
        f"/api/v1/handovers/{ho_b_id}",
        headers=org_a_headers,
    )
    assert res_cross_get.status_code == 403
    assert "outside your organization" in res_cross_get.json()["detail"]


def test_password_hashing_security_properties():
    """Verifies that passwords are cryptographic bcrypt hashes, never plaintext."""
    raw_password = "SecurePassword123!"
    hashed = hash_password(raw_password)

    # Must start with bcrypt prefix ($2b$ or $2a$)
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert raw_password not in hashed
    assert verify_password(raw_password, hashed) is True
    assert verify_password("IncorrectPassword", hashed) is False
