"""
API Integration & Persistence Tests with Real Database Operations
"""
from fastapi.testclient import TestClient


def test_health_with_database(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "connected" in data["database"]


def test_handover_crud_persistence(client: TestClient):
    # 1. Create a handover via API
    payload = {
        "employee_name": "Devin Torres",
        "role": "Staff Cloud Engineer",
        "department": "Infrastructure SRE",
        "transition_type": "project_transfer",
        "key_responsibilities": ["Kubernetes cluster networking", "Istio service mesh"],
        "critical_dependencies": ["AWS Route53 zone delegation", "Cert-manager TLS certs"],
        "unresolved_blockers": ["MTLS configuration between clusters undocumented"],
    }
    create_res = client.post("/api/v1/handovers/", json=payload)
    assert create_res.status_code == 201
    created_item = create_res.json()
    created_id = created_item["id"]
    assert created_item["employee_name"] == "Devin Torres"
    assert created_item["status"] == "draft"

    # 2. Retrieve the specific item
    get_res = client.get(f"/api/v1/handovers/{created_id}")
    assert get_res.status_code == 200
    item = get_res.json()
    assert item["id"] == created_id
    assert item["department"] == "Infrastructure SRE"

    # 3. List all handovers and ensure it appears
    list_res = client.get("/api/v1/handovers/")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(h["id"] == created_id for h in items)


def test_radar_gaps_and_coverage_endpoints(client: TestClient):
    # Test Radar gaps endpoint
    gaps_res = client.get("/api/v1/radar/gaps")
    assert gaps_res.status_code == 200
    assert isinstance(gaps_res.json(), list)

    # Test Project coverage endpoint
    coverage_res = client.get("/api/v1/radar/coverage")
    assert coverage_res.status_code == 200
    assert isinstance(coverage_res.json(), list)

