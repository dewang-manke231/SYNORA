import io
import zipfile

import pytest

from app.services.project_intake import ProjectArchiveError, inspect_project_archive


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buf.getvalue()


def test_archive_excludes_env_and_redacts_secret_material():
    archive = make_zip({
        "README.md": "# Demo\nRun with npm install",
        ".env": "API_KEY=real-secret\n",
        "src/config.py": "api_key = supersecret123\n# TODO: configure fallback\n",
        "config.json": '{"client_secret": "json-secret-567", "mode": "safe"}',
        "id_rsa": "PRIVATE KEY MATERIAL",
    })
    files, findings, inventory = inspect_project_archive(archive)
    names = [entry["path"] for entry in files]
    assert ".env" not in names
    assert "id_rsa" not in names
    source = next(entry for entry in files if entry["path"] == "src/config.py")
    assert b"supersecret123" not in source["content"]
    config = next(entry for entry in files if entry["path"] == "config.json")
    assert b"json-secret-567" not in config["content"]
    assert inventory["todo_count"] == 1
    todo = next(item for item in findings if item["category"] == "INCOMPLETE_TASK")
    assert todo["source"] == "src/config.py:2"
    assert todo["evidence_type"] == "observed"


def test_archive_rejects_path_traversal():
    with pytest.raises(ProjectArchiveError, match="unsafe path"):
        inspect_project_archive(make_zip({"../outside.py": "print('unsafe')"}))


def test_archive_rejects_symlinks_and_skips_unsupported_and_secret_files():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("app.py", "print('safe')")
        archive.writestr("payload.exe", "not source")
        archive.writestr(".env.production", "TOKEN=secret")
        link = zipfile.ZipInfo("linked.py")
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        archive.writestr(link, "../outside.py")
    with pytest.raises(ProjectArchiveError, match="symbolic link"):
        inspect_project_archive(buf.getvalue())

    files, _, inventory = inspect_project_archive(make_zip({
        "app.py": "print('safe')",
        "payload.exe": "not source",
        ".env.production": "TOKEN=secret",
    }))
    assert [entry["path"] for entry in files] == ["app.py"]
    assert inventory["skipped_files"] == 2


def test_archive_enforces_compression_ratio_limit():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("readme.txt", "A" * 2_000_000)
    with pytest.raises(ProjectArchiveError, match="compression ratio"):
        inspect_project_archive(buf.getvalue())


def test_archive_reports_unknown_dependencies_as_inference():
    _, findings, inventory = inspect_project_archive(make_zip({"src/main.py": "print('hi')"}))
    assert inventory["indexed_files"] == ["src/main.py"]
    dependency = next(item for item in findings if item["category"] == "DEPENDENCIES_UNKNOWN")
    assert dependency["evidence_type"] == "inference"


def test_authenticated_project_intake_indexes_and_runs_existing_scans(client, db_session, monkeypatch):
    from app.api.v1.endpoints import projects
    from app.services.storage import LocalStorageProvider
    from app.core.embeddings import DeterministicMockEmbeddingProvider
    import app.services.ingestion as ingestion_module
    monkeypatch.setattr(projects.ingestion_service, "storage", LocalStorageProvider())
    monkeypatch.setattr(ingestion_module, "get_embedding_provider", lambda: DeterministicMockEmbeddingProvider())
    archive = make_zip({
        "README.md": "# Uploaded app\n\nSetup: python app.py",
        "requirements.txt": "fastapi>=0.110\n",
        "app.py": "# TODO: add health check\nprint('uploaded')\n",
    })
    response = client.post(
        "/api/v1/projects/intake",
        data={"project_name": "Uploaded Demo"},
        files={"file": ("demo.zip", archive, "application/zip")},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["indexed_file_count"] == 3
    assert data["detected_technologies"] == ["Python manifest"]
    assert data["todo_count"] == 1
    assert data["radar_coverage_score"] >= 0
    assert data["sentinel_integrity_score"] >= 0

    from app.models import Project, Document, DocumentChunk
    project = db_session.query(Project).filter(Project.id == data["project_id"]).one()
    docs = db_session.query(Document).filter(Document.project_id == project.id).all()
    assert len(docs) == 3
    assert db_session.query(DocumentChunk).filter(DocumentChunk.document_id.in_([d.id for d in docs])).count() >= 3
    assert project.bus_factor == 0.0


def test_project_intake_requires_authentication(unauthed_client):
    response = unauthed_client.post(
        "/api/v1/projects/intake",
        data={"project_name": "No auth"},
        files={"file": ("demo.zip", make_zip({"README.md": "# Demo"}), "application/zip")},
    )
    assert response.status_code == 401


def test_project_routes_reject_cross_organization_access(client, db_session):
    from app.models import Organization, Project
    other_org = Organization(id="org-intake-other", name="Other Org", slug="other-intake-org-unique")
    db_session.add(other_org)
    project = Project(id="prj-intake-other", organization_id=other_org.id, name="Private", slug="private")
    db_session.add(project)
    db_session.commit()
    assert client.get(f"/api/v1/projects/{project.id}").status_code == 403
    assert client.post("/api/v1/radar/scan", json={"project_id": project.id}).status_code == 403
    assert client.post("/api/v1/sentinel/scan", json={"project_id": project.id}).status_code == 403
