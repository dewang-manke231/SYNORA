"""
Tests for Formal New-Joiner Handover Assignment & Access Boundaries
Verifies:
1. Successful manager assignment to an employee in the same organization.
2. Non-manager (employee) attempting assignment receives HTTP 403 Forbidden.
3. Cross-organization assignment is strictly denied (HTTP 403 Forbidden).
4. Unassigned third-party employee cannot access another employee's assigned handover (HTTP 403 Forbidden).
5. Assigned employee can successfully retrieve their assigned handover (HTTP 200).
6. Manager can view the assigned handover with populated assignee details.
7. Audit log entries are recorded for both initial assignment and reassignment.
8. Filtering by assigned_to=me / assigned_only=True returns only assigned dossiers.
9. GET /api/v1/handovers/assignees endpoint lists organization members for managers.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    User,
    Organization,
    OrganizationMembership,
    Project,
    Handover,
    AuditLog,
    generate_uuid,
    utc_now,
)
from app.core.security import hash_password, create_access_token


@pytest.fixture
def org_and_users(db_session: Session):
    """Sets up two organizations with managers and employees for isolation testing."""
    uid = generate_uuid()[:6]
    # Org 1: Primary Corp
    org1 = Organization(
        id=generate_uuid("org-"),
        name=f"Primary Corp {uid}",
        slug=f"primary-corp-{uid}",
        created_at=utc_now(),
    )
    db_session.add(org1)

    # Manager in Org 1
    manager1 = User(
        id=generate_uuid("usr-mgr-"),
        email=f"manager_{uid}@primary.corp",
        full_name="Sarah Connor",
        role="manager",
        hashed_password=hash_password("Password123!"),
        is_active=True,
        created_at=utc_now(),
    )
    db_session.add(manager1)

    # Employee 1 (Assignee) in Org 1
    employee1 = User(
        id=generate_uuid("usr-emp1-"),
        email=f"joiner_{uid}@primary.corp",
        full_name="Alex Chen",
        role="employee",
        hashed_password=hash_password("Password123!"),
        is_active=True,
        created_at=utc_now(),
    )
    db_session.add(employee1)

    # Employee 2 (Third party) in Org 1
    employee2 = User(
        id=generate_uuid("usr-emp2-"),
        email=f"other_{uid}@primary.corp",
        full_name="Jordan Lee",
        role="employee",
        hashed_password=hash_password("Password123!"),
        is_active=True,
        created_at=utc_now(),
    )
    db_session.add(employee2)

    # Memberships for Org 1
    db_session.add(OrganizationMembership(
        id=generate_uuid("mem-"),
        organization_id=org1.id,
        user_id=manager1.id,
        role="manager",
    ))
    db_session.add(OrganizationMembership(
        id=generate_uuid("mem-"),
        organization_id=org1.id,
        user_id=employee1.id,
        role="member",
    ))
    db_session.add(OrganizationMembership(
        id=generate_uuid("mem-"),
        organization_id=org1.id,
        user_id=employee2.id,
        role="member",
    ))

    # Project in Org 1
    project1 = Project(
        id=generate_uuid("prj-"),
        organization_id=org1.id,
        name="Payments Gateway",
        slug=f"payments-gw-{uid}",
        bus_factor=1.0,
    )
    db_session.add(project1)

    # Org 2: Competitor Corp
    org2 = Organization(
        id=generate_uuid("org-"),
        name=f"Competitor Corp {uid}",
        slug=f"competitor-corp-{uid}",
        created_at=utc_now(),
    )
    db_session.add(org2)

    # Employee in Org 2
    external_emp = User(
        id=generate_uuid("usr-ext-"),
        email=f"spy_{uid}@competitor.corp",
        full_name="Eve Hacker",
        role="employee",
        hashed_password=hash_password("Password123!"),
        is_active=True,
        created_at=utc_now(),
    )
    db_session.add(external_emp)

    db_session.add(OrganizationMembership(
        id=generate_uuid("mem-"),
        organization_id=org2.id,
        user_id=external_emp.id,
        role="member",
    ))

    # Handover in Org 1 Project
    handover = Handover(
        id=generate_uuid("ho-"),
        organization_id=org1.id,
        project_id=project1.id,
        employee_name="Departing Dev",
        role="Senior Backend Engineer",
        department="Engineering",
        transition_type="resignation",
        status="submitted",
        readiness_score=85.0,
        key_responsibilities=["Maintain Stripe integration"],
        critical_dependencies=["PostgreSQL database"],
        unresolved_blockers=[],
        completed_tasks=["Auth module migration"],
        pending_tasks=["Webhook retry mechanism"],
        created_at=utc_now(),
    )
    db_session.add(handover)
    db_session.commit()

    tokens = {
        "manager1": create_access_token({"sub": manager1.id, "email": manager1.email, "role": "manager", "org_id": org1.id}),
        "employee1": create_access_token({"sub": employee1.id, "email": employee1.email, "role": "employee", "org_id": org1.id}),
        "employee2": create_access_token({"sub": employee2.id, "email": employee2.email, "role": "employee", "org_id": org1.id}),
        "external_emp": create_access_token({"sub": external_emp.id, "email": external_emp.email, "role": "employee", "org_id": org2.id}),
    }

    return {
        "org1": org1,
        "org2": org2,
        "manager1": manager1,
        "employee1": employee1,
        "employee2": employee2,
        "external_emp": external_emp,
        "project1": project1,
        "handover": handover,
        "tokens": tokens,
    }


def test_manager_lists_eligible_assignees(client: TestClient, org_and_users):
    """Test GET /api/v1/handovers/assignees lists users within the manager's organization."""
    token = org_and_users["tokens"]["manager1"]
    resp = client.get(
        "/api/v1/handovers/assignees",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3
    emails = [u["email"] for u in data]
    assert org_and_users["employee1"].email in emails
    assert org_and_users["employee2"].email in emails
    assert org_and_users["external_emp"].email not in emails  # External user excluded!


def test_employee_cannot_list_assignees(client: TestClient, org_and_users):
    """Test that employees receive 403 Forbidden when attempting to list assignees."""
    token = org_and_users["tokens"]["employee1"]
    resp = client.get(
        "/api/v1/handovers/assignees",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_manager_assigns_handover_successfully(client: TestClient, org_and_users, db_session: Session):
    """Test manager assigns handover to an employee in the same organization."""
    token = org_and_users["tokens"]["manager1"]
    handover = org_and_users["handover"]
    employee1 = org_and_users["employee1"]

    resp = client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"assigned_to": employee1.id, "notes": "Welcome Alex! Please review the Stripe integration tasks."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned_to"] == employee1.id
    assert data["assigned_to_name"] == employee1.full_name
    assert data["assigned_to_email"] == employee1.email
    assert data["assigned_at"] is not None

    # Verify audit log was created
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == handover.id,
        AuditLog.action == "assign_handover",
    ).first()
    assert audit is not None
    assert audit.details["assigned_to"] == employee1.id
    assert audit.details["assignee_name"] == employee1.full_name


def test_employee_cannot_assign_handover(client: TestClient, org_and_users):
    """Test that an employee attempting assignment receives HTTP 403 Forbidden."""
    token = org_and_users["tokens"]["employee1"]
    handover = org_and_users["handover"]
    employee1 = org_and_users["employee1"]

    resp = client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"assigned_to": employee1.id},
    )
    assert resp.status_code == 403


def test_cross_organization_assignment_rejected(client: TestClient, org_and_users):
    """Test that manager cannot assign a handover to an employee from a different organization."""
    token = org_and_users["tokens"]["manager1"]
    handover = org_and_users["handover"]
    external_emp = org_and_users["external_emp"]

    resp = client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"assigned_to": external_emp.id},
    )
    assert resp.status_code == 403
    assert "outside your organization" in resp.json()["detail"]


def test_assigned_employee_can_retrieve_handover(client: TestClient, org_and_users):
    """Test that assigned employee can access their assigned handover."""
    token_mgr = org_and_users["tokens"]["manager1"]
    token_emp1 = org_and_users["tokens"]["employee1"]
    handover = org_and_users["handover"]
    employee1 = org_and_users["employee1"]

    # Assign to employee1
    client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token_mgr}"},
        json={"assigned_to": employee1.id},
    )

    # Employee 1 retrieves
    resp = client.get(
        f"/api/v1/handovers/{handover.id}",
        headers={"Authorization": f"Bearer {token_emp1}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == handover.id
    assert data["assigned_to"] == employee1.id


def test_unassigned_employee_cannot_access_assigned_handover(client: TestClient, org_and_users):
    """Test that a third-party unassigned employee cannot access another employee's assignment."""
    token_mgr = org_and_users["tokens"]["manager1"]
    token_emp2 = org_and_users["tokens"]["employee2"]
    handover = org_and_users["handover"]
    employee1 = org_and_users["employee1"]

    # Assign to employee 1
    client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token_mgr}"},
        json={"assigned_to": employee1.id},
    )

    # Employee 2 attempts retrieval -> HTTP 403 Forbidden
    resp = client.get(
        f"/api/v1/handovers/{handover.id}",
        headers={"Authorization": f"Bearer {token_emp2}"},
    )
    assert resp.status_code == 403
    assert "not assigned to this handover" in resp.json()["detail"]


def test_manager_reassigns_handover_creates_reassign_audit(client: TestClient, org_and_users, db_session: Session):
    """Test reassigning a handover to a different employee logs a reassign_handover audit event."""
    token_mgr = org_and_users["tokens"]["manager1"]
    handover = org_and_users["handover"]
    employee1 = org_and_users["employee1"]
    employee2 = org_and_users["employee2"]

    # Initial assignment
    client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token_mgr}"},
        json={"assigned_to": employee1.id},
    )

    # Reassignment to employee 2
    resp = client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token_mgr}"},
        json={"assigned_to": employee2.id, "notes": "Reassigned to Jordan Lee for primary ownership."},
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_to"] == employee2.id

    # Check audit log
    reassign_audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == handover.id,
        AuditLog.action == "reassign_handover",
    ).first()
    assert reassign_audit is not None
    assert reassign_audit.details["previous_assigned_to"] == employee1.id
    assert reassign_audit.details["assigned_to"] == employee2.id


def test_filter_handovers_assigned_to_me(client: TestClient, org_and_users):
    """Test filtering by assigned_to=me returns only handovers assigned to the authenticated employee."""
    token_mgr = org_and_users["tokens"]["manager1"]
    token_emp1 = org_and_users["tokens"]["employee1"]
    token_emp2 = org_and_users["tokens"]["employee2"]
    handover = org_and_users["handover"]
    employee1 = org_and_users["employee1"]

    # Assign to employee 1
    client.post(
        f"/api/v1/handovers/{handover.id}/assign",
        headers={"Authorization": f"Bearer {token_mgr}"},
        json={"assigned_to": employee1.id},
    )

    # Employee 1 queries with assigned_to=me
    resp1 = client.get(
        "/api/v1/handovers/?assigned_to=me",
        headers={"Authorization": f"Bearer {token_emp1}"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1) == 1
    assert data1[0]["id"] == handover.id

    # Employee 2 queries with assigned_to=me -> empty list
    resp2 = client.get(
        "/api/v1/handovers/?assigned_to=me",
        headers={"Authorization": f"Bearer {token_emp2}"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2) == 0


def test_cannot_assign_draft_handover(client: TestClient, org_and_users, db_session: Session):
    """Test that manager cannot assign a handover in 'draft' status (HTTP 400 Bad Request)."""
    token = org_and_users["tokens"]["manager1"]
    project1 = org_and_users["project1"]
    employee1 = org_and_users["employee1"]

    draft_ho = Handover(
        id=generate_uuid("ho-draft-"),
        project_id=project1.id,
        employee_name="Draft Engineer",
        role="Developer",
        department="Engineering",
        transition_type="resignation",
        status="draft",
        created_at=utc_now(),
    )
    db_session.add(draft_ho)
    db_session.commit()

    resp = client.post(
        f"/api/v1/handovers/{draft_ho.id}/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"assigned_to": employee1.id},
    )
    assert resp.status_code == 400
    assert "draft" in resp.json()["detail"].lower()
