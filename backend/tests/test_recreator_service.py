import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.models import (
    Project,
    Document,
    EnvironmentSnapshot,
    AuditLog,
    utc_now,
)
from app.services.recreator import RecreatorService
from app.core.security import create_access_token

manager_token = create_access_token({"sub": "usr-mgr-01", "email": "marcus.vance@acme.corp", "role": "manager", "org_id": "org-acme-01"})
client = TestClient(app, headers={"Authorization": f"Bearer {manager_token}"})


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_manifest_inspection_endpoint():
    """Verify inspection uses only manifests indexed for the selected uploaded project."""
    db = SessionLocal()
    project_id = f"prj-inspect-{int(utc_now().timestamp())}"
    project = Project(id=project_id, organization_id="org-acme-01", name="Uploaded Inspection", slug=project_id)
    db.add(project)
    db.flush()
    db.add_all([
        Document(id=f"doc-{project_id}-req", project_id=project_id, filename="requirements.txt", content_type="text/plain", file_size=20, raw_text="fastapi>=0.110\n", uploaded_at=utc_now()),
        Document(id=f"doc-{project_id}-pkg", project_id=project_id, filename="package.json", content_type="application/json", file_size=30, raw_text='{"dependencies":{"react":"19"},"devDependencies":{"vite":"8"}}', uploaded_at=utc_now()),
    ])
    db.commit()
    db.close()
    response = client.get(f"/api/v1/recreator/inspect?project_id={project_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["stack_type"] in ("python_fastapi_react_vite", "python_backend", "nodejs_react_frontend")
    assert "FastAPI" in data["detected_frameworks"] or "React" in data["detected_frameworks"]
    assert len(data["manifest_files_found"]) > 0

    # Verify dependencies are real strings from requirements.txt / package.json
    assert any("fastapi" in pkg.lower() for pkg in data["backend_dependencies"])
    assert any("react" in pkg.lower() for pkg in data["frontend_dependencies"])
    assert "detected" in data["confidence_breakdown"]


def test_secret_redaction_guarantee():
    """Verify secrets and credentials are strictly redacted from generated configurations."""
    sensitive_dict = {
        "DATABASE_URL": "postgresql://postgres:real_super_secret_password_123@db.supabase.co:5432/postgres",
        "GEMINI_API_KEY": "AIzaSyRealSecretKey1234567890",
        "JWT_SECRET_TOKEN": "super_secret_jwt_hmac_key",
        "APP_ENV": "development",
        "PORT": 8000,
    }

    redacted = RecreatorService.redact_secrets(sensitive_dict)
    assert "real_super_secret_password_123" not in str(redacted)
    assert "AIzaSyRealSecretKey1234567890" not in str(redacted)
    assert "super_secret_jwt_hmac_key" not in str(redacted)

    assert redacted["GEMINI_API_KEY"] == "your_gemini_api_key_here"
    assert redacted["APP_ENV"] == "development"
    assert redacted["PORT"] == 8000

    # Test .env.example generator has zero real secrets
    env_content = RecreatorService.generate_env_example(list(sensitive_dict.keys()))
    assert "AIzaSy" not in env_content
    assert "GEMINI_API_KEY=your_gemini_api_key_here" in env_content


def test_windows_and_bash_command_generation():
    """Verify OS-specific launch sequences are valid and .cmd aware."""
    inspection = {
        "stack_type": "python_fastapi_react_vite",
        "detected_frameworks": ["FastAPI", "React", "Vite"],
        "python_version": "3.12.6",
        "node_version": "26.x",
        "manifest_files_found": ["requirements.txt", "package.json"],
        "backend_dependencies": ["fastapi", "uvicorn"],
        "frontend_dependencies": ["react", "vite"],
        "scripts": {"dev": "vite"},
        "environment_variables_detected": ["DATABASE_URL", "GEMINI_API_KEY"],
    }

    ps_script = RecreatorService.generate_powershell_script(inspection)
    assert "Activate.ps1" in ps_script
    assert "npm.cmd" in ps_script  # .cmd aware on Windows PowerShell
    assert "pip install -r requirements.txt" in ps_script

    bash_script = RecreatorService.generate_bash_script(inspection)
    assert "source .venv/bin/activate" in bash_script
    assert "npm install" in bash_script
    assert "#!/usr/bin/env bash" in bash_script


def test_blueprint_generation_and_persistence(db_session: Session):
    """
    Verify POST /api/v1/recreator/generate and GET /api/v1/recreator/blueprint:
    - Creates EnvironmentSnapshot row in database
    - Persists blueprint_spec with Docker Compose and launch scripts
    - Records AuditLog
    """
    proj_id = f"prj-recreator-test-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Algorithmic Trading Cluster",
        slug="algo-trading",
        bus_factor=2.0,
    )
    db_session.add(project)
    db_session.commit()

    # Generate blueprint
    res_gen = client.post(
        "/api/v1/recreator/generate",
        json={"project_id": proj_id, "actor_name": "Lead DevOps Marcus"},
    )
    assert res_gen.status_code == 200
    bp_data = res_gen.json()
    assert bp_data["project_id"] == proj_id
    assert "powershell_quickstart" in bp_data
    assert "docker_compose_yaml" in bp_data
    assert "services:" in bp_data["docker_compose_yaml"]

    # Verify retrieval
    res_get = client.get(f"/api/v1/recreator/blueprint?project_id={proj_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == bp_data["id"]

    # Verify AuditLog
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_id == bp_data["id"],
            AuditLog.action == "GENERATE_ENVIRONMENT_BLUEPRINT",
        )
        .first()
    )
    assert audit is not None
    assert audit.details["generated_by"] == "Lead DevOps Marcus"

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_environment_readiness_assessment(db_session: Session):
    """Verify GET /api/v1/recreator/readiness checks toolchains, versions, and failure modes."""
    proj_id = f"prj-readiness-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Settlement Clearing Network",
        slug="settlement-net",
        bus_factor=1.0,
    )
    db_session.add(project)
    db_session.commit()

    res = client.get(f"/api/v1/recreator/readiness?project_id={proj_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ready", "action_required")
    assert data["readiness_score"] >= 60.0
    assert len(data["prerequisites"]) >= 3
    assert len(data["potential_failure_modes"]) >= 2
    assert "detected" in data["detected_vs_inferred"]

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_onboarding_checklist_workflow(db_session: Session):
    """
    Verify developer onboarding checklist:
    - Initial steps loaded
    - Toggling step completed persists in snapshot and records AuditLog
    - Completion percentage dynamically updates
    """
    proj_id = f"prj-checklist-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Identity Federation Broker",
        slug="id-broker",
        bus_factor=2.0,
    )
    db_session.add(project)
    db_session.commit()

    # Get initial checklist
    res_init = client.get(f"/api/v1/recreator/checklist?project_id={proj_id}")
    assert res_init.status_code == 200
    init_data = res_init.json()
    assert init_data["total_steps"] >= 5
    assert init_data["completed_steps"] == 0
    assert init_data["completion_percentage"] == 0.0

    target_step = init_data["steps"][0]

    # Update step to completed
    res_update = client.post(
        "/api/v1/recreator/checklist",
        json={
            "project_id": proj_id,
            "step_id": target_step["id"],
            "is_completed": True,
            "actor_name": "New Hire Alex",
            "notes": "Git repo cloned and toolchains verified.",
        },
    )
    assert res_update.status_code == 200
    updated_data = res_update.json()
    assert updated_data["completed_steps"] == 1
    assert updated_data["completion_percentage"] > 0.0

    first_step = updated_data["steps"][0]
    assert first_step["is_completed"] is True
    assert first_step["completed_by"] == "New Hire Alex"

    # Verify AuditLog
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "UPDATE_ONBOARDING_CHECKLIST",
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    assert audit is not None
    assert audit.details["updated_by"] == "New Hire Alex"

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_export_endpoints(db_session: Session):
    """Verify downloadable .env.example and docker-compose.yml endpoints."""
    proj_id = f"prj-export-{int(utc_now().timestamp())}"
    project = Project(
        id=proj_id,
        organization_id="org-acme-01",
        name="Data Export Hub",
        slug="export-hub",
        bus_factor=1.0,
    )
    db_session.add(project)
    db_session.add(Document(
        id=f"doc-{proj_id}-env-example",
        project_id=proj_id,
        filename=".env.example",
        content_type="text/plain",
        file_size=30,
        raw_text="DATABASE_URL=your_database_url_here\n",
        uploaded_at=utc_now(),
    ))
    db_session.commit()

    res_env = client.get(f"/api/v1/recreator/export/env?project_id={proj_id}")
    assert res_env.status_code == 200
    assert res_env.headers["content-type"].startswith("text/plain")
    assert "DATABASE_URL" in res_env.text

    res_docker = client.get(f"/api/v1/recreator/export/docker?project_id={proj_id}")
    assert res_docker.status_code == 200
    assert "services:" in res_docker.text

    # Clean up
    db_session.delete(project)
    db_session.commit()


def test_project_isolation(db_session: Session):
    """Verify that environment snapshots are strictly isolated per project."""
    p1_id = f"prj-e-iso-1-{int(utc_now().timestamp())}"
    p2_id = f"prj-e-iso-2-{int(utc_now().timestamp())}"

    p1 = Project(id=p1_id, organization_id="org-acme-01", name="Project Helios", slug="proj-helios")
    p2 = Project(id=p2_id, organization_id="org-acme-01", name="Project Selene", slug="proj-selene")
    db_session.add_all([p1, p2])
    db_session.commit()

    # Generate blueprint for p1 only
    res_p1 = client.post("/api/v1/recreator/generate", json={"project_id": p1_id})
    assert res_p1.status_code == 200

    snap1 = db_session.query(EnvironmentSnapshot).filter_by(project_id=p1_id).first()
    snap2 = db_session.query(EnvironmentSnapshot).filter_by(project_id=p2_id).first()

    assert snap1 is not None
    assert snap2 is None  # Project Selene has not been generated yet

    # Clean up
    db_session.delete(p1)
    db_session.delete(p2)
    db_session.commit()

