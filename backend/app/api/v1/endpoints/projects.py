"""Authenticated project inventory and ZIP intake endpoints."""
import mimetypes
import re
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_user_organization_id, verify_project_organization_access
from app.models import OrganizationMembership, Project, User, generate_uuid, utc_now
from app.schemas.common import ProjectIntakeResponse
from app.services.ingestion import DuplicateDocumentError, IngestionError, IngestionService
from app.services.project_intake import ProjectArchiveError, inspect_project_archive
from app.services.radar import RadarService
from app.services.sentinel import SentinelService

router = APIRouter()
ingestion_service = IngestionService()


class ProjectRepositoryUpdate(BaseModel):
    repository_url: Optional[str] = Field(default=None, max_length=512)


@router.get("")
def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> List[dict]:
    """List only projects in the authenticated user's organizations."""
    query = db.query(Project)
    if current_user.role != "admin":
        # One joined query avoids loading memberships and then issuing a second
        # project query. This endpoint is on the critical path for both Projects
        # and project-scoped modules.
        query = (
            query.join(
                OrganizationMembership,
                Project.organization_id == OrganizationMembership.organization_id,
            )
            .filter(OrganizationMembership.user_id == current_user.id)
            .distinct()
        )
    projects = query.order_by(Project.created_at.desc()).all()
    return [{"id": p.id, "name": p.name, "organization_id": p.organization_id,
             "description": p.description, "repository_url": p.repository_url,
             "created_at": p.created_at} for p in projects]


@router.post("/intake", response_model=ProjectIntakeResponse, status_code=status.HTTP_201_CREATED)
async def intake_project(
    project_name: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectIntakeResponse:
    """Create a tenant-scoped project, securely index an uploaded ZIP, and produce evidence-backed findings."""
    organization_id = get_user_organization_id(current_user, db)
    if not organization_id:
        raise HTTPException(status_code=403, detail="An organization membership is required to create a project.")
    archive_bytes = await file.read(50 * 1024 * 1024 + 1)
    try:
        extracted_files, findings, inventory = inspect_project_archive(archive_bytes)
    except ProjectArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Project intake requires a .zip archive.")

    clean_name = project_name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Project name cannot be blank.")
    slug_base = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")[:80] or "project"
    project_id = generate_uuid("prj-")
    project = Project(
        id=project_id,
        organization_id=organization_id,
        name=clean_name,
        slug=f"{slug_base}-{project_id[-8:]}",
        description="Imported project archive; analysis findings are evidence-based or explicitly marked as inference.",
        bus_factor=0.0,  # Unknown ownership is not treated as a measured single-person bus factor.
        knowledge_coverage_score=0.0,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    skipped = inventory["skipped_files"]
    indexed_file_names: List[str] = []
    try:
        for entry in extracted_files:
            mime_type = mimetypes.guess_type(entry["filename"])[0] or "text/plain"
            try:
                ingestion_service.process_and_store_document(
                    db=db,
                    file_bytes=entry["content"],
                    filename=entry["filename"],
                    content_type=mime_type,
                    project_id=project.id,
                    uploaded_by_id=current_user.id,
                )
                indexed_file_names.append(entry["filename"])
            except DuplicateDocumentError:
                skipped += 1
    except IngestionError as exc:
        # The already indexed files remain associated with this project and can be inspected/retried.
        raise HTTPException(status_code=422, detail=f"Project was created but indexing stopped: {exc}")

    radar_new, radar_gaps, radar_summary = RadarService.scan_project(db, project.id, actor_name=current_user.full_name)
    sentinel_new, sentinel_findings, sentinel_summary = SentinelService.scan_project(db, project.id, actor_name=current_user.full_name)
    for gap in radar_gaps:
        findings.append({
            "category": gap.gap_type,
            "severity": gap.severity,
            "evidence_type": "inference",
            "source": "RadarService project scan",
            "evidence": gap.description,
        })
    for event in sentinel_findings:
        findings.append({
            "category": event.category,
            "severity": event.risk_level,
            "evidence_type": "inference",
            "source": "SentinelService project scan",
            "evidence": event.description,
        })
    return ProjectIntakeResponse(
        project_id=project.id,
        project_name=project.name,
        indexed_file_count=len(extracted_files) - (skipped - inventory["skipped_files"]),
        skipped_file_count=skipped,
        manifests=inventory["manifests"],
        detected_technologies=inventory["technologies"],
        extracted_file_names=indexed_file_names,
        todo_count=inventory["todo_count"],
        findings=findings,
        radar_gaps_created=radar_new,
        radar_coverage_score=radar_summary["score"],
        sentinel_findings_created=sentinel_new,
        sentinel_integrity_score=sentinel_summary["integrity_score"],
    )


@router.post("/{project_id}/extract", response_model=ProjectIntakeResponse)
async def extract_project_files(
    project_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectIntakeResponse:
    """Securely extract and index another ZIP archive into an existing authorized project."""
    project = verify_project_organization_access(project_id, current_user, db)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Project extraction requires a .zip archive.")

    archive_bytes = await file.read(50 * 1024 * 1024 + 1)
    try:
        extracted_files, findings, inventory = inspect_project_archive(archive_bytes)
    except ProjectArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    skipped = inventory["skipped_files"]
    indexed_file_names: List[str] = []
    try:
        for entry in extracted_files:
            mime_type = mimetypes.guess_type(entry["filename"])[0] or "text/plain"
            try:
                ingestion_service.process_and_store_document(
                    db=db,
                    file_bytes=entry["content"],
                    filename=entry["filename"],
                    content_type=mime_type,
                    project_id=project.id,
                    uploaded_by_id=current_user.id,
                )
                indexed_file_names.append(entry["filename"])
            except DuplicateDocumentError:
                skipped += 1
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=f"Extraction stopped while indexing the project archive: {exc}")

    radar_new, radar_gaps, radar_summary = RadarService.scan_project(db, project.id, actor_name=current_user.full_name)
    sentinel_new, sentinel_findings, sentinel_summary = SentinelService.scan_project(db, project.id, actor_name=current_user.full_name)
    findings.extend({
        "category": gap.gap_type,
        "severity": gap.severity,
        "evidence_type": "inference",
        "source": "RadarService project scan",
        "evidence": gap.description,
    } for gap in radar_gaps)
    findings.extend({
        "category": event.category,
        "severity": event.risk_level,
        "evidence_type": "inference",
        "source": "SentinelService project scan",
        "evidence": event.description,
    } for event in sentinel_findings)

    return ProjectIntakeResponse(
        project_id=project.id,
        project_name=project.name,
        indexed_file_count=len(indexed_file_names),
        skipped_file_count=skipped,
        manifests=inventory["manifests"],
        detected_technologies=inventory["technologies"],
        extracted_file_names=indexed_file_names,
        todo_count=inventory["todo_count"],
        findings=findings,
        radar_gaps_created=radar_new,
        radar_coverage_score=radar_summary["score"],
        sentinel_findings_created=sentinel_new,
        sentinel_integrity_score=sentinel_summary["integrity_score"],
    )


@router.get("/{project_id}")
def get_project(project_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    project = verify_project_organization_access(project_id, current_user, db)
    return {"id": project.id, "name": project.name, "organization_id": project.organization_id,
            "description": project.description, "repository_url": project.repository_url,
            "created_at": project.created_at}


@router.patch("/{project_id}/repository")
def update_project_repository(
    project_id: str,
    payload: ProjectRepositoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Save a project's primary Git repository URL after tenant authorization."""
    project = verify_project_organization_access(project_id, current_user, db)
    value = payload.repository_url.strip() if payload.repository_url else None
    if value:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Enter a valid http(s) repository URL.")
    project.repository_url = value
    db.commit()
    db.refresh(project)
    return {"project_id": project.id, "repository_url": project.repository_url}
