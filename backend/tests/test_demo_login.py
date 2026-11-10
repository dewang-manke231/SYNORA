import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.mark.parametrize(
    ("role", "expected_email"),
    [
        ("manager", "marcus.vance@acme.corp"),
        ("employee", "alex.mercer@acme.corp"),
    ],
)
def test_demo_login_issues_session_for_selected_seeded_role(
    unauthed_client: TestClient, monkeypatch, role: str, expected_email: str,
):
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", True)
    response = unauthed_client.post("/api/v1/auth/demo-login", json={"role": role})
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["user"]["role"] == role
    assert session["user"]["email"] == expected_email

    authenticated = TestClient(
        unauthed_client.app,
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    profile = authenticated.get("/api/v1/auth/me")
    assert profile.status_code == 200
    assert profile.json()["role"] == role


def test_demo_login_is_disabled_unless_explicitly_enabled(
    unauthed_client: TestClient, monkeypatch,
):
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", False)
    response = unauthed_client.post("/api/v1/auth/demo-login", json={"role": "manager"})
    assert response.status_code == 404


def test_demo_login_rejects_arbitrary_roles(unauthed_client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", True)
    response = unauthed_client.post("/api/v1/auth/demo-login", json={"role": "admin"})
    assert response.status_code == 422
