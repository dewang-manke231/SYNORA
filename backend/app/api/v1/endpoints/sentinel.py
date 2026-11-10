from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import SentinelEvent, Project, Handover, User
from app.services.sentinel import SentinelService
from app.core.security import (
    require_role,
    get_current_user,
    get_accessible_project_ids,
    verify_project_organization_access,
    verify_handover_organization_access,
)
from app.schemas.common import (
    RiskAlert,
    SentinelOverviewResponse,
    SentinelScanRequest,
    SentinelScanResponse,
    SentinelRemediateRequest,
    SentinelRemediateResponse,
)

router = APIRouter()


@router.get("/overview", response_model=SentinelOverviewResponse)
def get_sentinel_overview(
    project_id: Optional[str] = Query(None, description="Optional project ID filter"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SentinelOverviewResponse:
    """
    Returns platform-wide or project-specific Sentinel Handover Integrity Overview,
    including average score, letter grade, and active findings distribution.
    """
    project_ids = get_accessible_project_ids(current_user, db)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
    overview = SentinelService.get_overview(db, project_id=project_id, project_ids=project_ids)
    return SentinelOverviewResponse(**overview)


@router.get("/risks", response_model=List[RiskAlert])
def list_risks(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    severity: Optional[str] = Query(None, description="Filter by severity / risk level"),
    category: Optional[str] = Query(None, description="Filter by finding category"),
    is_resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[RiskAlert]:
    """
    List Sentinel risk events / findings with multi-dimensional filtering.
    """
    query = db.query(SentinelEvent)
    allowed_projects = get_accessible_project_ids(current_user, db)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
    elif allowed_projects is not None:
        query = query.filter(SentinelEvent.project_id.in_(allowed_projects)) if allowed_projects else query.filter(SentinelEvent.project_id == "__no_access__")
    if project_id:
        query = query.filter(SentinelEvent.project_id == project_id)
    if severity:
        query = query.filter(SentinelEvent.risk_level == severity.lower())
    if category:
        query = query.filter(SentinelEvent.category == category)
    if is_resolved is not None:
        query = query.filter(SentinelEvent.is_resolved == is_resolved)

    risks = query.order_by(SentinelEvent.detected_at.desc()).all()
    return risks


@router.get("/findings", response_model=List[RiskAlert])
def list_findings(
    project_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    is_resolved: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[RiskAlert]:
    """Alias for /risks"""
    return list_risks(
        project_id=project_id,
        severity=severity,
        category=category,
        is_resolved=is_resolved,
        current_user=current_user,
        db=db,
    )


@router.post("/scan", response_model=SentinelScanResponse)
def trigger_sentinel_scan(
    request: SentinelScanRequest = SentinelScanRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SentinelScanResponse:
    """
    Trigger a continuous Handover Integrity and SPOF Sentinel scan.
    Audits missing documentation, incomplete sections, broken references, unsupported
    completion claims, contradictory deliverables, and missing environment setup instructions.
    """
    actor = request.actor_name or "Sentinel Integrity Scanner"
    total_new = 0
    all_findings: List[SentinelEvent] = []
    scanned_handovers = 0
    latest_score = 0.0

    if request.handover_id:
        handover = db.query(Handover).filter(Handover.id == request.handover_id).first()
        if not handover:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Handover with ID '{request.handover_id}' not found.",
            )
        verify_handover_organization_access(handover.id, current_user, db)
        count, evs = SentinelService.scan_handover(db, handover, actor_name=actor)
        total_new += count
        all_findings.extend(evs)
        scanned_handovers = 1
        if handover.project:
            summary = SentinelService.calculate_integrity_score(db, handover.project)
            latest_score = summary["integrity_score"]
    elif request.project_id:
        verify_project_organization_access(request.project_id, current_user, db)
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{request.project_id}' not found.",
            )
        count, evs, summary = SentinelService.scan_project(db, project.id, actor_name=actor)
        total_new += count
        all_findings.extend(evs)
        scanned_handovers = len(project.handovers or [])
        latest_score = summary["integrity_score"]
    else:
        allowed_projects = get_accessible_project_ids(current_user, db)
        project_query = db.query(Project)
        if allowed_projects is not None:
            project_query = project_query.filter(Project.id.in_(allowed_projects)) if allowed_projects else project_query.filter(Project.id == "__no_access__")
        projects = project_query.all()
        for p in projects:
            count, evs, summary = SentinelService.scan_project(db, p.id, actor_name=actor)
            total_new += count
            all_findings.extend(evs)
            scanned_handovers += len(p.handovers or [])
            latest_score = summary["integrity_score"]

    # Total active findings across all scanned scope
    active_query = db.query(SentinelEvent).filter(SentinelEvent.is_resolved == False)  # noqa: E712
    scanned_ids = [p.id for p in projects] if not request.project_id and not request.handover_id else ([request.project_id] if request.project_id else [handover.project_id])
    active_query = active_query.filter(SentinelEvent.project_id.in_(scanned_ids)) if scanned_ids else active_query.filter(SentinelEvent.project_id == "__no_access__")
    active_count = active_query.count()

    return SentinelScanResponse(
        message=f"Sentinel integrity scan complete. Discovered {total_new} new finding(s).",
        scanned_handovers_count=scanned_handovers,
        new_findings_created=total_new,
        active_findings_total=active_count,
        integrity_score=latest_score,
        detected_findings=[RiskAlert.model_validate(f) for f in all_findings],
    )


@router.patch("/risks/{risk_id}", response_model=SentinelRemediateResponse)
def remediate_sentinel_risk(
    risk_id: str,
    request: SentinelRemediateRequest,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
) -> SentinelRemediateResponse:
    """
    Remediate a Sentinel finding or request changes on the associated handover dossier.
    Enforces manager-only access and organization isolation.
    Recalculates the project integrity score and records an immutable AuditLog entry.
    """
    event = db.query(SentinelEvent).filter(SentinelEvent.id == risk_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sentinel finding '{risk_id}' not found.",
        )
    if event.project_id:
        verify_project_organization_access(event.project_id, current_user, db)

    actor = request.actor_name or current_user.full_name
    try:
        resolved_event, updated_score = SentinelService.resolve_finding(
            db=db,
            risk_id=risk_id,
            actor_name=actor,
            action=request.action,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return SentinelRemediateResponse(
        message=f"Sentinel finding '{resolved_event.category}' updated successfully.",
        risk=RiskAlert.model_validate(resolved_event),
        updated_integrity_score=updated_score,
    )
