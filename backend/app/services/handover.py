"""
Handover Lifecycle Service

Implements the finite state machine (FSM), structured validation,
manager reviews, change request feedback, and Markdown report export.
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import Handover, AuditLog, Project, User

# Valid status transitions
# draft -> submitted
# submitted -> under_review, changes_requested, verified
# under_review -> changes_requested, verified
# changes_requested -> submitted, draft
# verified -> completed
# completed -> (terminal state, no forward transitions)
VALID_TRANSITIONS: Dict[str, List[str]] = {
    "draft": ["submitted"],
    "submitted": ["under_review", "changes_requested", "verified"],
    "under_review": ["changes_requested", "verified"],
    "changes_requested": ["submitted", "draft"],
    "verified": ["completed"],
    "completed": [],
}


def calculate_readiness_score(handover: Handover) -> float:
    """
    Calculate dynamic readiness score (0% to 100%) based on:
    - Status weighting (verified/completed gets highest)
    - Completed tasks vs Pending tasks
    - Unresolved blockers penalty
    - Evidence & documentation links availability
    """
    if handover.status == "completed":
        return 100.0
    if handover.status == "verified":
        return 95.0

    completed_tasks = handover.completed_tasks or []
    pending_tasks = handover.pending_tasks or []
    total_tasks = len(completed_tasks) + len(pending_tasks)

    task_score = (len(completed_tasks) / total_tasks * 60.0) if total_tasks > 0 else 20.0

    # Links & documentation bonus (up to 20%)
    links_score = 0.0
    if handover.repository_links:
        links_score += 7.0
    if handover.documentation_links:
        links_score += 7.0
    if handover.database_references:
        links_score += 6.0

    # Dependencies & notes bonus (up to 20%)
    context_score = 0.0
    if handover.key_responsibilities:
        context_score += 7.0
    if handover.critical_dependencies:
        context_score += 7.0
    if handover.important_notes:
        context_score += 6.0

    raw_score = task_score + links_score + context_score

    # Unresolved blockers penalty (5% per blocker, up to 30%)
    blockers = handover.unresolved_blockers or []
    penalty = min(len(blockers) * 5.0, 30.0)

    score = max(0.0, min(90.0, raw_score - penalty))
    return round(score, 1)


class HandoverService:

    @staticmethod
    def get_or_404(db: Session, handover_id: str) -> Handover:
        item = db.query(Handover).filter(Handover.id == handover_id).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Handover report with ID '{handover_id}' was not found.")
        return item

    @staticmethod
    def validate_transition(current_status: str, target_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(current_status, [])
        if target_status not in allowed:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_STATUS_TRANSITION",
                    "message": f"Cannot transition handover from '{current_status}' to '{target_status}'. Allowed transitions: {allowed}",
                    "current_status": current_status,
                    "target_status": target_status,
                    "allowed_transitions": allowed,
                },
            )

    @classmethod
    def submit(cls, db: Session, handover_id: str, employee_name: Optional[str] = None) -> Handover:
        handover = cls.get_or_404(db, handover_id)
        cls.validate_transition(handover.status, "submitted")

        # Validate minimum submission requirements
        if not handover.key_responsibilities and not handover.completed_tasks:
            raise HTTPException(
                status_code=422,
                detail="Cannot submit handover without documented responsibilities or completed tasks."
            )

        handover.status = "submitted"
        handover.readiness_score = calculate_readiness_score(handover)
        handover.updated_at = datetime.now(timezone.utc)

        db.add(AuditLog(
            action="submit_handover",
            entity_type="handover",
            entity_id=handover.id,
            details={
                "previous_status": "draft",
                "new_status": "submitted",
                "employee": employee_name or handover.employee_name,
            }
        ))
        db.commit()
        db.refresh(handover)
        return handover

    @classmethod
    def start_review(cls, db: Session, handover_id: str, reviewer_name: str) -> Handover:
        handover = cls.get_or_404(db, handover_id)
        cls.validate_transition(handover.status, "under_review")

        handover.status = "under_review"
        handover.reviewed_by = reviewer_name
        handover.updated_at = datetime.now(timezone.utc)

        db.add(AuditLog(
            action="start_handover_review",
            entity_type="handover",
            entity_id=handover.id,
            details={"reviewer": reviewer_name}
        ))
        db.commit()
        db.refresh(handover)
        return handover

    @classmethod
    def approve(
        cls,
        db: Session,
        handover_id: str,
        reviewer_name: str,
        notes: Optional[str] = None
    ) -> Handover:
        handover = cls.get_or_404(db, handover_id)
        cls.validate_transition(handover.status, "verified")

        now = datetime.now(timezone.utc)
        handover.status = "verified"
        handover.reviewed_by = reviewer_name
        handover.reviewed_at = now
        handover.review_decision = "approved"
        handover.review_notes = notes or "Handover reviewed and approved by management."
        handover.readiness_score = calculate_readiness_score(handover)
        handover.updated_at = now

        db.add(AuditLog(
            action="approve_handover",
            entity_type="handover",
            entity_id=handover.id,
            details={
                "reviewer": reviewer_name,
                "decision": "approved",
                "notes": notes,
                "readiness_score": handover.readiness_score,
            }
        ))
        db.commit()
        db.refresh(handover)
        return handover

    @classmethod
    def request_changes(
        cls,
        db: Session,
        handover_id: str,
        reviewer_name: str,
        reason: str
    ) -> Handover:
        if not reason or not reason.strip():
            raise HTTPException(
                status_code=422,
                detail="A clear reason must be provided when requesting changes on a handover."
            )

        handover = cls.get_or_404(db, handover_id)
        cls.validate_transition(handover.status, "changes_requested")

        now = datetime.now(timezone.utc)
        handover.status = "changes_requested"
        handover.reviewed_by = reviewer_name
        handover.reviewed_at = now
        handover.review_decision = "changes_requested"
        handover.review_notes = reason.strip()
        handover.readiness_score = calculate_readiness_score(handover)
        handover.updated_at = now

        db.add(AuditLog(
            action="request_handover_changes",
            entity_type="handover",
            entity_id=handover.id,
            details={
                "reviewer": reviewer_name,
                "decision": "changes_requested",
                "reason": reason.strip(),
            }
        ))
        db.commit()
        db.refresh(handover)
        return handover

    @classmethod
    def mark_completed(cls, db: Session, handover_id: str, user_name: str) -> Handover:
        handover = cls.get_or_404(db, handover_id)
        cls.validate_transition(handover.status, "completed")

        now = datetime.now(timezone.utc)
        handover.status = "completed"
        handover.readiness_score = 100.0
        handover.updated_at = now

        db.add(AuditLog(
            action="complete_handover",
            entity_type="handover",
            entity_id=handover.id,
            details={"completed_by": user_name}
        ))
        db.commit()
        db.refresh(handover)
        return handover

    @classmethod
    def generate_markdown_report(cls, handover: Handover) -> str:
        """
        Synthesizes a clean, readable Markdown export of the handover dossier.
        """
        lines = []
        lines.append(f"# Synora Handover Dossier: {handover.employee_name}")
        lines.append("")
        lines.append(f"> **Document ID:** `{handover.id}`  ")
        lines.append(f"> **Status:** `{handover.status.upper()}`  ")
        lines.append(f"> **Readiness Score:** **{handover.readiness_score}%**  ")
        lines.append(f"> **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 1. Role & Project Profile")
        lines.append(f"- **Employee:** {handover.employee_name}")
        lines.append(f"- **Role:** {handover.role}")
        lines.append(f"- **Department:** {handover.department}")
        lines.append(f"- **Transition Type:** {handover.transition_type.replace('_', ' ').capitalize()}")
        if handover.project_name:
            lines.append(f"- **Project:** {handover.project_name}")
        if handover.project_description:
            lines.append(f"- **Project Summary:** {handover.project_description}")
        lines.append("")

        lines.append("## 2. Review & Verification Status")
        if handover.reviewed_by:
            lines.append(f"- **Reviewed By:** {handover.reviewed_by}")
            if handover.reviewed_at:
                lines.append(f"- **Reviewed At:** {handover.reviewed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            lines.append(f"- **Decision:** `{handover.review_decision or 'N/A'}`")
            if handover.review_notes:
                lines.append(f"- **Manager Feedback / Notes:**")
                lines.append(f"  > {handover.review_notes}")
        else:
            lines.append("- *Awaiting manager review and sign-off.*")
        lines.append("")

        lines.append("## 3. Key Responsibilities & Ownership")
        if handover.key_responsibilities:
            for item in handover.key_responsibilities:
                lines.append(f"- {item}")
        else:
            lines.append("- *None specified.*")
        lines.append("")

        lines.append("## 4. Completed Work & Evidence")
        if handover.completed_tasks:
            for item in handover.completed_tasks:
                lines.append(f"- [x] {item}")
        else:
            lines.append("- *No completed tasks documented.*")
        lines.append("")

        lines.append("## 5. Pending & Incomplete Tasks")
        if handover.pending_tasks:
            for item in handover.pending_tasks:
                lines.append(f"- [ ] {item}")
        else:
            lines.append("- *No pending tasks reported.*")
        lines.append("")

        lines.append("## 6. Critical Dependencies & External Systems")
        if handover.critical_dependencies:
            for item in handover.critical_dependencies:
                lines.append(f"- ⚠️ {item}")
        else:
            lines.append("- *None documented.*")
        lines.append("")

        lines.append("## 7. Unresolved Blockers & Knowledge Gaps")
        if handover.unresolved_blockers:
            for item in handover.unresolved_blockers:
                lines.append(f"- 🚨 **BLOCKER:** {item}")
        else:
            lines.append("- *Zero unresolved blockers. Handover cleared for completion.*")
        lines.append("")

        lines.append("## 8. Technical Links & References")
        if handover.repository_links:
            lines.append("### Repositories")
            for link in handover.repository_links:
                lines.append(f"- [{link}]({link})")
        if handover.documentation_links:
            lines.append("### Documentation")
            for link in handover.documentation_links:
                lines.append(f"- [{link}]({link})")
        if handover.database_references:
            lines.append("### Database References")
            for ref in handover.database_references:
                lines.append(f"- `{ref}`")
        lines.append("")

        if handover.important_notes:
            lines.append("## 9. Important Notes & Architectural Caveats")
            lines.append(handover.important_notes)
            lines.append("")

        if handover.recommended_next_actions:
            lines.append("## 10. Recommended Next Actions for Successor")
            for action in handover.recommended_next_actions:
                lines.append(f"1. {action}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by Synora Knowledge Continuity Platform.*")
        return "\n".join(lines)

