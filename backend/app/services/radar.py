import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import (
    Project,
    KnowledgeLossIndicator,
    ExtractedKnowledge,
    Document,
    Handover,
    AuditLog,
    KnowledgeRelationship,
    utc_now,
    generate_uuid,
)

logger = logging.getLogger(__name__)


class RadarService:
    """
    Synora Module 5: Knowledge Loss Radar Engine.
    Detects missing architectural decisions (ADR_MISSING), unmaintained modules
    (SECONDARY_OWNER_MISSING), stale documentation (STALE_DOCUMENTATION), and
    undocumented external dependencies. Calculates a transparent, project-specific
    Knowledge Coverage Score (0-100).
    """

    PENALTY_WEIGHTS = {
        "critical": 15.0,
        "high": 8.0,
        "medium": 4.0,
        "low": 2.0,
    }

    @classmethod
    def calculate_project_coverage(cls, db: Session, project: Project) -> Dict[str, Any]:
        """
        Calculate a transparent 0-100 Knowledge Coverage Score for a project.

        Formula:
          Raw Points (max 100) =
            + Documentation Coverage (max 35 pts)
            + Architecture Decision Coverage (max 30 pts)
            + Ownership & Continuity Health (max 20 pts)
            + Knowledge Verification Ratio (max 15 pts)

          Penalties =
            - 15 pts per active Critical gap
            - 8 pts per active High gap
            - 4 pts per active Medium gap
            - 2 pts per active Low gap

          Final Score = max(0.0, min(100.0, round(Raw Points - Total Penalties, 1)))
        """
        # 1. Documentation Factor (max 35)
        docs = project.documents or []
        verified_docs = [d for d in docs if d.processing_status in ("processed", "completed")]
        if docs:
            doc_pts = min(35.0, round((len(verified_docs) * 15.0) + (len(docs) * 5.0), 1))
        else:
            handovers = project.handovers or []
            doc_pts = 12.0 if handovers else 5.0

        # 2. Architectural Decisions Factor (max 30)
        knowledge_items = project.extracted_knowledge or []
        arch_items = [k for k in knowledge_items if k.category in ("architecture", "config")]
        decision_items = [
            k for k in knowledge_items
            if k.category == "decision" and k.verification_status in ("verified", "modified")
        ]
        if arch_items:
            decision_ratio = min(1.0, len(decision_items) / len(arch_items))
            decision_pts = round(decision_ratio * 30.0, 1)
        elif decision_items:
            decision_pts = 30.0
        else:
            decision_pts = 10.0

        # 3. Ownership & Continuity Health (max 20)
        bus_factor = project.bus_factor or 1.0
        handovers = project.handovers or []
        if bus_factor >= 2.0:
            ownership_pts = 20.0
        elif bus_factor > 1.0:
            ownership_pts = 15.0
        elif any(h.status in ("verified", "completed") for h in handovers):
            ownership_pts = 14.0
        elif len(handovers) > 0:
            ownership_pts = 10.0
        else:
            ownership_pts = 5.0

        # 4. Knowledge Verification Ratio (max 15)
        if knowledge_items:
            verified_count = len([
                k for k in knowledge_items
                if k.verification_status in ("verified", "modified")
            ])
            verification_pts = round((verified_count / len(knowledge_items)) * 15.0, 1)
        else:
            verification_pts = 5.0

        raw_score = min(100.0, round(doc_pts + decision_pts + ownership_pts + verification_pts, 1))

        # 5. Query active (unresolved) knowledge gaps
        active_gaps = (
            db.query(KnowledgeLossIndicator)
            .filter(
                KnowledgeLossIndicator.project_id == project.id,
                KnowledgeLossIndicator.is_resolved == False,  # noqa: E712
            )
            .all()
        )

        penalty_breakdown = []
        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0

        for gap in active_gaps:
            sev = (gap.severity or "medium").lower()
            deduction = cls.PENALTY_WEIGHTS.get(sev, 4.0)
            if sev == "critical":
                critical_count += 1
            elif sev == "high":
                high_count += 1
            elif sev == "low":
                low_count += 1
            else:
                medium_count += 1

            penalty_breakdown.append({
                "gap_id": gap.id,
                "module_name": gap.module_name,
                "severity": sev,
                "deduction": deduction,
            })

        total_penalties = round(sum(p["deduction"] for p in penalty_breakdown), 1)
        final_score = max(0.0, min(100.0, round(raw_score - total_penalties, 1)))

        # Letter Grade
        if final_score >= 85.0:
            grade = "A"
        elif final_score >= 70.0:
            grade = "B"
        elif final_score >= 50.0:
            grade = "C"
        elif final_score >= 30.0:
            grade = "D"
        else:
            grade = "F"

        # Update and persist project score
        project.knowledge_coverage_score = final_score
        db.add(project)
        db.commit()

        explanation = {
            "score": final_score,
            "raw_score": raw_score,
            "penalties": total_penalties,
            "formula": (
                "Score = max(0, min(100, (Documentation[35] + Decisions[30] + "
                "Ownership[20] + Verification[15]) - Penalties))"
            ),
            "grade": grade,
            "breakdown": {
                "documentation_points": doc_pts,
                "decision_points": decision_pts,
                "ownership_points": ownership_pts,
                "verification_points": verification_pts,
            },
            "penalty_breakdown": penalty_breakdown,
            "active_gaps_count": len(active_gaps),
            "critical_gaps_count": critical_count,
            "high_gaps_count": high_count,
            "medium_gaps_count": medium_count,
            "low_gaps_count": low_count,
        }

        return explanation

    @classmethod
    def scan_project(
        cls,
        db: Session,
        project_id: str,
        actor_name: str = "Radar Continuous Observer",
    ) -> Tuple[int, List[KnowledgeLossIndicator], Dict[str, Any]]:
        """
        Scan a single project for knowledge loss risks:
        - ADR_MISSING
        - SECONDARY_OWNER_MISSING
        - STALE_DOCUMENTATION
        - UNDOCUMENTED_DEPENDENCY
        Persists newly discovered risks idempotently.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        # Existing active gaps to prevent duplicate records
        existing_gaps = (
            db.query(KnowledgeLossIndicator)
            .filter(
                KnowledgeLossIndicator.project_id == project.id,
                KnowledgeLossIndicator.is_resolved == False,  # noqa: E712
            )
            .all()
        )
        existing_keys = {(g.module_name.lower(), g.gap_type.upper()) for g in existing_gaps}

        new_gaps: List[KnowledgeLossIndicator] = []
        now = utc_now()

        # ----------------------------------------------------
        # 1. Missing ADR Detection (ADR_MISSING)
        # ----------------------------------------------------
        knowledge_items = project.extracted_knowledge or []
        decision_items = [
            k for k in knowledge_items
            if k.category == "decision"
        ]
        decision_labels = {d.label.lower() for d in decision_items}

        arch_items = [
            k for k in knowledge_items
            if k.category in ("architecture", "config")
        ]

        for item in arch_items:
            key = (item.label.lower(), "ADR_MISSING")
            if key not in existing_keys:
                # Check if any decision is linked to this item via relationships or label match
                has_linked_decision = False
                for rel in item.outgoing_relationships or []:
                    if rel.relation_type in ("DECIDED_BY", "IMPLEMENTS", "DOCUMENTED_IN"):
                        has_linked_decision = True
                        break
                for rel in item.incoming_relationships or []:
                    if rel.relation_type in ("DECIDED_BY", "IMPLEMENTS"):
                        has_linked_decision = True
                        break

                if not has_linked_decision and not any(item.label.lower() in dl for dl in decision_labels):
                    is_critical = any(
                        kw in item.label.lower()
                        for kw in ("consensus", "failover", "auth", "security", "ingress", "billing", "settlement", "election")
                    )
                    source_doc = item.document.filename if item.document else "Project Repository"
                    new_gap = KnowledgeLossIndicator(
                        id=generate_uuid("rad-"),
                        project_id=project.id,
                        module_name=item.label,
                        gap_type="ADR_MISSING",
                        severity="critical" if is_critical else "high",
                        description=(
                            f"Architectural module '{item.label}' (Source: {source_doc}, "
                            f"Confidence: {round(item.confidence_score, 2)}) has no linked "
                            "Architecture Decision Record (ADR) documenting design trade-offs and failure scenarios."
                        ),
                        recommended_remediation=(
                            f"Author and commit an ADR documenting decision rationale, operational failure modes, "
                            f"and consensus rules for '{item.label}'."
                        ),
                        is_resolved=False,
                        detected_at=now,
                    )
                    db.add(new_gap)
                    new_gaps.append(new_gap)
                    existing_keys.add(key)

        # ----------------------------------------------------
        # 2. Missing Secondary Owner Detection (SECONDARY_OWNER_MISSING)
        # ----------------------------------------------------
        for item in knowledge_items:
            if item.owner and len(item.owner.strip()) > 0:
                key = (item.label.lower(), "SECONDARY_OWNER_MISSING")
                if key not in existing_keys:
                    # Check if there is an alternate co-owner or maintainer
                    has_secondary = False
                    for rel in item.incoming_relationships or []:
                        if rel.relation_type == "MAINTAINS" and rel.source_node and rel.source_node.owner != item.owner:
                            has_secondary = True
                            break
                    if not has_secondary:
                        is_high_risk = project.bus_factor <= 1.0 or item.category in ("architecture", "config")
                        new_gap = KnowledgeLossIndicator(
                            id=generate_uuid("rad-"),
                            project_id=project.id,
                            module_name=item.label,
                            gap_type="SECONDARY_OWNER_MISSING",
                            severity="high" if is_high_risk else "medium",
                            description=(
                                f"Component '{item.label}' has a single primary owner ('{item.owner}') "
                                f"with no designated secondary maintainer on record."
                            ),
                            recommended_remediation=(
                                f"Assign a secondary engineer to shadow '{item.owner}' on '{item.label}' "
                                "and establish paired reviews to eliminate the Single Point of Failure (SPOF)."
                            ),
                            is_resolved=False,
                            detected_at=now,
                        )
                        db.add(new_gap)
                        new_gaps.append(new_gap)
                        existing_keys.add(key)

        # ----------------------------------------------------
        # 3. Stale Documentation Detection (STALE_DOCUMENTATION)
        # ----------------------------------------------------
        for doc in project.documents or []:
            key = (doc.filename.lower(), "STALE_DOCUMENTATION")
            if key not in existing_keys:
                if doc.uploaded_at:
                    doc_uploaded = (
                        doc.uploaded_at
                        if doc.uploaded_at.tzinfo
                        else doc.uploaded_at.replace(tzinfo=timezone.utc)
                    )
                    doc_age = (now - doc_uploaded).days
                else:
                    doc_age = 0

                is_stale_flagged = False
                if doc.metadata_tags and doc.metadata_tags.get("stale"):
                    is_stale_flagged = True
                
                # Documents older than 30 days or explicitly flagged
                if doc_age >= 30 or is_stale_flagged:
                    new_gap = KnowledgeLossIndicator(
                        id=generate_uuid("rad-"),
                        project_id=project.id,
                        module_name=doc.filename,
                        gap_type="STALE_DOCUMENTATION",
                        severity="medium",
                        description=(
                            f"Documentation file '{doc.filename}' was uploaded {doc_age} days ago "
                            "and has not undergone periodic verification against active code changes."
                        ),
                        recommended_remediation=(
                            f"Conduct a verification audit on '{doc.filename}' to validate that code references, "
                            "configuration parameters, and deployment steps match production."
                        ),
                        is_resolved=False,
                        detected_at=now,
                    )
                    db.add(new_gap)
                    new_gaps.append(new_gap)
                    existing_keys.add(key)

        # ----------------------------------------------------
        # 4. Undocumented Dependency Detection (UNDOCUMENTED_DEPENDENCY)
        # ----------------------------------------------------
        for handover in project.handovers or []:
            for dep in (handover.critical_dependencies or []):
                dep_name = str(dep).strip()
                if not dep_name:
                    continue
                key = (dep_name.lower(), "UNDOCUMENTED_DEPENDENCY")
                if key not in existing_keys:
                    # Check if any document mentions this dependency
                    documented = any(
                        dep_name.lower() in (d.raw_text or "").lower()
                        for d in project.documents or []
                    )
                    if not documented:
                        new_gap = KnowledgeLossIndicator(
                            id=generate_uuid("rad-"),
                            project_id=project.id,
                            module_name=dep_name,
                            gap_type="UNDOCUMENTED_DEPENDENCY",
                            severity="medium",
                            description=(
                                f"Handover dossier by {handover.employee_name} ({handover.role}) flags critical "
                                f"external dependency '{dep_name}', but no integration runbook or recovery documentation exists."
                            ),
                            recommended_remediation=(
                                f"Document operational runbook, fallback credentials, and SLA contracts for '{dep_name}'."
                            ),
                            is_resolved=False,
                            detected_at=now,
                        )
                        db.add(new_gap)
                        new_gaps.append(new_gap)
                        existing_keys.add(key)

        if new_gaps:
            db.commit()

        # Recalculate coverage score immediately
        explanation = cls.calculate_project_coverage(db, project)

        # Audit log entry
        audit = AuditLog(
            id=generate_uuid("aud-"),
            action="RUN_RADAR_SCAN",
            entity_type="PROJECT",
            entity_id=project.id,
            details={
                "project_name": project.name,
                "actor_name": actor_name,
                "new_gaps_found": len(new_gaps),
                "knowledge_coverage_score": explanation["score"],
                "grade": explanation["grade"],
            },
            timestamp=now,
        )
        db.add(audit)
        db.commit()

        return len(new_gaps), new_gaps, explanation

    @classmethod
    def resolve_gap(
        cls,
        db: Session,
        gap_id: str,
        actor_name: str,
        notes: Optional[str] = None,
    ) -> Tuple[KnowledgeLossIndicator, Dict[str, Any]]:
        """
        Mark a knowledge gap as resolved, record remediation audit details,
        and recalculate project coverage score.
        """
        gap = db.query(KnowledgeLossIndicator).filter(KnowledgeLossIndicator.id == gap_id).first()
        if not gap:
            raise ValueError(f"Knowledge gap with ID '{gap_id}' not found.")

        now = utc_now()
        gap.is_resolved = True
        gap.resolved_at = now

        if notes:
            timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
            resolution_entry = f"[Remediated by {actor_name} on {timestamp_str}]: {notes.strip()}"
            if gap.recommended_remediation:
                gap.recommended_remediation = f"{resolution_entry}\n\nHistorical Remediation Guide:\n{gap.recommended_remediation}"
            else:
                gap.recommended_remediation = resolution_entry

        db.commit()
        db.refresh(gap)

        # Recalculate project coverage score
        project = gap.project or db.query(Project).filter(Project.id == gap.project_id).first()
        explanation = cls.calculate_project_coverage(db, project)

        # Audit log entry
        audit = AuditLog(
            id=generate_uuid("aud-"),
            action="RESOLVE_KNOWLEDGE_GAP",
            entity_type="KNOWLEDGE_LOSS_INDICATOR",
            entity_id=gap.id,
            details={
                "gap_id": gap.id,
                "module_name": gap.module_name,
                "gap_type": gap.gap_type,
                "resolved_by": actor_name,
                "notes": notes,
                "updated_coverage_score": explanation["score"],
            },
            timestamp=now,
        )
        db.add(audit)
        db.commit()

        return gap, explanation

    @classmethod
    def get_overview(cls, db: Session, project_id: Optional[str] = None, project_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Produce a high-level radar overview with coverage breakdown and risk counts.
        """
        query = db.query(Project)
        if project_id:
            query = query.filter(Project.id == project_id)
        elif project_ids is not None:
            query = query.filter(Project.id.in_(project_ids)) if project_ids else query.filter(Project.id == "__no_access__")
        projects = query.all()

        project_summaries = []
        total_score = 0.0
        total_active_gaps = 0
        total_critical = 0
        total_high = 0
        total_medium = 0
        total_resolved = 0

        for prj in projects:
            explanation = cls.calculate_project_coverage(db, prj)
            total_score += explanation["score"]

            active_gaps_count = explanation["active_gaps_count"]
            critical_count = explanation["critical_gaps_count"]
            high_count = explanation["high_gaps_count"]
            medium_count = explanation["medium_gaps_count"]

            resolved_count = (
                db.query(KnowledgeLossIndicator)
                .filter(
                    KnowledgeLossIndicator.project_id == prj.id,
                    KnowledgeLossIndicator.is_resolved == True,  # noqa: E712
                )
                .count()
            )

            total_active_gaps += active_gaps_count
            total_critical += critical_count
            total_high += high_count
            total_medium += medium_count
            total_resolved += resolved_count

            project_summaries.append({
                "id": prj.id,
                "name": prj.name,
                "slug": prj.slug,
                "bus_factor": prj.bus_factor,
                "knowledge_coverage_score": explanation["score"],
                "grade": explanation["grade"],
                "active_gaps_count": active_gaps_count,
                "critical_gaps_count": critical_count,
                "explanation": explanation,
            })

        avg_score = round(total_score / len(projects), 1) if projects else 0.0
        if avg_score >= 85.0:
            overall_grade = "A"
        elif avg_score >= 70.0:
            overall_grade = "B"
        elif avg_score >= 50.0:
            overall_grade = "C"
        elif avg_score >= 30.0:
            overall_grade = "D"
        else:
            overall_grade = "F"

        return {
            "average_coverage_score": avg_score,
            "overall_grade": overall_grade,
            "total_active_gaps": total_active_gaps,
            "critical_gaps": total_critical,
            "high_gaps": total_high,
            "medium_gaps": total_medium,
            "resolved_gaps": total_resolved,
            "projects": project_summaries,
            "scoring_formula": (
                "Score = max(0, min(100, (Documentation[35] + Decisions[30] + "
                "Ownership[20] + Verification[15]) - Penalties))"
            ),
        }
