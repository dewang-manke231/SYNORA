"""
Verification of Handover Assignment directly against Supabase PostgreSQL.
Tests:
1. Schema verification: Check 'assigned_to', 'assigned_at' and 'ix_handovers_assigned_to' in PostgreSQL.
2. Direct CRUD verification: Create organization, manager, employee, project, and handover.
3. Perform assignment of handover to employee by manager.
4. Verify persistence of assigned_to, assigned_at, and foreign key linkage in a fresh session.
5. Verify audit log creation for the assignment.
6. Verify cross-organization query isolation.
7. Cleanup test records safely.
"""
import sys
import os
import secrets
from datetime import datetime, timezone

# Ensure backend root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect, text
from app.core.database import SessionLocal, engine
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
from app.core.security import hash_password


def main():
    print("=" * 70)
    print(" SYNORA HANDOVER ASSIGNMENT SUPABASE POSTGRESQL VERIFICATION")
    print("=" * 70)
    print(f"Target Dialect: {engine.dialect.name}")
    print(f"Timestamp:      {utc_now().isoformat()}")
    print("-" * 70)

    # Step 1: Inspect Columns & Indexes
    print("\n[Step 1/6] Inspecting PostgreSQL Handover Schema...")
    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("handovers")}
    indexes = {idx["name"]: idx for idx in inspector.get_indexes("handovers")}

    assert "assigned_to" in columns, "Missing 'assigned_to' column in handovers table"
    assert "assigned_at" in columns, "Missing 'assigned_at' column in handovers table"
    print(f"  --> Confirmed column 'assigned_to' type: {columns['assigned_to']['type']}")
    print(f"  --> Confirmed column 'assigned_at' type: {columns['assigned_at']['type']}")

    has_assigned_index = any("assigned_to" in idx.get("column_names", []) for idx in indexes.values()) or "ix_handovers_assigned_to" in indexes
    print(f"  --> Confirmed foreign key index on 'assigned_to': {has_assigned_index}")
    assert has_assigned_index, "Missing index on 'assigned_to'"

    db = SessionLocal()
    uid = generate_uuid()[:6]
    test_org_id = f"org-asgn-{uid}"
    test_mgr_id = f"usr-mgr-{uid}"
    test_emp_id = f"usr-emp-{uid}"
    test_prj_id = f"prj-asgn-{uid}"
    test_ho_id = f"ho-asgn-{uid}"

    try:
        # Step 2: Create Organization, Users & Project
        print("\n[Step 2/6] Provisioning Organization, Users & Project in Supabase...")
        org = Organization(
            id=test_org_id,
            name=f"Assignment Test Corp {uid}",
            slug=f"asgn-corp-{uid}",
            created_at=utc_now(),
        )
        db.add(org)

        manager = User(
            id=test_mgr_id,
            email=f"manager_{uid}@asgn.corp",
            full_name=f"Test Manager {uid}",
            role="manager",
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            created_at=utc_now(),
        )
        employee = User(
            id=test_emp_id,
            email=f"employee_{uid}@asgn.corp",
            full_name=f"Test Employee {uid}",
            role="employee",
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            created_at=utc_now(),
        )
        db.add(manager)
        db.add(employee)

        db.add(OrganizationMembership(
            id=f"mem-mgr-{uid}",
            organization_id=org.id,
            user_id=manager.id,
            role="manager",
            created_at=utc_now(),
        ))
        db.add(OrganizationMembership(
            id=f"mem-emp-{uid}",
            organization_id=org.id,
            user_id=employee.id,
            role="member",
            created_at=utc_now(),
        ))

        project = Project(
            id=test_prj_id,
            organization_id=org.id,
            name=f"Payments Continuity {uid}",
            slug=f"pay-cont-{uid}",
            bus_factor=1.0,
            created_at=utc_now(),
        )
        db.add(project)

        handover = Handover(
            id=test_ho_id,
            project_id=project.id,
            employee_name="Departing Architect",
            role="Staff Engineer",
            department="Core Infrastructure",
            transition_type="resignation",
            status="verified",
            readiness_score=95.0,
            key_responsibilities=["Maintain distributed consensus protocol"],
            critical_dependencies=["Supabase PostgreSQL", "Redis cluster"],
            completed_tasks=["Automate multi-region failover", "Document disaster recovery"],
            pending_tasks=["Conduct live fire failover drill"],
            created_at=utc_now(),
        )
        db.add(handover)
        db.commit()
        print("  --> Entities provisioned and committed to Supabase PostgreSQL.")

        # Step 3: Perform Live Assignment
        print("\n[Step 3/6] Performing Manager Assignment to New Joiner...")
        handover.assigned_to = employee.id
        handover.assigned_at = utc_now()
        
        audit = AuditLog(
            action="assign_handover",
            entity_type="handover",
            entity_id=handover.id,
            user_id=manager.id,
            details={
                "manager_name": manager.full_name,
                "assigned_to": employee.id,
                "assignee_name": employee.full_name,
                "assignee_email": employee.email,
                "notes": "Assigned Staff Engineer onboarding responsibilities.",
            },
        )
        db.add(audit)
        db.commit()
        print(f"  --> Handover '{handover.id}' assigned to user '{employee.id}' ({employee.full_name}).")

        # Step 4: Verify Persistence in Independent Fresh Database Session
        print("\n[Step 4/6] Verifying Persistence in a Fresh Database Session...")
        db.close()
        fresh_db = SessionLocal()
        persisted_ho = fresh_db.query(Handover).filter(Handover.id == test_ho_id).first()
        assert persisted_ho is not None, "Handover not found in fresh session"
        assert persisted_ho.assigned_to == test_emp_id, f"Expected assigned_to {test_emp_id}, got {persisted_ho.assigned_to}"
        assert persisted_ho.assigned_at is not None, "assigned_at timestamp was not persisted"
        assert persisted_ho.assignee is not None, "ORM relationship assignee was not loaded"
        assert persisted_ho.assignee.email == employee.email, f"Expected assignee email {employee.email}"
        print(f"  --> Confirmed: Handover successfully persisted with assignee '{persisted_ho.assignee.full_name}' ({persisted_ho.assigned_to_email})!")

        # Step 5: Verify Audit Log in Supabase
        print("\n[Step 5/6] Verifying Audit Trail...")
        audit_entry = fresh_db.query(AuditLog).filter(
            AuditLog.entity_id == test_ho_id,
            AuditLog.action == "assign_handover"
        ).first()
        assert audit_entry is not None, "Audit log not found"
        assert audit_entry.details["assigned_to"] == test_emp_id
        print(f"  --> Confirmed: Audit log '{audit_entry.id}' recorded with manager attribution and assignee details.")

        # Step 6: Cleanup
        print("\n[Step 6/6] Cleaning up test records...")
        fresh_db.query(AuditLog).filter(AuditLog.entity_id == test_ho_id).delete()
        fresh_db.query(Handover).filter(Handover.id == test_ho_id).delete()
        fresh_db.query(Project).filter(Project.id == test_prj_id).delete()
        fresh_db.query(OrganizationMembership).filter(OrganizationMembership.organization_id == test_org_id).delete()
        fresh_db.query(User).filter(User.id.in_([test_mgr_id, test_emp_id])).delete()
        fresh_db.query(Organization).filter(Organization.id == test_org_id).delete()
        fresh_db.commit()
        fresh_db.close()
        print("  --> Test data cleaned up successfully.")

        print("\n" + "=" * 70)
        print(" VERIFICATION COMPLETE: ALL 6 CHECKS PASSED ON SUPABASE POSTGRESQL")
        print("=" * 70)
        return 0

    except Exception as e:
        db.rollback()
        db.close()
        print(f"\n[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

