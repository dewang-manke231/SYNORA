from fastapi import APIRouter, HTTPException, Depends, Query, Response, status as http_status
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.schemas.common import (
    HandoverItem,
    HandoverCreate,
    HandoverUpdate,
    HandoverActionRequest,
    HandoverChangeRequest,
    HandoverAssignRequest,
    HandoverExportResponse,
    UserResponse,
)
from app.core.database import get_db
from app.models import Handover, AuditLog, Project, User, Organization, OrganizationMembership, utc_now
from app.services.handover import HandoverService, calculate_readiness_score
from app.core.security import (
    get_current_user,
    get_current_user_optional,
    get_user_organization_id,
    require_role,
    verify_handover_organization_access,
    verify_project_organization_access,
)

router = APIRouter()


@router.get("/", response_model=List[HandoverItem])
def list_handovers(
    status: Optional[str] = Query(None, description="Filter by status (draft, submitted, under_review, changes_requested, verified, completed)"),
    department: Optional[str] = Query(None, description="Filter by department"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user ID or 'me'"),
    assigned_only: Optional[bool] = Query(False, description="Filter to only handovers assigned to the current authenticated user"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[HandoverItem]:
    """List all handover dossiers with mandatory organization-level scoping and optional filtering."""
    query = db.query(Handover)

    # Enforce organization scoping for non-admins
    if current_user.role != "admin":
        user_memberships = (
            db.query(OrganizationMembership.organization_id)
            .filter(OrganizationMembership.user_id == current_user.id)
            .all()
        )
        user_org_ids = [m[0] for m in user_memberships]

        # Scoped to handovers matching user's organizations, project organizations, assignees, or creator
        query = query.filter(
            (Handover.organization_id.in_(user_org_ids)) |
            (Handover.assigned_to == current_user.id) |
            (Handover.employee_name == current_user.full_name) |
            (Handover.project_id.in_(
                db.query(Project.id).filter(Project.organization_id.in_(user_org_ids))
            ))
        )

    if status:
        query = query.filter(Handover.status == status)
    if department:
        query = query.filter(Handover.department == department)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
        query = query.filter(Handover.project_id == project_id)

    if assigned_only or assigned_to == "me":
        query = query.filter(Handover.assigned_to == current_user.id)
    elif assigned_to:
        query = query.filter(Handover.assigned_to == assigned_to)

    handovers = query.order_by(Handover.created_at.desc()).all()
    return handovers


@router.get("/assignees", response_model=List[UserResponse])
def list_eligible_assignees(
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
) -> List[UserResponse]:
    """List eligible assignees (employees and engineers) within the manager's organization."""
    org_id = get_user_organization_id(current_user, db)
    if not org_id:
        return []

    memberships = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == org_id)
        .all()
    )
    user_ids = [m.user_id for m in memberships]
    users = db.query(User).filter(User.id.in_(user_ids), User.is_active == True).all()

    org = db.query(Organization).filter(Organization.id == org_id).first()
    org_name = org.name if org else None

    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            organization_id=org_id,
            organization_name=org_name,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/{handover_id}", response_model=HandoverItem)
def get_handover(
    handover_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Retrieve detailed handover dossier by ID with mandatory authentication and org access enforcement."""
    return verify_handover_organization_access(handover_id, current_user, db)


@router.post("/", response_model=HandoverItem, status_code=201)
def create_handover(
    payload: HandoverCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Create a new structured handover dossier in 'draft' status with mandatory organization attribution."""
    new_id = f"ho-{uuid.uuid4().hex[:6]}"

    # Auto-resolve project name and enforce organization boundary if project_id is provided
    target_org_id = payload.organization_id
    proj_name = payload.project_name
    proj_desc = payload.project_description

    if payload.project_id:
        prj = verify_project_organization_access(payload.project_id, current_user, db)
        if not proj_name:
            proj_name = prj.name
            proj_desc = proj_desc or prj.description
        if not target_org_id:
            target_org_id = prj.organization_id

    if not target_org_id:
        target_org_id = get_user_organization_id(current_user, db)

    if not target_org_id and current_user.role != "admin":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Cannot create handover: user does not belong to any organization and no project was linked.",
        )

    new_item = Handover(
        id=new_id,
        organization_id=target_org_id,
        project_id=payload.project_id,
        project_name=proj_name,
        project_description=proj_desc,
        employee_name=payload.employee_name or current_user.full_name,
        role=payload.role or current_user.role,
        department=payload.department,
        transition_type=payload.transition_type,
        status="draft",
        readiness_score=0.0,
        key_responsibilities=payload.key_responsibilities or [],
        critical_dependencies=payload.critical_dependencies or [],
        unresolved_blockers=payload.unresolved_blockers or [],
        completed_tasks=payload.completed_tasks or [],
        pending_tasks=payload.pending_tasks or [],
        important_notes=payload.important_notes,
        recommended_next_actions=payload.recommended_next_actions or [],
        repository_links=payload.repository_links or [],
        documentation_links=payload.documentation_links or [],
        database_references=payload.database_references or [],
    )
    new_item.readiness_score = calculate_readiness_score(new_item)
    db.add(new_item)

    audit = AuditLog(
        action="create_handover",
        entity_type="handover",
        entity_id=new_id,
        user_id=current_user.id,
        details={
            "employee_name": payload.employee_name or current_user.full_name,
            "department": payload.department,
            "project_name": proj_name,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.patch("/{handover_id}", response_model=HandoverItem)
def update_handover(
    handover_id: str,
    payload: HandoverUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Update editable content on a handover. Allowed in draft or changes_requested status."""
    verify_handover_organization_access(handover_id, current_user, db)
    item = HandoverService.get_or_404(db, handover_id)

    # Lock content modification once verified or completed
    if item.status in ["verified", "completed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit content of a handover in terminal status '{item.status}'."
        )

    update_dict = payload.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(item, field, val)

    item.readiness_score = calculate_readiness_score(item)
    item.updated_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        action="update_handover",
        entity_type="handover",
        entity_id=item.id,
        user_id=current_user.id,
        details={"updated_fields": list(update_dict.keys())}
    ))
    db.commit()
    db.refresh(item)
    return item


@router.post("/{handover_id}/submit", response_model=HandoverItem)
def submit_handover(
    handover_id: str,
    payload: Optional[HandoverActionRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Employee transitions handover from 'draft' or 'changes_requested' to 'submitted'."""
    verify_handover_organization_access(handover_id, current_user, db)
    actor = (payload.actor_name if payload and payload.actor_name else None) or current_user.full_name
    return HandoverService.submit(db, handover_id, employee_name=actor)


@router.post("/{handover_id}/start-review", response_model=HandoverItem)
def start_handover_review(
    handover_id: str,
    payload: Optional[HandoverActionRequest] = None,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Manager transitions handover from 'submitted' to 'under_review'."""
    verify_handover_organization_access(handover_id, current_user, db)
    actor = (payload.actor_name if payload and payload.actor_name else None) or current_user.full_name
    return HandoverService.start_review(db, handover_id, reviewer_name=actor)


@router.post("/{handover_id}/approve", response_model=HandoverItem)
def approve_handover(
    handover_id: str,
    payload: Optional[HandoverActionRequest] = None,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Manager approves handover, transitioning to 'verified' with audit sign-off."""
    verify_handover_organization_access(handover_id, current_user, db)
    actor = (payload.actor_name if payload and payload.actor_name else None) or current_user.full_name
    notes = payload.notes if payload else None
    return HandoverService.approve(
        db,
        handover_id,
        reviewer_name=actor,
        notes=notes,
    )


@router.post("/{handover_id}/request-changes", response_model=HandoverItem)
def request_changes_handover(
    handover_id: str,
    payload: HandoverChangeRequest,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Manager requests revisions on handover with mandatory reason for the employee."""
    verify_handover_organization_access(handover_id, current_user, db)
    reviewer = payload.reviewer_name or current_user.full_name
    return HandoverService.request_changes(
        db,
        handover_id,
        reviewer_name=reviewer,
        reason=payload.reason,
    )


@router.post("/{handover_id}/complete", response_model=HandoverItem)
def complete_handover(
    handover_id: str,
    payload: Optional[HandoverActionRequest] = None,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """Final operational sign-off: transitions 'verified' handover to 'completed'."""
    verify_handover_organization_access(handover_id, current_user, db)
    actor = (payload.actor_name if payload and payload.actor_name else None) or current_user.full_name
    return HandoverService.mark_completed(db, handover_id, user_name=actor)


@router.post("/{handover_id}/assign", response_model=HandoverItem)
def assign_handover(
    handover_id: str,
    payload: HandoverAssignRequest,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
) -> HandoverItem:
    """
    Manager assigns a handover dossier to an incoming new joiner / employee.
    Enforces that target employee belongs to the same organization and handover is in a valid state.
    """
    handover = verify_handover_organization_access(handover_id, current_user, db)

    if handover.status == "draft":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign a handover in 'draft' status. Handover must be submitted or verified before assignment.",
        )

    target_user = db.query(User).filter(User.id == payload.assigned_to, User.is_active == True).first()
    if not target_user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Target assignee user '{payload.assigned_to}' not found.",
        )

    manager_org_id = get_user_organization_id(current_user, db)
    target_org_id = get_user_organization_id(target_user, db)

    if not manager_org_id or manager_org_id != target_org_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Cannot assign handover to a user outside your organization.",
        )

    prev_assignee_id = handover.assigned_to
    handover.assigned_to = target_user.id
    handover.assigned_at = utc_now()
    handover.updated_at = utc_now()

    action_name = "reassign_handover" if prev_assignee_id else "assign_handover"
    audit = AuditLog(
        action=action_name,
        entity_type="handover",
        entity_id=handover.id,
        user_id=current_user.id,
        details={
            "manager_name": current_user.full_name,
            "manager_id": current_user.id,
            "previous_assigned_to": prev_assignee_id,
            "assigned_to": target_user.id,
            "assignee_name": target_user.full_name,
            "assignee_email": target_user.email,
            "notes": payload.notes,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(handover)
    return handover


@router.get("/{handover_id}/export")
def export_handover_markdown(
    handover_id: str,
    download: bool = Query(False, description="Set true to trigger attachment download"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export formatted Markdown handover report with mandatory authentication and org access check."""
    verify_handover_organization_access(handover_id, current_user, db)
    item = HandoverService.get_or_404(db, handover_id)
    md_content = HandoverService.generate_markdown_report(item)
    filename = f"handover_{item.employee_name.replace(' ', '_').lower()}_{item.id}.md"

    if download:
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return HandoverExportResponse(
        id=item.id,
        filename=filename,
        markdown_content=md_content,
    )
