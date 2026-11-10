from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.embeddings import check_embedding_connectivity
from app.core.llm import check_gemini_connectivity
from app.models import ExtractedKnowledge, User, Document
from app.core.security import require_role, verify_project_organization_access, get_accessible_project_ids, get_current_user
from app.schemas.common import (
    EmbeddingStatusResponse,
    GraphResponse,
    KnowledgeExtractRequest,
    KnowledgeNode,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
    KnowledgeVerificationRequest,
    LLMStatusResponse,
)
from app.services.extraction import ExtractionService
from app.services.graph import GraphService
from app.services.rag import RAGService

router = APIRouter()
extraction_service = ExtractionService()
graph_service = GraphService()
rag_service = RAGService()


@router.get("/llm-status", response_model=LLMStatusResponse)
def get_llm_status():
    """Returns the current LLM provider configuration and Gemini connectivity."""
    info = check_gemini_connectivity()
    return LLMStatusResponse(
        configured=info["configured"],
        provider=info["provider"],
        model=info["model"],
        status=info["status"],
        message=info["message"],
    )


@router.get("/embedding-status", response_model=EmbeddingStatusResponse)
def get_embedding_status():
    """Returns the current embedding provider configuration and vector dimensionality."""
    info = check_embedding_connectivity()
    return EmbeddingStatusResponse(
        configured=info["configured"],
        provider=info["provider"],
        model=info["model"],
        dimension=info["dimension"],
        status=info["status"],
        message=info["message"],
    )


@router.get("/graph", response_model=GraphResponse)
def get_knowledge_graph(
    project_id: Optional[str] = Query(None, description="Optional project ID filter (or 'all')"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Constructs and returns the grounded Organizational Memory Graph (Module 3)
    containing verified knowledge items, documents, attested owners, and directed
    dependencies without fabricated links.
    """
    if project_id and project_id != "all":
        project = verify_project_organization_access(project_id, current_user, db)
        # The explicit project access check is sufficient scope for this graph;
        # don't fetch every project ID first.
        project_ids = [project_id]
    elif project_id == "all" and current_user.role != "admin":
        project_id = None
        project_ids = get_accessible_project_ids(current_user, db)
    else:
        project_ids = get_accessible_project_ids(current_user, db)
    try:
        graph = graph_service.get_project_graph(
            db,
            project_id=project_id,
            project_ids=project_ids,
            project_name=project.name if project_id and project_id != "all" else None,
        )
        return graph
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate knowledge graph: {str(e)}",
        )


@router.post("/query", response_model=KnowledgeQueryResponse)
def query_knowledge_assistant(
    payload: KnowledgeQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI Knowledge Assistant (Module 4): Retrieves project chunks using cosine
    similarity, enforces honest uncertainty when similarity < threshold,
    and returns strictly grounded answers with verifiable source citations.
    """
    verify_project_organization_access(payload.project_id, current_user, db)
    try:
        result = rag_service.query(db, payload)
        return result
    except ValueError as e:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge Assistant query failed: {str(e)}",
        )


@router.post("/extract/{document_id}", response_model=List[KnowledgeNode], status_code=status.HTTP_201_CREATED)
def extract_knowledge_from_document(
    document_id: str,
    payload: Optional[KnowledgeExtractRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Extracts structured knowledge items (tasks, decisions, blockers, dependencies, configs)
    from all chunks of the specified document with source citations and confidence scores.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    verify_project_organization_access(document.project_id, current_user, db)
    try:
        actor = payload.actor_name if payload else None
        nodes = extraction_service.extract_from_document(db, document_id, actor_name=actor)
        return nodes
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge extraction pipeline failed: {str(e)}",
        )


@router.get("/nodes", response_model=List[KnowledgeNode])
def list_knowledge_nodes(
    category: Optional[str] = Query(None, description="Filter by category (task, decision, blocker, etc.)"),
    verification_status: Optional[str] = Query(None, description="Filter by status (unverified, verified, modified, rejected)"),
    document_id: Optional[str] = Query(None, description="Filter by originating document ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[KnowledgeNode]:
    """
    Lists extracted knowledge nodes with optional category, verification status, and document filters.
    """
    query = db.query(ExtractedKnowledge)
    allowed_projects = get_accessible_project_ids(current_user, db)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
    elif allowed_projects is not None:
        query = query.filter(ExtractedKnowledge.project_id.in_(allowed_projects)) if allowed_projects else query.filter(ExtractedKnowledge.project_id == "__no_access__")
    if category:
        query = query.filter(ExtractedKnowledge.category == category)
    if verification_status:
        query = query.filter(ExtractedKnowledge.verification_status == verification_status)
    if document_id:
        query = query.filter(ExtractedKnowledge.document_id == document_id)
    if project_id:
        query = query.filter(ExtractedKnowledge.project_id == project_id)

    nodes = query.order_by(ExtractedKnowledge.created_at.desc()).all()
    return nodes


@router.get("/nodes/{node_id}", response_model=KnowledgeNode)
def get_knowledge_node(node_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieves full details for a single extracted knowledge node."""
    node = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge node '{node_id}' not found.",
        )
    verify_project_organization_access(node.project_id, current_user, db)
    return node


@router.patch("/nodes/{node_id}/verify", response_model=KnowledgeNode)
def verify_knowledge_node(
    node_id: str,
    payload: KnowledgeVerificationRequest,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    """
    Records a human verification decision (verified, modified, rejected) with mandatory reviewer name,
    optional edits and notes, creating an immutable verification record and audit log.
    Enforces manager-only authorization and organization-level scoping.
    """
    node = db.query(ExtractedKnowledge).filter(ExtractedKnowledge.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge node '{node_id}' not found.",
        )
    if node.project_id:
        verify_project_organization_access(node.project_id, current_user, db)

    reviewer = payload.reviewer_name or current_user.full_name
    try:
        updated_node = extraction_service.verify_node(
            db=db,
            node_id=node_id,
            action=payload.action,
            reviewer_name=reviewer,
            notes=payload.notes,
            modified_label=payload.modified_label,
            modified_details=payload.modified_details,
        )
        return updated_node
    except ValueError as e:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}",
        )
