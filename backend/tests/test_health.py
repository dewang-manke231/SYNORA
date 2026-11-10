from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Synora API" in data["message"]


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Synora - Knowledge Continuity & Project Protection Platform"


def test_handovers_requires_auth():
    # Anonymous request must fail closed with HTTP 401
    response = client.get("/api/v1/handovers/")
    assert response.status_code == 401


def test_handovers_authenticated(client: TestClient):
    # Authenticated client receives HTTP 200 with organization-scoped dossiers
    response = client.get("/api/v1/handovers/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_sentinel_risks():
    response = client.get("/api/v1/sentinel/risks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_knowledge_nodes():
    response = client.get("/api/v1/knowledge/nodes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

