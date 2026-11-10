from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import KnowledgeLossIndicator, Project, User
from app.services.radar import RadarService
from app.core.security import require_role, verify_project_organization_access, get_accessible_project_ids, get_current_user
from app.schemas.common import (
    KnowledgeGapItem,
    ProjectCoverage,
    ProjectCoverageDetail,
    RadarOverviewResponse,
    RadarScanRequest,
    RadarScanResponse,
    RadarRiskRemediateRequest,
    RadarRiskRemediateResponse,
)

router = APIRouter()


@router.get("/overview", response_model=RadarOverviewResponse)
def get_radar_overview(
    project_id: Optional[str] = Query(None, description="Optional project ID filter"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RadarOverviewResponse:
    """
    Returns platform-wide or project-specific Knowledge Loss Radar overview,
    including average coverage score, letter grade, and active risk breakdown.
    """
    project_ids = get_accessible_project_ids(current_user, db)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
    overview = RadarService.get_overview(db, project_id=project_id, project_ids=project_ids)
    return RadarOverviewResponse(**overview)


@router.get("/risks", response_model=List[KnowledgeGapItem])
def list_radar_risks(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    severity: Optional[str] = Query(None, description="Filter by severity: critical, high, medium, low"),
    gap_type: Optional[str] = Query(None, description="Filter by gap type: ADR_MISSING, SECONDARY_OWNER_MISSING, etc."),
    is_resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[KnowledgeGapItem]:
    """
    List all knowledge risks / indicators with optional filtering by project,
    severity, gap type, and resolution status.
    """
    query = db.query(KnowledgeLossIndicator)
    allowed_projects = get_accessible_project_ids(current_user, db)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
    elif allowed_projects is not None:
        query = query.filter(KnowledgeLossIndicator.project_id.in_(allowed_projects)) if allowed_projects else query.filter(KnowledgeLossIndicator.project_id == "__no_access__")
    if project_id:
        query = query.filter(KnowledgeLossIndicator.project_id == project_id)
    if severity:
        query = query.filter(KnowledgeLossIndicator.severity == severity.lower())
    if gap_type:
        query = query.filter(KnowledgeLossIndicator.gap_type == gap_type)
    if is_resolved is not None:
        query = query.filter(KnowledgeLossIndicator.is_resolved == is_resolved)

    risks = query.order_by(KnowledgeLossIndicator.detected_at.desc()).all()
    return risks


@router.post("/scan", response_model=RadarScanResponse)
def trigger_radar_scan(
    request: RadarScanRequest = RadarScanRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RadarScanResponse:
    """
    Trigger a proactive Knowledge Loss Radar scan against a project (or all projects).
    Detects missing ADRs, single points of failure, stale documents, and undocumented dependencies.
    """
    if request.project_id:
        verify_project_organization_access(request.project_id, current_user, db)
        target_projects = db.query(Project).filter(Project.id == request.project_id).all()
        if not target_projects:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{request.project_id}' not found.",
            )
    else:
        allowed_projects = get_accessible_project_ids(current_user, db)
        project_query = db.query(Project)
        if allowed_projects is not None:
            project_query = project_query.filter(Project.id.in_(allowed_projects)) if allowed_projects else project_query.filter(Project.id == "__no_access__")
        target_projects = project_query.all()

    total_new_gaps = 0
    all_detected_risks: List[KnowledgeLossIndicator] = []
    latest_explanation = None
    latest_score = 0.0

    actor = request.actor_name or "Radar Continuous Observer"

    for prj in target_projects:
        new_count, new_gaps, explanation = RadarService.scan_project(
            db, project_id=prj.id, actor_name=actor
        )
        total_new_gaps += new_count
        all_detected_risks.extend(new_gaps)
        latest_explanation = explanation
        latest_score = explanation["score"]

    # Gather total active gaps across scanned scope
    target_ids = [p.id for p in target_projects]
    active_gaps_count = (
        db.query(KnowledgeLossIndicator)
        .filter(
            KnowledgeLossIndicator.project_id.in_(target_ids),
            KnowledgeLossIndicator.is_resolved == False,  # noqa: E712
        )
        .count()
    )

    return RadarScanResponse(
        message=f"Scan complete. Discovered {total_new_gaps} new knowledge risk(s).",
        project_id=request.project_id,
        scanned_projects_count=len(target_projects),
        new_gaps_created=total_new_gaps,
        active_gaps_total=active_gaps_count,
        coverage_score=latest_score,
        explanation=latest_explanation,
        detected_risks=[KnowledgeGapItem.model_validate(g) for g in all_detected_risks],
    )


@router.patch("/risks/{risk_id}", response_model=RadarRiskRemediateResponse)
def remediate_radar_risk(
    risk_id: str,
    request: RadarRiskRemediateRequest,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
) -> RadarRiskRemediateResponse:
    """
    Remediate or resolve an identified knowledge risk. Recalculates project coverage
    score and records an audit log entry. Enforces manager-only access and organization isolation.
    """
    gap = db.query(KnowledgeLossIndicator).filter(KnowledgeLossIndicator.id == risk_id).first()
    if not gap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge risk '{risk_id}' not found.",
        )
    if gap.project_id:
        verify_project_organization_access(gap.project_id, current_user, db)

    actor = request.actor_name or current_user.full_name
    try:
        resolved_gap, explanation = RadarService.resolve_gap(
            db=db,
            gap_id=risk_id,
            actor_name=actor,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return RadarRiskRemediateResponse(
        message=f"Risk '{resolved_gap.module_name}' ({resolved_gap.gap_type}) successfully resolved.",
        risk=KnowledgeGapItem.model_validate(resolved_gap),
        updated_coverage_score=explanation["score"],
        explanation=explanation,
    )


# ----------------------------------------------------
# Backward Compatibility Endpoints
# ----------------------------------------------------

@router.get("/gaps", response_model=List[KnowledgeGapItem])
def list_knowledge_gaps(
    project_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[KnowledgeGapItem]:
    """Backward compatibility alias for /risks"""
    return list_radar_risks(
        project_id=project_id,
        severity=None,
        gap_type=None,
        is_resolved=None,
        current_user=current_user,
        db=db,
    )


@router.get("/coverage", response_model=List[ProjectCoverageDetail])
def list_project_coverage(
    project_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ProjectCoverageDetail]:
    """
    Returns list of project coverage scores with full transparency explanations.
    """
    project_ids = get_accessible_project_ids(current_user, db)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
    overview = RadarService.get_overview(db, project_id=project_id, project_ids=project_ids)
    return [ProjectCoverageDetail(**p) for p in overview["projects"]]
