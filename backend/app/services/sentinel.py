import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import (
    Project,
    Handover,
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    SentinelEvent,
    AuditLog,
    utc_now,
    generate_uuid,
)

logger = logging.getLogger(__name__)


class SentinelService:
    """
    Synora Module 7: Synora Sentinel Engine.
    Continuous integrity observer and handover verification engine.
    Detects missing documents, incomplete sections, unsupported completion claims,
    contradictory information, broken references, and missing environment setup instructions.
    Distinguishes verified facts, unverified claims, and suspected inconsistencies.
    """

    PENALTY_WEIGHTS = {
        "critical": 20.0,
        "high": 10.0,
        "medium": 5.0,
        "low": 2.0,
    }

    ENV_KEYWORDS = [
        "environment",
        "setup",
        "prerequisite",
        "prerequisites",
        "docker",
        "docker-compose",
        "install",
        "npm run",
        "python",
        "venv",
        "virtualenv",
        ".env",
        "database_url",
        "port",
        "runbook",
        "quickstart",
    ]

    PLACEHOLDER_PATTERN = re.compile(
        r"^(todo|tbd|none|n/a|na|placeholder|localhost|temp|nil)$",
        re.IGNORECASE,
    )

    @classmethod
    def calculate_integrity_score(
        cls, db: Session, project: Project, handovers: Optional[List[Handover]] = None
    ) -> Dict[str, Any]:
        """
        Calculates a transparent Handover Integrity Score (0-100) for a project.

        Formula:
          Base Points (max 100):
            + Section Completeness (max 30 pts): 5 pts for each of 6 standard handover sections populated
            + Verified Documentation Linkage (max 30 pts): 15 pts per attached document
            + Supported Task Evidence Ratio (max 25 pts): % of completed tasks backed by verified citations
            + Environment Setup Clarity (max 15 pts): Runbook and reproduction instructions present

          Penalties:
            - 20 pts per active Critical Sentinel finding
            - 10 pts per active High finding
            - 5 pts per active Medium finding
            - 2 pts per active Low finding

          Final Score = max(0.0, min(100.0, round(Base - Penalties, 1)))
        """
        target_handovers = handovers if handovers is not None else (project.handovers or [])

        if not target_handovers:
            # Baseline if no handovers initiated yet
            base_score = 65.0 if project.documents else 40.0
        else:
            total_section_pts = 0.0
            total_doc_pts = 0.0
            total_task_pts = 0.0
            total_env_pts = 0.0

            for h in target_handovers:
                # 1. Section completeness (max 30)
                sections = [
                    h.key_responsibilities,
                    h.critical_dependencies,
                    h.unresolved_blockers,
                    h.completed_tasks,
                    h.pending_tasks,
                    h.recommended_next_actions,
                ]
                populated_sections = sum(1 for s in sections if s and len(s) > 0)
                section_pts = round((populated_sections / 6.0) * 30.0, 1)

                # 2. Attached docs (max 30)
                docs = h.documents or []
                doc_pts = min(30.0, len(docs) * 15.0)

                # 3. Supported task evidence (max 25)
                comp_tasks = h.completed_tasks or []
                if comp_tasks:
                    supported = 0
                    all_text = " ".join([d.raw_text or "" for d in docs]).lower()
                    for t in comp_tasks:
                        # Simple keyword check in attached docs
                        words = [w.lower() for w in str(t).split() if len(w) > 4]
                        if any(w in all_text for w in words):
                            supported += 1
                    task_pts = round((supported / len(comp_tasks)) * 25.0, 1)
                else:
                    task_pts = 15.0

                # 4. Environment setup instructions (max 15)
                notes_text = (h.important_notes or "").lower()
                doc_text = " ".join([d.raw_text or "" for d in docs]).lower()
                combined_env = f"{notes_text} {doc_text}"
                has_env = any(kw in combined_env for kw in cls.ENV_KEYWORDS)
                env_pts = 15.0 if has_env else 0.0

                total_section_pts += section_pts
                total_doc_pts += doc_pts
                total_task_pts += task_pts
                total_env_pts += env_pts

            n = max(1, len(target_handovers))
            base_score = min(
                100.0,
                round(
                    (total_section_pts / n)
                    + (total_doc_pts / n)
                    + (total_task_pts / n)
                    + (total_env_pts / n),
                    1,
                ),
            )

        # Active Sentinel findings penalties
        active_events = (
            db.query(SentinelEvent)
            .filter(
                SentinelEvent.project_id == project.id,
                SentinelEvent.is_resolved == False,  # noqa: E712
            )
            .all()
        )

        total_penalties = 0.0
        crit_count = 0
        high_count = 0
        med_count = 0

        for ev in active_events:
            sev = (ev.risk_level or "medium").lower()
            deduction = cls.PENALTY_WEIGHTS.get(sev, 5.0)
            total_penalties += deduction
            if sev == "critical":
                crit_count += 1
            elif sev == "high":
                high_count += 1
            else:
                med_count += 1

        final_score = max(0.0, min(100.0, round(base_score - total_penalties, 1)))

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

        return {
            "project_id": project.id,
            "project_name": project.name,
            "integrity_score": final_score,
            "base_score": base_score,
            "penalties": total_penalties,
            "grade": grade,
            "active_findings_count": len(active_events),
            "critical_count": crit_count,
            "high_count": high_count,
            "medium_count": med_count,
            "handovers_count": len(target_handovers),
            "bus_factor": project.bus_factor,
        }

    @classmethod
    def scan_handover(
        cls,
        db: Session,
        handover: Handover,
        actor_name: str = "Sentinel Scanner",
    ) -> Tuple[int, List[SentinelEvent]]:
        """
        Runs comprehensive handover integrity checks:
        1. Missing required project documents
        2. Incomplete handover sections
        3. Broken or missing repository / resource references
        4. Tasks marked completed without supporting evidence
        5. Inconsistencies between completed work and pending/blockers
        6. Missing environment setup instructions
        """
        project = handover.project or db.query(Project).filter(Project.id == handover.project_id).first()
        project_name = project.name if project else (handover.project_name or "Unknown Project")
        project_id = project.id if project else handover.project_id

        # Query existing unresolved events to prevent duplicates
        existing_events = (
            db.query(SentinelEvent)
            .filter(
                SentinelEvent.project_id == project_id,
                SentinelEvent.is_resolved == False,  # noqa: E712
            )
            .all()
        )

        def has_active_event(cat: str, search_snippet: str) -> bool:
            snippet = search_snippet.strip().lower()
            return any(
                e.category == cat and snippet in e.description.lower()
                for e in existing_events
            )

        new_events: List[SentinelEvent] = []
        now = utc_now()

        docs = handover.documents or []
        doc_raw_corpus = " ".join([(d.raw_text or "").lower() for d in docs])
        proj_docs = project.documents or [] if project else []
        proj_corpus = " ".join([(d.raw_text or "").lower() for d in proj_docs])

        # ----------------------------------------------------
        # 1. Missing Required Project Documents
        # ----------------------------------------------------
        if len(docs) == 0:
            if not has_active_event("MISSING_DOCUMENTATION", handover.employee_name):
                is_crit = handover.status in ("submitted", "under_review")
                ev = SentinelEvent(
                    id=generate_uuid("risk-"),
                    project_id=project_id,
                    project_name=project_name,
                    risk_level="critical" if is_crit else "high",
                    category="MISSING_DOCUMENTATION",
                    description=(
                        f"Handover dossier for {handover.employee_name} ({handover.role}) has 0 attached "
                        "verification documents. Institutional transition dossiers require at least one verified "
                        "architectural specification or system runbook before approval."
                    ),
                    recommended_action=(
                        f"Upload architectural documentation, system specifications, or runbook (.pdf, .md, .txt) "
                        f"to Handover '{handover.id}'."
                    ),
                    is_resolved=False,
                    detected_at=now,
                )
                db.add(ev)
                new_events.append(ev)
                existing_events.append(ev)

        # ----------------------------------------------------
        # 2. Incomplete Handover Sections
        # ----------------------------------------------------
        mandatory_sections = [
            ("key_responsibilities", handover.key_responsibilities, "Key Responsibilities"),
            ("critical_dependencies", handover.critical_dependencies, "Critical Dependencies"),
            ("completed_tasks", handover.completed_tasks, "Completed Tasks"),
        ]

        for sec_name, sec_val, sec_label in mandatory_sections:
            if not sec_val or len(sec_val) == 0:
                if not has_active_event("INCOMPLETE_HANDOVER_SECTION", sec_label):
                    ev = SentinelEvent(
                        id=generate_uuid("risk-"),
                        project_id=project_id,
                        project_name=project_name,
                        risk_level="high",
                        category="INCOMPLETE_HANDOVER_SECTION",
                        description=(
                            f"Handover dossier for {handover.employee_name} is missing mandatory section '{sec_label}'. "
                            "Empty responsibilities or dependencies leave the successor engineer without operational scope."
                        ),
                        recommended_action=(
                            f"Complete the '{sec_label}' section with explicit operational duties and dependencies "
                            "before manager review."
                        ),
                        is_resolved=False,
                        detected_at=now,
                    )
                    db.add(ev)
                    new_events.append(ev)
                    existing_events.append(ev)

        # ----------------------------------------------------
        # 3. Broken or Missing Repository & Resource References
        # ----------------------------------------------------
        all_refs = (handover.repository_links or []) + (handover.documentation_links or []) + (handover.database_references or [])
        if not all_refs:
            if not has_active_event("BROKEN_OR_MISSING_REFERENCE", "contains no technical repository"):
                ev = SentinelEvent(
                    id=generate_uuid("risk-"),
                    project_id=project_id,
                    project_name=project_name,
                    risk_level="medium",
                    category="BROKEN_OR_MISSING_REFERENCE",
                    description=(
                        f"Handover for {handover.employee_name} contains no technical repository, documentation, "
                        "or database connection references."
                    ),
                    recommended_action=(
                        "Provide verifiable repository URLs, confluence/wiki documentation links, or database "
                        "cluster identifiers in the handover technical references."
                    ),
                    is_resolved=False,
                    detected_at=now,
                )
                db.add(ev)
                new_events.append(ev)
                existing_events.append(ev)
        else:
            # Check for placeholder references
            for ref in all_refs:
                ref_str = str(ref).strip()
                if cls.PLACEHOLDER_PATTERN.match(ref_str) or ref_str in ("http://localhost", "https://"):
                    if not has_active_event("BROKEN_OR_MISSING_REFERENCE", ref_str):
                        ev = SentinelEvent(
                            id=generate_uuid("risk-"),
                            project_id=project_id,
                            project_name=project_name,
                            risk_level="high",
                            category="BROKEN_OR_MISSING_REFERENCE",
                            description=(
                                f"Handover contains placeholder or unresolvable technical reference: '{ref_str}'. "
                                "Successors cannot locate required codebase assets or deployment endpoints."
                            ),
                            recommended_action=(
                                f"Replace placeholder reference '{ref_str}' with an accessible repository URL "
                                "or production resource URI."
                            ),
                            is_resolved=False,
                            detected_at=now,
                        )
                        db.add(ev)
                        new_events.append(ev)
                        existing_events.append(ev)

        # ----------------------------------------------------
        # 4. Tasks Marked Completed Without Supporting Evidence
        # ----------------------------------------------------
        comp_tasks = handover.completed_tasks or []
        for task in comp_tasks:
            task_str = str(task).strip()
            if not task_str:
                continue

            # Extract substantive keywords (>4 chars)
            keywords = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_-]{4,}\b", task_str)]
            has_doc_support = False

            if keywords:
                # Check against attached docs first, then project docs
                combined_corpus = f"{doc_raw_corpus} {proj_corpus}"
                matches = sum(1 for kw in keywords if kw in combined_corpus)
                if matches >= min(2, len(keywords)):
                    has_doc_support = True

            # If no docs are attached, or no keyword evidence found in docs
            if len(docs) == 0 or not has_doc_support:
                snippet = task_str[:25]
                if not has_active_event("UNSUPPORTED_COMPLETION_CLAIM", snippet):
                    is_critical_task = any(
                        kw in task_str.lower()
                        for kw in ("migration", "consensus", "production", "security", "failover", "database", "auth", "billing")
                    )
                    ev = SentinelEvent(
                        id=generate_uuid("risk-"),
                        project_id=project_id,
                        project_name=project_name,
                        risk_level="critical" if is_critical_task else "high",
                        category="UNSUPPORTED_COMPLETION_CLAIM",
                        description=(
                            f"Task '{task_str}' was marked completed by {handover.employee_name}, but zero verifiable "
                            "citations or corroborating mentions were found in attached documentation or extracted knowledge."
                        ),
                        recommended_action=(
                            f"Attach pull request links, test verification reports, or design documentation "
                            f"validating that '{task_str}' was completed and verified in production."
                        ),
                        is_resolved=False,
                        detected_at=now,
                    )
                    db.add(ev)
                    new_events.append(ev)
                    existing_events.append(ev)

        # ----------------------------------------------------
        # 5. Inconsistencies Between Completed Work and Pending/Blockers
        # ----------------------------------------------------
        pending = handover.pending_tasks or []
        blockers = handover.unresolved_blockers or []
        conflicting_candidates = pending + blockers

        for task in comp_tasks:
            task_str = str(task).strip().lower()
            task_words = set(re.findall(r"\b[A-Za-z0-9_-]{4,}\b", task_str))
            if not task_words:
                continue

            for conflict in conflicting_candidates:
                conflict_str = str(conflict).strip().lower()
                conflict_words = set(re.findall(r"\b[A-Za-z0-9_-]{4,}\b", conflict_str))
                overlap = task_words.intersection(conflict_words)

                # If significant token overlap between completed task and pending/blocker
                if len(overlap) >= 2 or (len(overlap) == 1 and any(len(w) >= 7 for w in overlap)):
                    snippet = task_str[:25]
                    if not has_active_event("CONTRADICTORY_HANDOVER_INFO", snippet):
                        ev = SentinelEvent(
                            id=generate_uuid("risk-"),
                            project_id=project_id,
                            project_name=project_name,
                            risk_level="critical",
                            category="CONTRADICTORY_HANDOVER_INFO",
                            description=(
                                f"Contradiction detected in {handover.employee_name}'s handover: Task '{task}' is marked "
                                f"as completed in completed_tasks, but also appears in pending tasks / unresolved blockers ('{conflict}')."
                            ),
                            recommended_action=(
                                f"Resolve deliverable status ambiguity for '{task}': verify with {handover.employee_name} "
                                "whether the deliverable is fully verified or remains blocked."
                            ),
                            is_resolved=False,
                            detected_at=now,
                        )
                        db.add(ev)
                        new_events.append(ev)
                        existing_events.append(ev)
                        break

        # ----------------------------------------------------
        # 6. Missing Environment Setup Instructions
        # ----------------------------------------------------
        notes_text = (handover.important_notes or "").lower()
        combined_text = f"{notes_text} {doc_raw_corpus}"
        has_setup_instructions = any(kw in combined_text for kw in cls.ENV_KEYWORDS)

        if not has_setup_instructions:
            if not has_active_event("MISSING_ENVIRONMENT_SETUP", handover.id):
                ev = SentinelEvent(
                    id=generate_uuid("risk-"),
                    project_id=project_id,
                    project_name=project_name,
                    risk_level="medium",
                    category="MISSING_ENVIRONMENT_SETUP",
                    description=(
                        f"No reproducible local or containerized environment setup instructions were found in "
                        f"Handover '{handover.id}' or its attached documents. Incoming successor engineers will "
                        "experience onboarding friction and environment recreation delays."
                    ),
                    recommended_action=(
                        "Include local reproduction steps, required toolchains, environment variables, and run "
                        "commands in Handover Notes or an attached runbook."
                    ),
                    is_resolved=False,
                    detected_at=now,
                )
                db.add(ev)
                new_events.append(ev)
                existing_events.append(ev)

        if new_events:
            db.commit()

        return len(new_events), new_events

    @classmethod
    def scan_project(
        cls,
        db: Session,
        project_id: str,
        actor_name: str = "Sentinel Continuous Observer",
    ) -> Tuple[int, List[SentinelEvent], Dict[str, Any]]:
        """
        Runs full Sentinel inspection across a project:
        - Scans every handover
        - Inspects Single Point of Failure (SPOF) risks based on Bus Factor
        - Calculates dynamic Handover Integrity Score
        - Records immutable AuditLog entry
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        total_new = 0
        all_new: List[SentinelEvent] = []

        # 1. Scan all handovers
        for ho in project.handovers or []:
            count, evs = cls.scan_handover(db, ho, actor_name=actor_name)
            total_new += count
            all_new.extend(evs)

        # 2. Check SPOF based on Bus Factor
        # Zero means ownership data is unknown. Do not report a measured SPOF
        # until a positive bus-factor value has been established from evidence.
        if project.bus_factor is not None and 0.0 < project.bus_factor <= 1.0:
            existing_spof = (
                db.query(SentinelEvent)
                .filter(
                    SentinelEvent.project_id == project.id,
                    SentinelEvent.category == "SPOF_RISK",
                    SentinelEvent.is_resolved == False,  # noqa: E712
                )
                .first()
            )
            has_completed_handover = any(h.status == "completed" for h in project.handovers or [])
            if not existing_spof and not has_completed_handover:
                spof_ev = SentinelEvent(
                    id=generate_uuid("risk-"),
                    project_id=project.id,
                    project_name=project.name,
                    risk_level="critical",
                    category="SPOF_RISK",
                    description=(
                        f"Repository '{project.name}' has Bus Factor {project.bus_factor:.1f} (Single Point of Failure). "
                        "Critical operational knowledge and write ownership are concentrated in a single engineer "
                        "with no completed transition dossier on record."
                    ),
                    recommended_action=(
                        f"Initiate an emergency handover dossier and cross-train a secondary engineer on '{project.name}' immediately."
                    ),
                    is_resolved=False,
                    detected_at=utc_now(),
                )
                db.add(spof_ev)
                db.commit()
                all_new.append(spof_ev)
                total_new += 1

        # 3. Calculate integrity score
        integrity_summary = cls.calculate_integrity_score(db, project)

        # 4. Audit Log
        audit = AuditLog(
            id=generate_uuid("aud-"),
            action="RUN_SENTINEL_SCAN",
            entity_type="PROJECT",
            entity_id=project.id,
            details={
                "project_name": project.name,
                "actor_name": actor_name,
                "new_findings_discovered": total_new,
                "integrity_score": integrity_summary["integrity_score"],
                "grade": integrity_summary["grade"],
            },
            timestamp=utc_now(),
        )
        db.add(audit)
        db.commit()

        return total_new, all_new, integrity_summary

    @classmethod
    def resolve_finding(
        cls,
        db: Session,
        risk_id: str,
        actor_name: str,
        action: str = "resolve",
        notes: Optional[str] = None,
    ) -> Tuple[SentinelEvent, float]:
        """
        Remediate or resolve an identified Sentinel finding.
        Supports:
        - 'resolve': marks finding resolved with resolution notes
        - 'request_changes': requests changes on associated handover and records manager critique
        """
        event = db.query(SentinelEvent).filter(SentinelEvent.id == risk_id).first()
        if not event:
            raise ValueError(f"Sentinel finding with ID '{risk_id}' not found.")

        now = utc_now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        if action == "resolve":
            event.is_resolved = True
            event.resolved_at = now
            resolution_entry = f"[Remediated by {actor_name} on {timestamp_str}]: {notes or 'Verified and resolved.'}"
            event.recommended_action = f"{resolution_entry}\n\nPrescribed Action:\n{event.recommended_action}"
        elif action == "request_changes":
            # If associated with a handover in submitted / under_review, change status
            project = event.project or db.query(Project).filter(Project.id == event.project_id).first()
            if project and project.handovers:
                for ho in project.handovers:
                    if ho.status in ("submitted", "under_review"):
                        ho.status = "changes_requested"
                        ho.review_decision = "changes_requested"
                        ho.reviewed_by = actor_name
                        ho.reviewed_at = now
                        ho.review_notes = f"[Sentinel Finding Flagged by {actor_name}]: {notes or event.description}"
            event.recommended_action = f"[Changes Requested by {actor_name} on {timestamp_str}]: {notes or 'Changes requested on handover dossier.'}\n\n{event.recommended_action}"

        db.commit()
        db.refresh(event)

        # Recalculate project integrity score
        project = event.project or db.query(Project).filter(Project.id == event.project_id).first()
        integrity_score = 75.0
        if project:
            summary = cls.calculate_integrity_score(db, project)
            integrity_score = summary["integrity_score"]

        # Audit log entry
        audit = AuditLog(
            id=generate_uuid("aud-"),
            action="RESOLVE_SENTINEL_FINDING" if action == "resolve" else "SENTINEL_REQUEST_CHANGES",
            entity_type="SENTINEL_EVENT",
            entity_id=event.id,
            details={
                "risk_id": event.id,
                "project_name": event.project_name,
                "category": event.category,
                "action": action,
                "actor_name": actor_name,
                "notes": notes,
                "updated_integrity_score": integrity_score,
            },
            timestamp=now,
        )
        db.add(audit)
        db.commit()

        return event, integrity_score

    @classmethod
    def get_overview(cls, db: Session, project_id: Optional[str] = None, project_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Calculates platform-wide Sentinel metrics: average integrity score, overall grade,
        breakdown of findings by severity, and project details.
        """
        query = db.query(Project)
        if project_id:
            query = query.filter(Project.id == project_id)
        elif project_ids is not None:
            query = query.filter(Project.id.in_(project_ids)) if project_ids else query.filter(Project.id == "__no_access__")
        projects = query.all()

        project_details = []
        total_score = 0.0
        total_active = 0
        crit_total = 0
        high_total = 0
        med_total = 0
        resolved_total = 0

        for prj in projects:
            summary = cls.calculate_integrity_score(db, prj)
            total_score += summary["integrity_score"]
            total_active += summary["active_findings_count"]
            crit_total += summary["critical_count"]
            high_total += summary["high_count"]
            med_total += summary["medium_count"]

            resolved_count = (
                db.query(SentinelEvent)
                .filter(
                    SentinelEvent.project_id == prj.id,
                    SentinelEvent.is_resolved == True,  # noqa: E712
                )
                .count()
            )
            resolved_total += resolved_count

            project_details.append(summary)

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

        # Count verified items (documents completed + verified knowledge nodes)
        docs_query = db.query(Document).filter(Document.processing_status == "completed")
        knowledge_query = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.verification_status.in_(["verified", "modified"]))
        if project_ids is not None:
            docs_query = docs_query.filter(Document.project_id.in_(project_ids)) if project_ids else docs_query.filter(Document.project_id == "__no_access__")
            knowledge_query = knowledge_query.filter(ExtractedKnowledge.project_id.in_(project_ids)) if project_ids else knowledge_query.filter(ExtractedKnowledge.project_id == "__no_access__")
        verified_items = docs_query.count() + knowledge_query.count()

        return {
            "average_integrity_score": avg_score,
            "overall_grade": overall_grade,
            "total_active_findings": total_active,
            "critical_findings": crit_total,
            "high_findings": high_total,
            "medium_findings": med_total,
            "resolved_findings": resolved_total,
            "verified_items_count": verified_items,
            "projects": project_details,
            "formula": (
                "Score = max(0, min(100, (Sections[30] + Documents[30] + "
                "SupportedTasks[25] + EnvSetup[15]) - Penalties))"
            ),
        }
