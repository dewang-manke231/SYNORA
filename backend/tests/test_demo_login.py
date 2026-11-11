import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.endpoints.auth import (
    demo_login, get_public_demo_credentials, login_user,
)
from app.core.config import Settings, settings
from app.core.security import decode_access_token, hash_password, verify_password, verify_project_organization_access
from app.core.seed import (
    PUBLIC_DEMO_EMPLOYEE_ID, PUBLIC_DEMO_MANAGER_ID,
    PUBLIC_DEMO_ORGANIZATION_ID, PUBLIC_DEMO_PROJECT_ID, seed_database,
)
from app.models import OrganizationMembership, User
from app.schemas.common import DemoLoginRequest, UserLoginRequest


def _production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": "production-demo-test-key-0123456789abcdef0123456789abcdef",
        "DEMO_LOGIN_ENABLED": True,
        "DEMO_SEED_ENABLED": True,
        "DEMO_MANAGER_EMAIL": "manager@demo.synora.app",
        "DEMO_MANAGER_PASSWORD": "TestManagerPass!2026",
        "DEMO_EMPLOYEE_EMAIL": "employee@demo.synora.app",
        "DEMO_EMPLOYEE_PASSWORD": "TestEmployeePass!2026",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_demo_flags_and_credentials_require_explicit_configuration():
    _production_settings()
    with pytest.raises(ValueError, match="DEMO_SEED_ENABLED"):
        _production_settings(DEMO_SEED_ENABLED=False)
    with pytest.raises(ValueError, match="email/password configuration"):
        _production_settings(DEMO_MANAGER_PASSWORD=None)


@pytest.mark.parametrize(
    ("role", "user_id", "expected_email", "expected_password"),
    [
        ("manager", PUBLIC_DEMO_MANAGER_ID, "manager@demo.test", "TestManagerPass!2026"),
        ("employee", PUBLIC_DEMO_EMPLOYEE_ID, "employee@demo.test", "TestEmployeePass!2026"),
    ],
)
def test_demo_role_password_login_isolated_and_correct(db_session, role, user_id, expected_email, expected_password):
    user = db_session.query(User).filter_by(id=user_id).one()
    assert user.email == expected_email
    assert user.role == role
    assert user.hashed_password != expected_password
    assert verify_password(expected_password, user.hashed_password)
    session = login_user(UserLoginRequest(email=expected_email, password=expected_password), db_session)
    assert session.user.role == role
    assert session.user.organization_id == PUBLIC_DEMO_ORGANIZATION_ID
    claims = decode_access_token(session.access_token)
    assert claims["role"] == role
    assert claims["org_id"] == PUBLIC_DEMO_ORGANIZATION_ID
    assert db_session.query(OrganizationMembership).filter_by(
        user_id=user_id, organization_id=PUBLIC_DEMO_ORGANIZATION_ID, role=role,
    ).one()


@pytest.mark.parametrize(
    ("email", "role"),
    [("manager@demo.test", "manager"), ("employee@demo.test", "employee")],
)
def test_demo_invalid_password_rejected(db_session, email, role):
    with pytest.raises(HTTPException) as exc:
        login_user(UserLoginRequest(email=email, password="incorrect password"), db_session)
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    ("email", "password", "role"),
    [
        ("manager@demo.test", "TestManagerPass!2026", "manager"),
        ("employee@demo.test", "TestEmployeePass!2026", "employee"),
    ],
)
def test_demo_accounts_authenticate_through_normal_http_login(client, email, password, role):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["user"]["role"] == role
    assert result["user"]["organization_id"] == PUBLIC_DEMO_ORGANIZATION_ID
    assert decode_access_token(result["access_token"])["role"] == role


def test_normal_password_authentication_remains_available(db_session):
    user = db_session.query(User).filter_by(id="usr-dev-02").one()
    original_hash = user.hashed_password
    user.hashed_password = hash_password("ExistingEmployee!2026")
    db_session.commit()
    session = login_user(UserLoginRequest(email=user.email, password="ExistingEmployee!2026"), db_session)
    assert session.user.email == user.email
    assert session.user.role == "employee"
    user.hashed_password = original_hash
    db_session.commit()


def test_public_credentials_are_returned_only_when_both_demo_flags_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_SEED_ENABLED", True)
    credentials = get_public_demo_credentials()
    assert credentials.manager.email == settings.DEMO_MANAGER_EMAIL
    assert credentials.manager.password == settings.DEMO_MANAGER_PASSWORD
    assert credentials.employee.email == settings.DEMO_EMPLOYEE_EMAIL
    assert credentials.employee.password == settings.DEMO_EMPLOYEE_PASSWORD
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        get_public_demo_credentials()
    assert exc.value.status_code == 404


def test_public_credential_endpoint(client):
    response = client.get("/api/v1/auth/demo-credentials")
    assert response.status_code == 200
    result = response.json()
    assert result["manager"]["email"] == settings.DEMO_MANAGER_EMAIL
    assert result["employee"]["email"] == settings.DEMO_EMPLOYEE_EMAIL
    assert result["manager"]["password"] == settings.DEMO_MANAGER_PASSWORD
    assert result["employee"]["password"] == settings.DEMO_EMPLOYEE_PASSWORD


def test_legacy_passwordless_demo_route_is_not_available_in_production(db_session, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", True)
    with pytest.raises(HTTPException) as exc:
        demo_login(DemoLoginRequest(role="manager"), db_session)
    assert exc.value.status_code == 404


def test_invalid_demo_roles_are_rejected():
    with pytest.raises(ValidationError):
        DemoLoginRequest(role="admin")


def test_demo_users_cannot_access_another_organization_project(db_session):
    demo_user = db_session.query(User).filter_by(id=PUBLIC_DEMO_EMPLOYEE_ID).one()
    assert verify_project_organization_access(PUBLIC_DEMO_PROJECT_ID, demo_user, db_session).id == PUBLIC_DEMO_PROJECT_ID
    with pytest.raises(HTTPException) as exc:
        verify_project_organization_access("prj-pay-01", demo_user, db_session)
    assert exc.value.status_code == 403
    assert db_session.query(OrganizationMembership).filter_by(
        user_id=PUBLIC_DEMO_EMPLOYEE_ID, organization_id="org-acme-01",
    ).first() is None


def test_demo_seed_is_idempotent_and_reconciles_password_hash(db_session):
    before_users = db_session.query(User).filter(User.id.in_([PUBLIC_DEMO_MANAGER_ID, PUBLIC_DEMO_EMPLOYEE_ID])).count()
    before_memberships = db_session.query(OrganizationMembership).filter_by(organization_id=PUBLIC_DEMO_ORGANIZATION_ID).count()
    seed_database(db_session)
    after_users = db_session.query(User).filter(User.id.in_([PUBLIC_DEMO_MANAGER_ID, PUBLIC_DEMO_EMPLOYEE_ID])).count()
    after_memberships = db_session.query(OrganizationMembership).filter_by(organization_id=PUBLIC_DEMO_ORGANIZATION_ID).count()
    assert before_users == after_users == 2
    assert before_memberships == after_memberships
