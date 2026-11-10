import logging
import re
from typing import Dict, List, Optional, Set
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentChunk,
    ExtractedKnowledge,
    KnowledgeRelationship,
    Project,
)
from app.schemas.common import GraphEdge, GraphNode, GraphResponse

logger = logging.getLogger("synora.graph")


class GraphService:
    """
    Constructs and queries the grounded Organizational Memory Graph (Module 3)
    from persisted ExtractedKnowledge, Document, and KnowledgeRelationship records.
    Strictly avoids inventing ungrounded links or phantom entities.
    """

    def get_project_graph(
        self,
        db: Session,
        project_id: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        project_name: Optional[str] = None,
    ) -> GraphResponse:
        """
        Retrieves graph nodes and directed relationships for a given project (or all projects).
        """
        resolved_project_name = project_name or "All Projects"
        if project_id and project_id != "all" and project_name is None:
            prj = db.query(Project).filter(Project.id == project_id).first()
            if not prj:
                raise ValueError(f"Project '{project_id}' not found.")
            resolved_project_name = prj.name

        # 1. Fetch ExtractedKnowledge records
        kn_query = db.query(ExtractedKnowledge)
        if project_id and project_id != "all":
            kn_query = kn_query.filter(ExtractedKnowledge.project_id == project_id)
        elif project_ids is not None:
            kn_query = kn_query.filter(ExtractedKnowledge.project_id.in_(project_ids)) if project_ids else kn_query.filter(ExtractedKnowledge.project_id == "__no_access__")
        knowledge_items = kn_query.all()

        # 2. Fetch Document records
        doc_query = db.query(Document, func.count(DocumentChunk.id)).outerjoin(
            DocumentChunk, DocumentChunk.document_id == Document.id
        )
        if project_id and project_id != "all":
            doc_query = doc_query.filter(Document.project_id == project_id)
        elif project_ids is not None:
            doc_query = doc_query.filter(Document.project_id.in_(project_ids)) if project_ids else doc_query.filter(Document.project_id == "__no_access__")
        document_rows = doc_query.group_by(Document.id).all()
        documents = [row[0] for row in document_rows]
        chunk_counts = {row[0].id: row[1] for row in document_rows}

        nodes: List[GraphNode] = []
        node_ids: Set[str] = set()

        # Track owners with source-attested knowledge
        owner_to_id: Dict[str, str] = {}
        
        # Add ExtractedKnowledge Nodes
        for kn in knowledge_items:
            # Map category to node_type
            cat = (kn.category or "instruction").lower()
            if cat in ("decision", "architecture"):
                node_type = "decision"
            elif cat in ("task",):
                node_type = "task"
            elif cat in ("blocker",):
                node_type = "blocker"
            elif cat in ("dependency",):
                node_type = "dependency"
            elif cat in ("module",):
                node_type = "module"
            elif cat in ("config", "tooling"):
                node_type = "config"
            else:
                node_type = "instruction"

            node = GraphNode(
                id=kn.id,
                label=kn.label,
                node_type=node_type,
                category=kn.category,
                details=kn.details,
                owner=kn.owner,
                confidence_score=kn.confidence_score,
                verification_status=kn.verification_status,
                document_id=kn.document_id,
                chunk_id=kn.chunk_id,
                source_quote=kn.source_quote,
                project_id=kn.project_id,
                metadata_tags=kn.metadata_tags,
            )
            nodes.append(node)
            node_ids.add(kn.id)

            # Register source-supported owner entity
            if kn.owner and kn.owner.strip():
                clean_owner = kn.owner.strip()
                if clean_owner not in owner_to_id:
                    owner_slug = re.sub(r"[^\w-]", "-", clean_owner.lower()).strip("-")
                    owner_id = f"owner-{owner_slug}"
                    owner_to_id[clean_owner] = owner_id

        # Fetch chunk counts in one grouped query instead of lazy-loading the
        # chunks relationship once per document (N+1 round trips).
        # Add Document Nodes
        for doc in documents:
            chunk_cnt = chunk_counts.get(
                doc.id,
                doc.metadata_tags.get("chunk_count", 0) if doc.metadata_tags else 0,
            )
            doc_node = GraphNode(
                id=doc.id,
                label=doc.filename,
                node_type="document",
                category="document",
                details=f"{doc.content_type.upper()} ({doc.file_size} bytes, {chunk_cnt} chunks)",
                owner=None,
                confidence_score=1.0,
                verification_status="verified" if doc.processing_status == "processed" else "unverified",
                document_id=doc.id,
                chunk_id=None,
                source_quote=None,
                project_id=doc.project_id,
                metadata_tags=doc.metadata_tags,
            )
            nodes.append(doc_node)
            node_ids.add(doc.id)

        # Add Source-Supported Owner Nodes
        for owner_name, owner_id in owner_to_id.items():
            if owner_id not in node_ids:
                owner_node = GraphNode(
                    id=owner_id,
                    label=owner_name,
                    node_type="owner",
                    category="personnel",
                    details=f"Institutional contributor & maintainer",
                    owner=owner_name,
                    confidence_score=1.0,
                    verification_status="verified",
                    document_id=None,
                    chunk_id=None,
                    source_quote=None,
                    project_id=project_id if (project_id and project_id != "all") else None,
                    metadata_tags={"is_source_supported": True},
                )
                nodes.append(owner_node)
                node_ids.add(owner_id)

        # 3. Build Grounded Edges
        edges: List[GraphEdge] = []
        edge_keys: Set[str] = set()

        def add_edge(edge_id: str, src: str, tgt: str, rel: str, conf: float = 1.0, meta: Optional[Dict] = None):
            if src in node_ids and tgt in node_ids and src != tgt:
                key = f"{src}->{tgt}:{rel}"
                if key not in edge_keys:
                    edges.append(
                        GraphEdge(
                            id=edge_id,
                            source=src,
                            target=tgt,
                            relation_type=rel,
                            confidence=conf,
                            metadata_tags=meta,
                        )
                    )
                    edge_keys.add(key)

        # A. Query explicit KnowledgeRelationship records in the database
        db_relationships = []
        if node_ids:
            db_relationships = (
                db.query(KnowledgeRelationship)
                .filter(
                    KnowledgeRelationship.source_id.in_(node_ids),
                    KnowledgeRelationship.target_id.in_(node_ids),
                )
                .all()
            )
        for rel in db_relationships:
            add_edge(
                edge_id=rel.id,
                src=rel.source_id,
                tgt=rel.target_id,
                rel=rel.relation_type,
                conf=rel.confidence,
                meta=rel.metadata_tags,
            )

        # B. Connect ExtractedKnowledge to its source Document via DOCUMENTED_IN
        for kn in knowledge_items:
            if kn.document_id and kn.document_id in node_ids:
                add_edge(
                    edge_id=f"docin-{kn.id}-{kn.document_id}",
                    src=kn.id,
                    tgt=kn.document_id,
                    rel="DOCUMENTED_IN",
                    conf=kn.confidence_score,
                    meta={"source_chunk_id": kn.chunk_id},
                )

        # C. Connect Owner to ExtractedKnowledge via MAINTAINS
        for kn in knowledge_items:
            if kn.owner and kn.owner.strip() in owner_to_id:
                owner_id = owner_to_id[kn.owner.strip()]
                add_edge(
                    edge_id=f"maint-{owner_id}-{kn.id}",
                    src=owner_id,
                    tgt=kn.id,
                    rel="MAINTAINS",
                    conf=1.0,
                    meta={"owner_attribution": kn.owner},
                )

        # D. Category-specific grounded relations (DEPENDS_ON, BLOCKED_BY, IMPLEMENTS)
        # Scan if extracted blockers or tasks reference existing nodes by label keywords
        for kn in knowledge_items:
            if kn.category == "blocker":
                # Look for tasks or decisions in same project blocked by this blocker
                for other in knowledge_items:
                    if other.id != kn.id and other.category in ("task", "architecture", "decision"):
                        # Check if blocker details mention other node's label
                        if other.label.lower() in kn.details.lower() or other.label.lower() in (kn.source_quote or "").lower():
                            add_edge(
                                edge_id=f"blk-{kn.id}-{other.id}",
                                src=other.id,
                                tgt=kn.id,
                                rel="BLOCKED_BY",
                                conf=kn.confidence_score,
                                meta={"inferred_from_evidence": True},
                            )
            elif kn.category == "dependency":
                for other in knowledge_items:
                    if other.id != kn.id and other.category in ("module", "architecture", "task"):
                        if other.label.lower() in kn.details.lower():
                            add_edge(
                                edge_id=f"dep-{kn.id}-{other.id}",
                                src=kn.id,
                                tgt=other.id,
                                rel="DEPENDS_ON",
                                conf=kn.confidence_score,
                                meta={"inferred_from_evidence": True},
                            )

        # Calculate statistics
        verified_count = sum(1 for n in nodes if n.verification_status in ("verified", "modified"))
        unverified_count = sum(1 for n in nodes if n.verification_status == "unverified")

        return GraphResponse(
            project_id=project_id if project_id != "all" else None,
            project_name=resolved_project_name,
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
            verified_nodes=verified_count,
            unverified_nodes=unverified_count,
        )
