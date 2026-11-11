import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.api.v1.endpoints.auth import demo_login
from app.core.seed import (
    PUBLIC_DEMO_EMPLOYEE_ID,
    PUBLIC_DEMO_MANAGER_ID,
    PUBLIC_DEMO_ORGANIZATION_ID,
    seed_database,
)
from app.models import OrganizationMembership
from app.schemas.common import DemoLoginRequest
from app.core.security import decode_access_token


def test_production_demo_flags_are_allowed_only_with_both_options_explicit():
    Settings(
        ENVIRONMENT="production",
        JWT_SECRET="production-demo-test-key-0123456789abcdef0123456789abcdef",
        DEMO_LOGIN_ENABLED=True,
        DEMO_SEED_ENABLED=True,
    )
    with pytest.raises(ValueError, match="DEMO_SEED_ENABLED"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="production-demo-test-key-0123456789abcdef0123456789abcdef",
            DEMO_LOGIN_ENABLED=True,
            DEMO_SEED_ENABLED=False,
        )


@pytest.mark.parametrize(
    ("role", "expected_email"),
    [
        ("manager", "marcus.vance@acme.corp"),
        ("employee", "alex.mercer@acme.corp"),
    ],
)
def test_demo_login_issues_session_for_selected_seeded_role(
    db_session, monkeypatch, role: str, expected_email: str,
):
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", True)
    session = demo_login(DemoLoginRequest(role=role), db_session)
    assert session.user.role == role
    assert session.user.email == expected_email
    assert decode_access_token(session.access_token)["role"] == role


def test_demo_login_is_disabled_unless_explicitly_enabled(
    db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        demo_login(DemoLoginRequest(role="manager"), db_session)
    assert exc.value.status_code == 404


def test_demo_login_rejects_arbitrary_roles():
    with pytest.raises(ValidationError):
        DemoLoginRequest(role="admin")


@pytest.mark.parametrize(
    ("role", "expected_id"),
    [("manager", PUBLIC_DEMO_MANAGER_ID), ("employee", PUBLIC_DEMO_EMPLOYEE_ID)],
)
def test_production_demo_login_uses_only_isolated_sample_workspace(
    db_session, monkeypatch, role: str, expected_id: str,
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEMO_LOGIN_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_SEED_ENABLED", True)
    seed_database(db_session)

    session = demo_login(DemoLoginRequest(role=role), db_session)
    assert session.user.id == expected_id
    assert session.user.role == role
    assert session.user.organization_id == PUBLIC_DEMO_ORGANIZATION_ID
    assert decode_access_token(session.access_token)["role"] == role
    assert db_session.query(OrganizationMembership).filter_by(
        user_id=expected_id, organization_id="org-acme-01"
    ).first() is None


