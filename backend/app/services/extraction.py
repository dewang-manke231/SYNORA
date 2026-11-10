from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.llm import get_llm_provider
from app.models import (
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    VerificationRecord,
    AuditLog,
    User,
    utc_now,
)


class ExtractionService:
    def __init__(self):
        self.llm = get_llm_provider()

    def extract_from_document(
        self,
        db: Session,
        document_id: str,
        actor_name: Optional[str] = None,
    ) -> List[ExtractedKnowledge]:
        """
        Reads all chunks for a document, applies the LLM extraction provider,
        enforces source citations, confidence scoring (<0.65 flagged for review),
        and idempotently persists ExtractedKnowledge records.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        if not chunks:
            raise ValueError(f"Document '{document_id}' has no chunk records to extract from.")

        # Duplicate Prevention: Clear previous extractions for this document so re-running is idempotent
        db.query(ExtractedKnowledge).filter(ExtractedKnowledge.document_id == document_id).delete()
        db.flush()

        extracted_nodes: List[ExtractedKnowledge] = []

        for chunk in chunks:
            items = self.llm.extract_knowledge(
                chunk_text=chunk.chunk_text,
                source_metadata={
                    "source_filename": doc.filename,
                    "document_id": doc.id,
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                },
            )

            for item in items:
                conf = float(item.get("confidence_score", 0.8))
                is_low_conf = conf < 0.65
                is_flagged = is_low_conf or bool(item.get("is_flagged_for_review", False))

                node = ExtractedKnowledge(
                    project_id=doc.project_id,
                    document_id=doc.id,
                    chunk_id=chunk.id,
                    label=item.get("label", "Extracted Item")[:255],
                    category=item.get("category", "instruction"),
                    details=item.get("details", ""),
                    owner=item.get("owner"),
                    confidence_score=conf,
                    verification_status="unverified",
                    source_quote=item.get("source_quote") or chunk.chunk_text[:120],
                    metadata_tags={
                        "source_filename": doc.filename,
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "work_status": item.get("work_status"),
                        "is_flagged_for_review": is_flagged,
                        "review_reason": "Low confidence score (< 0.65)" if is_low_conf else None,
                        "extracted_at": utc_now().isoformat(),
                        "llm_provider": self.llm.get_provider_info()["provider"],
                    },
                )
                db.add(node)
                extracted_nodes.append(node)

        # Audit Log
        user_fk = None
        if actor_name:
            user_rec = db.query(User).filter(
                (User.id == actor_name) | (User.full_name == actor_name)
            ).first()
            if user_rec:
                user_fk = user_rec.id

        audit = AuditLog(
            user_id=user_fk,
            action="knowledge.extracted",
            entity_type="document",
            entity_id=doc.id,
            details={
                "actor_name": actor_name,
                "document_id": doc.id,
                "filename": doc.filename,
                "extracted_count": len(extracted_nodes),
                "chunks_processed": len(chunks),
            },
        )
        db.add(audit)
        db.commit()

        # Refresh all items
        for n in extracted_nodes:
            db.refresh(n)

        return extracted_nodes

    def verify_node(
        self,
        db: Session,
        node_id: str,
        action: str,  # verified, modified, rejected
        reviewer_name: str,
        notes: Optional[str] = None,
        modified_label: Optional[str] = None,
        modified_details: Optional[str] = None,
    ) -> ExtractedKnowledge:
        """
        Records human verification decision, updates node status,
        creates immutable VerificationRecord and AuditLog entries.
        """
        valid_actions = {"verified", "modified", "rejected"}
        if action not in valid_actions:
            raise ValueError(f"Invalid verification action '{action}'. Must be one of {valid_actions}.")

        node = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.id == node_id).first()
        if not node:
            raise ValueError(f"Knowledge node '{node_id}' not found.")

        # Update node state
        node.verification_status = action
        if action == "modified":
            if modified_label:
                node.label = modified_label
            if modified_details:
                node.details = modified_details

        # Clear review flag if explicitly verified or modified by human
        if node.metadata_tags:
            new_tags = dict(node.metadata_tags)
            new_tags["is_flagged_for_review"] = False
            new_tags["human_verified_by"] = reviewer_name
            node.metadata_tags = new_tags

        # Create VerificationRecord
        user_fk = None
        user_rec = db.query(User).filter(
            (User.id == reviewer_name) | (User.full_name == reviewer_name)
        ).first()
        if user_rec:
            user_fk = user_rec.id

        ver_rec = VerificationRecord(
            knowledge_id=node.id,
            verified_by_id=user_fk,
            reviewer_name=reviewer_name,
            action=action,
            notes=notes,
            verified_at=utc_now(),
        )
        db.add(ver_rec)

        # Audit Log
        audit = AuditLog(
            user_id=user_fk,
            action=f"knowledge.{action}",
            entity_type="extracted_knowledge",
            entity_id=node.id,
            details={
                "reviewer_name": reviewer_name,
                "decision": action,
                "notes": notes,
                "node_label": node.label,
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(node)
        return node
