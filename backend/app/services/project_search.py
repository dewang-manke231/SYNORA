"""Project-scoped hybrid retrieval over the records Synora actually stores."""
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased

from app.core.embeddings import cosine_similarity, get_embedding_provider
from app.core.security import verify_handover_organization_access, verify_project_organization_access
from app.models import (
    Document,
    DocumentChunk,
    EnvironmentSnapshot,
    ExtractedKnowledge,
    Handover,
    KnowledgeLossIndicator,
    KnowledgeRelationship,
    Project,
    SentinelEvent,
    User,
)


STOP_WORDS = {
    "about", "above", "after", "again", "also", "and", "are", "because", "been", "before",
    "being", "between", "could", "does", "from", "have", "into", "issue", "missing", "most",
    "project", "should", "that", "their", "there", "these", "this", "those", "what", "when",
    "where", "which", "while", "with", "would", "your", "using", "show", "find", "tell",
}
QUERY_EXPANSIONS = {
    "dependency": {"package", "library", "requirement", "manifest"},
    "dependencies": {"package", "library", "requirement", "manifest"},
    "setup": {"install", "quickstart", "environment", "command"},
    "owner": {"ownership", "responsibility", "maintainer", "assignee"},
    "risk": {"finding", "sentinel", "radar", "blocker"},
    "todo": {"task", "incomplete", "pending", "blocker"},
    "architecture": {"component", "module", "service", "design"},
}


class ProjectSearchService:
    """Hybrid keyword and stored-vector search, plus authorized project records.

    This uses existing DocumentChunk embeddings without re-embedding them. A query
    embedding is generated once per request; chunks with no stored vector remain
    keyword-searchable and are reported as lacking semantic coverage.
    """

    MAX_RESULTS = 30
    MAX_QUERY_TERMS = 16
    MAX_SEARCH_ITERATIONS = 3

    def __init__(self, embedder=None):
        self.embedder = embedder or get_embedding_provider()

    def search(
        self,
        db: Session,
        project_id: str,
        query: str,
        current_user: User,
        top_k: int = 8,
        source_types: Optional[Set[str]] = None,
        conversation_context: Optional[str] = None,
        priority_source_types: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        project = verify_project_organization_access(project_id, current_user, db)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")
        query = (query or "").strip()[:2000]
        if not query:
            raise ValueError("Search query cannot be empty.")
        top_k = max(1, min(int(top_k), self.MAX_RESULTS))
        terms = self._terms(query)
        if conversation_context:
            terms = list(dict.fromkeys(terms + self._terms(conversation_context)))[:self.MAX_QUERY_TERMS]
        base_terms = list(terms)
        expanded_terms = set(terms)
        for term in terms:
            expanded_terms.update(QUERY_EXPANSIONS.get(term, set()))
        terms = sorted(expanded_terms)[:self.MAX_QUERY_TERMS]

        allowed = source_types or {
            "project_file", "knowledge", "knowledge_relationship", "handover",
            "radar_finding", "sentinel_finding", "environment_setup",
        }
        priority_source_types = priority_source_types or set()
        results: Dict[str, Dict[str, Any]] = {}
        supported_sources: Dict[str, bool] = {}
        semantic_missing = 0

        def add(item: Dict[str, Any]) -> None:
            key = f"{item['source_type']}:{item['source_id']}:{item.get('chunk_id') or ''}"
            previous = results.get(key)
            if previous:
                previous["relevance"] = max(previous["relevance"], item["relevance"])
                previous["retrieval_methods"] = sorted(set(previous["retrieval_methods"] + item["retrieval_methods"]))
            else:
                results[key] = item

        def is_allowed(source_type: str) -> bool:
            return source_type in allowed

        chunks_query = (
            db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(Document.project_id == project_id)
        )
        chunks = [
            (chunk, document) for chunk, document in chunks_query.all()
            if not self._is_sensitive_filename(document.filename)
        ]
        supported_sources["project_files_and_docs"] = bool(db.query(Document.id).filter(Document.project_id == project_id).first())
        if is_allowed("project_file") and terms:
            patterns = [f"%{term}%" for term in terms]
            chunk_match = or_(*[DocumentChunk.chunk_text.ilike(pattern) for pattern in patterns])
            file_match = or_(*[Document.filename.ilike(pattern) for pattern in patterns])
            raw_match = or_(*[Document.raw_text.ilike(pattern) for pattern in patterns])
            keyword_chunks = (
                db.query(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .filter(Document.project_id == project_id)
                .filter(or_(chunk_match, file_match))
                .limit(120)
                .all()
            )
            for chunk, doc in keyword_chunks:
                if self._is_sensitive_filename(doc.filename):
                    continue
                text = chunk.chunk_text or ""
                score = self._keyword_score(query, terms, f"{doc.filename}\n{text}")
                status = self._document_status(db, chunk, doc)
                add({
                    "source_type": "project_file", "source_title": doc.filename,
                    "source_id": doc.id, "document_id": doc.id, "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index, "file_path": doc.filename,
                    "excerpt": self._redact(self._snippet(text, terms)),
                    "relevance": score, "verification_status": status,
                    "retrieval_methods": ["keyword"],
                })
            # Files ingested without chunk records are still searchable as stored text.
            chunked_ids = {doc.id for _, doc in chunks}
            raw_docs = db.query(Document).filter(Document.project_id == project_id)
            if chunked_ids:
                raw_docs = raw_docs.filter(~Document.id.in_(chunked_ids))
            for doc in raw_docs.filter(raw_match).limit(30).all():
                if self._is_sensitive_filename(doc.filename):
                    continue
                add({
                    "source_type": "project_file", "source_title": doc.filename,
                    "source_id": doc.id, "document_id": doc.id, "file_path": doc.filename,
                    "excerpt": self._redact(self._snippet(doc.raw_text or "", terms)),
                    "relevance": self._keyword_score(query, terms, f"{doc.filename}\n{doc.raw_text or ''}"),
                    "verification_status": "verified" if doc.processing_status == "processed" else "unverified",
                    "retrieval_methods": ["keyword"],
                })

        if is_allowed("project_file") and chunks:
            missing = [chunk for chunk, _ in chunks if not chunk.embedding_json]
            semantic_missing = len(missing)
            try:
                query_vector = self.embedder.embed_text(query)
                for chunk, doc in chunks:
                    vector = chunk.embedding_json
                    if not vector:
                        continue
                    similarity = cosine_similarity(query_vector, vector)
                    if similarity < 0.42:
                        continue
                    status = self._document_status(db, chunk, doc)
                    add({
                        "source_type": "project_file", "source_title": doc.filename,
                        "source_id": doc.id, "document_id": doc.id, "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index, "file_path": doc.filename,
                        "excerpt": self._redact(self._snippet(chunk.chunk_text or "", terms)),
                        "relevance": min(1.0, max(0.0, similarity)),
                        "verification_status": status,
                        "retrieval_methods": ["semantic"],
                    })
            except Exception:
                supported_sources["semantic_search"] = False
            else:
                supported_sources["semantic_search"] = semantic_missing < len(chunks)
        else:
            supported_sources["semantic_search"] = False

        if is_allowed("knowledge"):
            q = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.project_id == project_id)
            if terms:
                q = q.filter(or_(*[
                    ExtractedKnowledge.label.ilike(f"%{term}%")
                    | ExtractedKnowledge.details.ilike(f"%{term}%")
                    | ExtractedKnowledge.source_quote.ilike(f"%{term}%")
                    for term in terms
                ]))
            knowledge_rows = q.order_by(ExtractedKnowledge.updated_at.desc()).limit(100).all()
            supported_sources["knowledge_graph_entities"] = bool(knowledge_rows)
            for row in knowledge_rows:
                body = f"{row.label}. {row.details}\nEvidence: {row.source_quote or ''}"
                add({
                    "source_type": "knowledge", "source_title": row.label,
                    "source_id": row.id, "document_id": row.document_id,
                    "chunk_id": row.chunk_id, "file_path": None,
                    "excerpt": self._redact(self._snippet(body, terms)),
                    "relevance": self._keyword_score(query, terms, body) * max(0.3, float(row.confidence_score or 0.0)),
                    "verification_status": row.verification_status,
                    "category": row.category, "owner": row.owner,
                    "retrieval_methods": ["keyword"],
                })

        if is_allowed("knowledge_relationship"):
            source_node = aliased(ExtractedKnowledge)
            target_node = aliased(ExtractedKnowledge)
            relationship_query = db.query(KnowledgeRelationship, source_node, target_node).join(
                source_node, KnowledgeRelationship.source_id == source_node.id
            ).join(target_node, KnowledgeRelationship.target_id == target_node.id).filter(
                source_node.project_id == project_id,
                target_node.project_id == project_id,
            )
            supported_sources["knowledge_graph_relationships"] = relationship_query.first() is not None
            if terms:
                rel_patterns = [f"%{term}%" for term in terms]
                relationship_query = relationship_query.filter(or_(
                    *[KnowledgeRelationship.relation_type.ilike(pattern) for pattern in rel_patterns],
                    *[source_node.label.ilike(pattern) for pattern in rel_patterns],
                    *[target_node.label.ilike(pattern) for pattern in rel_patterns],
                ))
                for relation, source, target in relationship_query.limit(100).all():
                    body = f"{source.label} {relation.relation_type} {target.label}"
                    verification = "verified" if source.verification_status in ("verified", "modified") and target.verification_status in ("verified", "modified") else "unverified"
                    add({"source_type": "knowledge_relationship", "source_title": body,
                         "source_id": relation.id, "document_id": source.document_id,
                         "file_path": None, "excerpt": self._redact(body),
                         "relevance": self._keyword_score(query, terms, body) * float(relation.confidence or 0),
                         "verification_status": verification, "retrieval_methods": ["keyword"]})

        if is_allowed("radar_finding"):
            radar_rows = db.query(KnowledgeLossIndicator).filter(
                KnowledgeLossIndicator.project_id == project_id,
                KnowledgeLossIndicator.is_resolved.is_(False),
            ).order_by(KnowledgeLossIndicator.detected_at.desc()).limit(100).all()
            supported_sources["radar_findings"] = bool(radar_rows)
            for row in radar_rows:
                body = f"{row.gap_type} ({row.severity}): {row.description}. Remediation: {row.recommended_remediation or ''}"
                score = self._keyword_score(query, terms, body)
                if score or "radar_finding" in priority_source_types:
                    severity_score = {"critical": 0.62, "high": 0.54, "medium": 0.44, "low": 0.34}.get((row.severity or "").lower(), 0.3)
                    add({"source_type": "radar_finding", "source_title": f"{row.gap_type} · {row.severity}",
                         "source_id": row.id, "excerpt": self._redact(body), "relevance": max(score, severity_score if "radar_finding" in priority_source_types else 0),
                         "verification_status": "observed_finding", "retrieval_methods": ["keyword"]})

        if is_allowed("sentinel_finding"):
            sentinel_rows = db.query(SentinelEvent).filter(
                SentinelEvent.project_id == project_id,
                SentinelEvent.is_resolved.is_(False),
            ).order_by(SentinelEvent.detected_at.desc()).limit(100).all()
            supported_sources["sentinel_findings"] = bool(sentinel_rows)
            for row in sentinel_rows:
                body = f"{row.category} ({row.risk_level}): {row.description}. Action: {row.recommended_action}"
                score = self._keyword_score(query, terms, body)
                if score or "sentinel_finding" in priority_source_types:
                    severity_score = {"critical": 0.66, "high": 0.56, "medium": 0.46, "low": 0.36}.get((row.risk_level or "").lower(), 0.3)
                    add({"source_type": "sentinel_finding", "source_title": f"{row.category} · {row.risk_level}",
                         "source_id": row.id, "excerpt": self._redact(body), "relevance": max(score, severity_score if "sentinel_finding" in priority_source_types else 0),
                         "verification_status": "observed_finding", "severity": row.risk_level,
                         "retrieval_methods": ["keyword"]})

        if is_allowed("handover"):
            handovers = db.query(Handover).filter(Handover.project_id == project_id).order_by(Handover.updated_at.desc()).limit(100).all()
            visible_handovers = []
            for handover in handovers:
                try:
                    verify_handover_organization_access(handover.id, current_user, db)
                    visible_handovers.append(handover)
                except Exception:
                    continue
            supported_sources["authorized_handovers"] = bool(visible_handovers)
            for row in visible_handovers:
                body = self._handover_text(row)
                score = self._keyword_score(query, terms, body)
                if score or "handover" in priority_source_types:
                    verified = row.status in ("verified", "completed")
                    add({"source_type": "handover", "source_title": f"Handover · {row.employee_name}",
                         "source_id": row.id, "excerpt": self._redact(self._snippet(body, terms)),
                         "relevance": max(score, 0.3 if "handover" in priority_source_types else 0), "verification_status": row.status if verified else "unverified_draft",
                         "status": row.status, "retrieval_methods": ["keyword"]})

        if is_allowed("environment_setup"):
            snapshots = db.query(EnvironmentSnapshot).filter(EnvironmentSnapshot.project_id == project_id).order_by(EnvironmentSnapshot.created_at.desc()).limit(20).all()
            supported_sources["environment_setup"] = bool(snapshots)
            for row in snapshots:
                spec = row.blueprint_spec or {}
                body = "\n".join(filter(None, [row.environment_name, row.stack_type, row.powershell_quickstart, row.bash_quickstart, str(spec)]))
                score = self._keyword_score(query, terms, body)
                if score:
                    add({"source_type": "environment_setup", "source_title": f"{row.environment_name} setup snapshot",
                         "source_id": row.id, "excerpt": self._redact(self._snippet(body, terms)),
                         "relevance": score, "verification_status": "unverified_not_locally_validated",
                         "retrieval_methods": ["keyword"]})

        ranked = sorted(results.values(), key=lambda item: item["relevance"], reverse=True)[:top_k]
        for index, item in enumerate(ranked, start=1):
            item["citation_id"] = f"S{index}"
            item["relevance"] = round(float(item["relevance"]), 3)
        unavailable = [name for name, available in supported_sources.items() if not available]
        unsupported = [
            "Live GitHub/Jira/Confluence/Slack APIs are not searched; only project documents and records already stored in Synora are searchable.",
            "Audit logs and organization-wide data are excluded from project search.",
        ]
        return {
            "project_id": project_id,
            "project_name": project.name,
            "query": query,
            "results": ranked,
            "searched_sources": sorted(supported_sources.keys()),
            "sources_without_searchable_records": unavailable,
            "unsupported_sources": unsupported,
            "semantic_chunks_missing_embeddings": semantic_missing,
            "iterations": 1,
            "query_terms": base_terms,
            "expanded_terms": terms,
        }

    @staticmethod
    def _terms(query: str) -> List[str]:
        return [term.lower() for term in re.findall(r"[\w./-]{3,}", query) if term.lower() not in STOP_WORDS][:ProjectSearchService.MAX_QUERY_TERMS]

    @staticmethod
    def _keyword_score(query: str, terms: Iterable[str], text: str) -> float:
        low = (text or "").lower()
        terms = list(terms)
        if not low:
            return 0.0
        matched = sum(1 for term in terms if term in low)
        coverage = matched / max(1, len(terms))
        phrase_bonus = 0.2 if len(query.strip()) > 4 and query.strip().lower() in low else 0.0
        return min(1.0, coverage * 0.8 + phrase_bonus)

    @staticmethod
    def _snippet(text: str, terms: Iterable[str], limit: int = 600) -> str:
        value = (text or "").strip()
        if len(value) <= limit:
            return value
        lower = value.lower()
        positions = [lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0]
        start = max(0, min(positions) - limit // 4) if positions else 0
        excerpt = value[start:start + limit]
        return ("…" if start else "") + excerpt + ("…" if start + limit < len(value) else "")

    @staticmethod
    def _document_status(db: Session, chunk: DocumentChunk, document: Document) -> str:
        extracted = db.query(ExtractedKnowledge.verification_status).filter(ExtractedKnowledge.chunk_id == chunk.id).all()
        if extracted:
            return "verified" if any(item[0] in ("verified", "modified") for item in extracted) else "unverified"
        return "verified" if document.processing_status == "processed" else "unverified"

    @staticmethod
    def _handover_text(row: Handover) -> str:
        parts = [row.employee_name, row.role, row.department, row.status, row.project_description, row.important_notes]
        for field in ("key_responsibilities", "critical_dependencies", "unresolved_blockers", "completed_tasks", "pending_tasks", "recommended_next_actions"):
            parts.extend(str(item) for item in (getattr(row, field) or []))
        return "\n".join(str(part) for part in parts if part)

    @staticmethod
    def _redact(text: str) -> str:
        text = re.sub(r"(?i)([\"']?[A-Z0-9_.-]*(?:API[_-]?KEY|ACCESS[_-]?KEY(?:[_-]?ID)?|SECRET|PASSWORD|TOKEN|DATABASE[_-]?URL|PRIVATE[_-]?KEY|AUTHORIZATION)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"']+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", text)
        text = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[PRIVATE KEY REDACTED]", text, flags=re.DOTALL)
        return text[:2000]

    @staticmethod
    def _is_sensitive_filename(filename: Optional[str]) -> bool:
        name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
        return bool(
            re.fullmatch(r"\.?env(?:\.[^/]+)?", name)
            or name in {".npmrc", ".pypirc", ".netrc", "authorized_keys"}
            or re.search(r"(?:^|[._-])(?:credentials?|secrets?|tokens?)(?:[._-]|$)", name)
            or re.search(r"(?:^|[._-])id_(?:rsa|ed25519|ecdsa)(?:[._-]|$)", name)
            or name.endswith((".pem", ".key", ".p12", ".pfx", ".keystore"))
        )


project_search_service = ProjectSearchService()
