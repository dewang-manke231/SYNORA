from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, ChatThread, ChatMessage
from app.schemas.common import (
    ChatThreadCreate,
    ChatThreadResponse,
    ChatMessageCreate,
    ChatMessageResponse,
)
from app.services.agents.orchestrator import orchestrator, AGENT_ROLES
from app.core.security import verify_project_organization_access
from app.core.llm import get_llm_provider

router = APIRouter()


@router.get("/status")
def get_chat_service_status(current_user: User = Depends(get_current_user)):
    """Return provider configuration only; actual availability is reported per response."""
    provider = get_llm_provider().get_provider_info()
    return {
        "provider": provider.get("provider"),
        "model": provider.get("model"),
        "configured": provider.get("provider") == "gemini" and provider.get("status") == "configured",
        "is_mock": bool(provider.get("is_mock")),
        "status": provider.get("status"),
        "message": "Configuration is known; Gemini success is verified per generated response.",
    }


@router.get("/agents")
def list_available_agents(current_user: User = Depends(get_current_user)):
    """Returns metadata about the 4 specialized AI agents."""
    return [
        {
            "agent_type": k,
            "name": v["name"],
            "description": v["description"],
            "allowed_roles": v["allowed_roles"],
        }
        for k, v in AGENT_ROLES.items()
        if current_user.role in v["allowed_roles"]
    ]


@router.post("/threads", response_model=ChatThreadResponse, status_code=status.HTTP_201_CREATED)
def create_chat_thread(
    payload: ChatThreadCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatThreadResponse:
    """
    Initializes a new specialized agent chat thread.
    Enforces role authorization and multi-tenant organization scoping.
    """
    thread = orchestrator.create_thread(
        db=db,
        current_user=current_user,
        agent_type=payload.agent_type,
        title=payload.title,
        project_id=payload.project_id,
        context_id=payload.context_id,
    )
    return thread


@router.get("/threads", response_model=List[ChatThreadResponse])
def list_chat_threads(
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ChatThreadResponse]:
    """
    Lists chat threads for the authenticated user within their organization.
    """
    user_org_ids = {m.organization_id for m in current_user.memberships}
    query = db.query(ChatThread).filter(ChatThread.user_id == current_user.id)
    if current_user.role != "admin":
        if not user_org_ids:
            return []
        query = query.filter(ChatThread.organization_id.in_(user_org_ids))

    if agent_type:
        query = query.filter(ChatThread.agent_type == agent_type)
    if project_id:
        verify_project_organization_access(project_id, current_user, db)
        query = query.filter(ChatThread.project_id == project_id)
    else:
        query = query.filter(ChatThread.project_id.is_(None))

    threads = query.order_by(ChatThread.updated_at.desc()).all()
    return threads


@router.get("/threads/{thread_id}", response_model=ChatThreadResponse)
def get_chat_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatThreadResponse:
    """
    Retrieves full chat thread history and verified citations.
    Enforces organization-level access authorization.
    """
    thread = orchestrator.get_thread_or_403(db, thread_id, current_user)
    return thread


@router.post("/threads/{thread_id}/messages", response_model=ChatMessageResponse)
def send_chat_message(
    thread_id: str,
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """
    Sends a message to the specialized agent, triggers tool execution,
    and returns an AI-generated assistant response with source citations.
    """
    thread = orchestrator.get_thread_or_403(db, thread_id, current_user)
    assistant_msg = orchestrator.process_message(
        db=db,
        thread=thread,
        current_user=current_user,
        user_content=payload.content,
        trigger_action=payload.action,
        current_page=payload.page_context,
    )
    return assistant_msg


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deletes a chat thread and all associated messages.
    """
    thread = orchestrator.get_thread_or_403(db, thread_id, current_user)
    if thread.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete threads created by another user.")

    db.delete(thread)
    db.commit()
    return None
