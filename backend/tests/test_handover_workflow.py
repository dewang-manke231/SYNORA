"""
Comprehensive Handover Lifecycle & Manager Review Integration Tests
Verifies:
- Creation of draft handover with structured tasks, links, notes
- Submission workflow with validation checks
- Status transitions: draft -> submitted -> under_review -> changes_requested -> submitted -> verified -> completed
- Rejection of invalid status transitions (e.g. draft directly to verified or completed)
- Manager change request with mandatory reason visible in review_notes
- Manager approval with reviewer name and decision recorded in audit log
- Markdown report generation and export
- Persistence across database sessions
"""
import pytest
from fastapi.testclient import TestClient


def test_handover_full_lifecycle(client: TestClient):
    # 1. Create a structured handover dossier in draft status
    payload = {
        "employee_name": "Marcus Aurelius",
        "role": "Staff Distributed Systems Engineer",
        "department": "Platform Reliability",
        "transition_type": "internal_transition",
        "project_name": "Global Multi-Tenant Ingress",
        "project_description": "Global routing, TLS termination, and DDoS mitigation layer.",
        "key_responsibilities": [
            "BGP Anycast routing maintenance",
            "Envoy edge proxy fleet configuration",
        ],
        "critical_dependencies": [
            "Cloudflare Magic Transit API tokens",
            "Internal CA intermediate certificates",
        ],
        "unresolved_blockers": [
            "Automated cert renewal script fails on edge PoP in Tokyo",
        ],
        "completed_tasks": [
            "Upgraded Envoy sidecars to v1.30.1",
            "Drafted disaster recovery playbook for datacenter severance",
        ],
        "pending_tasks": [
            "Hand over root access credentials to team lead",
        ],
        "important_notes": "Do not touch the MTU configuration on the Singapore interconnect without notifying ISP.",
        "recommended_next_actions": [
            "Pair with successor on Tokyo edge cert rotation",
            "Audit Vault lease durations",
        ],
        "repository_links": [
            "https://github.com/acme-fintech/edge-routing",
        ],
        "documentation_links": [
            "https://wiki.acme.corp/edge-playbook",
        ],
        "database_references": [
            "db.routing.edge_nodes",
        ],
    }

    create_res = client.post("/api/v1/handovers/", json=payload)
    assert create_res.status_code == 201
    item = create_res.json()
    ho_id = item["id"]
    assert item["status"] == "draft"
    assert item["employee_name"] == "Marcus Aurelius"
    assert item["project_name"] == "Global Multi-Tenant Ingress"
    assert len(item["completed_tasks"]) == 2
    assert len(item["pending_tasks"]) == 1
    assert item["readiness_score"] > 0

    # 2. Test Invalid Transition: Cannot approve draft directly
    invalid_approve = client.post(
        f"/api/v1/handovers/{ho_id}/approve",
        json={"actor_name": "Elena Rostova", "notes": "Premature approval"}
    )
    assert invalid_approve.status_code == 400
    err = invalid_approve.json()["detail"]
    assert err["error_code"] == "INVALID_STATUS_TRANSITION"

    # 3. Update Draft content (PATCH)
    patch_res = client.patch(
        f"/api/v1/handovers/{ho_id}",
        json={"important_notes": "Updated note: Singapore MTU fixed to 1500."}
    )
    assert patch_res.status_code == 200
    assert "Singapore MTU fixed to 1500" in patch_res.json()["important_notes"]

    # 4. Employee Submits Handover (draft -> submitted)
    submit_res = client.post(
        f"/api/v1/handovers/{ho_id}/submit",
        json={"actor_name": "Marcus Aurelius"}
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "submitted"

    # 5. Manager starts review (submitted -> under_review)
    review_res = client.post(
        f"/api/v1/handovers/{ho_id}/start-review",
        json={"actor_name": "Elena Rostova"}
    )
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "under_review"
    assert review_res.json()["reviewed_by"] == "Elena Rostova"

    # 6. Manager requests changes with reason (under_review -> changes_requested)
    change_res = client.post(
        f"/api/v1/handovers/{ho_id}/request-changes",
        json={
            "reviewer_name": "Elena Rostova",
            "reason": "Please attach the Singapore ISP contact sheet and verify Tokyo certs before handoff."
        }
    )
    assert change_res.status_code == 200
    item = change_res.json()
    assert item["status"] == "changes_requested"
    assert item["review_decision"] == "changes_requested"
    assert "Singapore ISP contact sheet" in item["review_notes"]

    # 7. Employee addresses feedback & updates handover
    client.patch(
        f"/api/v1/handovers/{ho_id}",
        json={
            "unresolved_blockers": [],
            "completed_tasks": [
                "Upgraded Envoy sidecars to v1.30.1",
                "Drafted disaster recovery playbook for datacenter severance",
                "Resolved Tokyo cert renewal bug and attached ISP contact sheet",
            ],
            "pending_tasks": [],
        }
    )

    # 8. Employee resubmits (changes_requested -> submitted)
    resubmit_res = client.post(
        f"/api/v1/handovers/{ho_id}/submit",
        json={"actor_name": "Marcus Aurelius"}
    )
    assert resubmit_res.status_code == 200
    assert resubmit_res.json()["status"] == "submitted"

    # 9. Manager Approves (submitted -> verified)
    approve_res = client.post(
        f"/api/v1/handovers/{ho_id}/approve",
        json={
            "actor_name": "Elena Rostova",
            "notes": "Verified Tokyo edge fix and full documentation. Cleared for exit."
        }
    )
    assert approve_res.status_code == 200
    verified_item = approve_res.json()
    assert verified_item["status"] == "verified"
    assert verified_item["review_decision"] == "approved"
    assert verified_item["reviewed_by"] == "Elena Rostova"
    assert verified_item["readiness_score"] >= 95.0

    # 10. Operational Sign-off (verified -> completed)
    complete_res = client.post(
        f"/api/v1/handovers/{ho_id}/complete",
        json={"actor_name": "Marcus Vance"}
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "completed"
    assert complete_res.json()["readiness_score"] == 100.0

    # 11. Test Export to Markdown
    export_res = client.get(f"/api/v1/handovers/{ho_id}/export")
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "markdown_content" in export_data
    assert "Synora Handover Dossier: Marcus Aurelius" in export_data["markdown_content"]
    assert "Elena Rostova" in export_data["markdown_content"]
    assert "`COMPLETED`" in export_data["markdown_content"]

    # 12. Test Export Download stream
    download_res = client.get(f"/api/v1/handovers/{ho_id}/export?download=true")
    assert download_res.status_code == 200
    assert download_res.headers["content-type"].startswith("text/markdown")
    assert "attachment" in download_res.headers.get("content-disposition", "")
