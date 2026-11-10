from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Project, User
from app.services.recreator import RecreatorService
from app.core.security import get_current_user, verify_project_organization_access
from app.schemas.common import (
    ManifestInspectionResult,
    EnvironmentBlueprintResponse,
    ReadinessAssessment,
    OnboardingChecklistResponse,
    OnboardingChecklistUpdateRequest,
    EnvironmentSnapshotCreateRequest,
)

router = APIRouter()


@router.get("/inspect", response_model=ManifestInspectionResult)
def inspect_repository_manifests(
    project_id: str = Query(..., description="Project ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ManifestInspectionResult:
    """
    Inspects repository manifest files (requirements.txt, package.json, .env.example)
    and returns detected dependencies, frameworks, scripts, and runtime versions.
    """
    verify_project_organization_access(project_id, current_user, db)
    inspection = RecreatorService.inspect_project_documents(db, project_id)
    return ManifestInspectionResult(**inspection)


@router.get("/blueprint", response_model=EnvironmentBlueprintResponse)
def get_environment_blueprint(
    project_id: str = Query(..., description="Project ID to retrieve blueprint for"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnvironmentBlueprintResponse:
    """
    Retrieves or generates the deterministic development blueprint for a project,
    including PowerShell, Bash, and Docker Compose configurations.
    """
    verify_project_organization_access(project_id, current_user, db)
    try:
        snapshot = RecreatorService.get_or_create_blueprint(db, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    spec = snapshot.blueprint_spec or {}
    return EnvironmentBlueprintResponse(
        id=snapshot.id,
        project_id=snapshot.project_id,
        environment_name=snapshot.environment_name,
        stack_type=snapshot.stack_type,
        powershell_quickstart=snapshot.powershell_quickstart or "",
        bash_quickstart=snapshot.bash_quickstart or "",
        docker_compose_yaml=spec.get("docker_compose_yaml", ""),
        env_example_content=spec.get("env_example_content", ""),
        blueprint_spec=spec,
        created_at=snapshot.created_at,
    )


@router.post("/generate", response_model=EnvironmentBlueprintResponse)
def generate_environment_blueprint(
    request: EnvironmentSnapshotCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnvironmentBlueprintResponse:
    """
    Generates a deterministic environment snapshot blueprint for a project,
    recording an immutable AuditLog entry.
    """
    verify_project_organization_access(request.project_id, current_user, db)
    try:
        snapshot = RecreatorService.get_or_create_blueprint(
            db,
            project_id=request.project_id,
            actor_name=request.actor_name or "Recreator Service",
            force_regenerate=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    spec = snapshot.blueprint_spec or {}
    return EnvironmentBlueprintResponse(
        id=snapshot.id,
        project_id=snapshot.project_id,
        environment_name=snapshot.environment_name,
        stack_type=snapshot.stack_type,
        powershell_quickstart=snapshot.powershell_quickstart or "",
        bash_quickstart=snapshot.bash_quickstart or "",
        docker_compose_yaml=spec.get("docker_compose_yaml", ""),
        env_example_content=spec.get("env_example_content", ""),
        blueprint_spec=spec,
        created_at=snapshot.created_at,
    )


@router.get("/readiness", response_model=ReadinessAssessment)
def assess_environment_readiness(
    project_id: str = Query(..., description="Project ID to evaluate"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReadinessAssessment:
    """
    Assesses local machine readiness, toolchain installations, port availability,
    and potential failure modes for incoming engineers.
    """
    verify_project_organization_access(project_id, current_user, db)
    try:
        readiness = RecreatorService.assess_readiness(db, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return ReadinessAssessment(**readiness)


@router.get("/checklist", response_model=OnboardingChecklistResponse)
def get_onboarding_checklist(
    project_id: str = Query(..., description="Project ID to get checklist for"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingChecklistResponse:
    """
    Retrieves the interactive developer onboarding checklist with completion states.
    """
    verify_project_organization_access(project_id, current_user, db)
    try:
        checklist = RecreatorService.get_checklist(db, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return OnboardingChecklistResponse(**checklist)


@router.post("/checklist", response_model=OnboardingChecklistResponse)
def update_onboarding_checklist(
    request: OnboardingChecklistUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingChecklistResponse:
    """
    Updates an onboarding checklist item (toggle completed) with actor attribution
    and persistence in the snapshot specification.
    """
    verify_project_organization_access(request.project_id, current_user, db)
    try:
        updated = RecreatorService.update_checklist_step(
            db,
            project_id=request.project_id,
            step_id=request.step_id,
            is_completed=request.is_completed,
            actor_name=request.actor_name,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return OnboardingChecklistResponse(**updated)


@router.get("/export/env")
def export_env_example(
    project_id: str = Query(..., description="Project ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Exports clean, secret-redacted .env.example content.
    """
    verify_project_organization_access(project_id, current_user, db)
    try:
        snapshot = RecreatorService.get_or_create_blueprint(db, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    spec = snapshot.blueprint_spec or {}
    content = spec.get("env_example_content")
    if not content:
        inspection = RecreatorService.inspect_project_documents(db, project_id)
        content = RecreatorService.generate_env_example(inspection["environment_variables_detected"])
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={snapshot.project_id}_env.example"},
    )


@router.get("/export/docker")
def export_docker_compose(
    project_id: str = Query(..., description="Project ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Exports self-contained docker-compose.yml configuration.
    """
    verify_project_organization_access(project_id, current_user, db)
    try:
        snapshot = RecreatorService.get_or_create_blueprint(db, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    spec = snapshot.blueprint_spec or {}
    content = spec.get("docker_compose_yaml")
    if not content:
        inspection = RecreatorService.inspect_project_documents(db, project_id)
        content = RecreatorService.generate_docker_compose(inspection)
    return Response(
        content=content,
        media_type="text/yaml",
        headers={"Content-Disposition": f"attachment; filename={snapshot.project_id}_docker-compose.yml"},
    )
