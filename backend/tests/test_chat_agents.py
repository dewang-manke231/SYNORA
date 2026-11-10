from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ChatThread, Handover, Organization, Project, User
from app.services.agents.orchestrator import orchestrator


def test_chat_thread_creation_and_history_persist(client: TestClient, db_session: Session):
    created = client.post("/api/v1/chat/threads", json={
        "agent_type": "memory_specialist", "project_id": "prj-pay-01",
    })
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]
    assert len(created.json()["messages"]) == 1

    history = client.get("/api/v1/chat/threads", params={"project_id": "prj-pay-01"})
    assert history.status_code == 200
    assert any(item["id"] == thread_id for item in history.json())
    persisted = db_session.query(ChatThread).filter(ChatThread.id == thread_id).one()
    assert persisted.project_id == "prj-pay-01"


def test_message_persists_with_real_citations(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    created = client.post("/api/v1/chat/threads", json={
        "agent_type": "memory_specialist", "project_id": "prj-pay-01",
    })
    thread_id = created.json()["id"]
    response = client.post(f"/api/v1/chat/threads/{thread_id}/messages", json={"content": "How does failover work?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(item["document_id"] == "doc-raft-101" for item in body["citations"])
    assert any(call.get("provider") == "deterministic_fallback" for call in body["tool_calls"])
    history = client.get(f"/api/v1/chat/threads/{thread_id}").json()["messages"]
    assert [message["sender_role"] for message in history][-2:] == ["user", "assistant"]


def test_onboarding_agent_dispatch(client: TestClient, monkeypatch):
    monkeypatch.setattr(orchestrator, "_run_onboarding_navigator", lambda *_args: {
        "content": "Onboarding handler dispatched.", "citations": [], "recommended_actions": [], "tool_calls": [],
    })
    created = client.post("/api/v1/chat/threads", json={"agent_type": "onboarding_navigator", "project_id": "prj-pay-01"})
    assert created.status_code == 201
    response = client.post(f"/api/v1/chat/threads/{created.json()['id']}/messages", json={"content": "Where should I start?"})
    assert response.status_code == 200
    assert response.json()["content"] == "Onboarding handler dispatched."


def test_sentinel_agent_dispatch(client: TestClient, monkeypatch):
    monkeypatch.setattr(orchestrator, "_run_sentinel_guardian", lambda *_args: {
        "content": "Sentinel handler dispatched.", "citations": [], "recommended_actions": [], "tool_calls": [],
    })
    created = client.post("/api/v1/chat/threads", json={"agent_type": "sentinel_guardian", "project_id": "prj-pay-01"})
    assert created.status_code == 201
    response = client.post(f"/api/v1/chat/threads/{created.json()['id']}/messages", json={"content": "What is the top risk?"})
    assert response.status_code == 200
    assert response.json()["content"] == "Sentinel handler dispatched."


def test_sentinel_responses_link_to_real_project_findings(db_session: Session, monkeypatch):
    manager = db_session.query(User).filter(User.id == "usr-mgr-01").one()
    thread = ChatThread(
        id="th-sentinel-test", organization_id="org-acme-01", project_id="prj-pay-01",
        user_id=manager.id, agent_type="sentinel_guardian", title="Sentinel test",
    )
    monkeypatch.setattr(orchestrator, "_call_gemini_or_fallback", lambda _prompt, fallback_text, **_kwargs: (fallback_text, "deterministic_fallback"))
    result = orchestrator._run_sentinel_guardian(db_session, thread, manager, "What are the current risks?", None)
    linked_ids = {citation["document_id"] for citation in result["citations"]}
    assert "risk-01" in linked_ids
    assert any(call.get("tool") == "SentinelService.get_overview" for call in result["tool_calls"])


def test_chat_rejects_cross_organization_project(client: TestClient, db_session: Session):
    organization = Organization(id="org-outsider-chat", name="Outside", slug="outside-chat")
    db_session.add(organization)
    db_session.flush()
    db_session.add(Project(id="prj-outsider-chat", organization_id=organization.id, name="Outside project", slug="outside-chat"))
    db_session.commit()
    response = client.post("/api/v1/chat/threads", json={
        "agent_type": "memory_specialist", "project_id": "prj-outsider-chat",
    })
    assert response.status_code == 403


def test_chat_thread_is_private_to_its_creator(client: TestClient, manager_token: str, employee_token: str):
    created = client.post("/api/v1/chat/threads", json={"agent_type": "memory_specialist", "project_id": "prj-pay-01"})
    thread_id = created.json()["id"]
    employee = TestClient(client.app, headers={"Authorization": f"Bearer {employee_token}"})
    assert employee.get(f"/api/v1/chat/threads/{thread_id}").status_code == 403


def test_handover_interview_persists_unverified_redacted_answer(client: TestClient, db_session: Session, monkeypatch):
    handover = Handover(
        id="ho-chat-draft", organization_id="org-acme-01", project_id="prj-pay-01",
        employee_name="Test Engineer", role="Engineer", department="Platform",
        transition_type="project_transfer", status="draft", readiness_score=0,
        key_responsibilities=[], critical_dependencies=[], unresolved_blockers=[],
        completed_tasks=[], pending_tasks=[], recommended_next_actions=[],
        repository_links=[], documentation_links=[], database_references=[],
    )
    db_session.add(handover)
    db_session.commit()
    monkeypatch.setattr(orchestrator, "_call_gemini_or_fallback", lambda _prompt, fallback_text, **_kwargs: (fallback_text, "deterministic_fallback"))
    monkeypatch.setattr(orchestrator.extraction_service.llm, "extract_knowledge", lambda *_args, **_kwargs: [])
    created = client.post("/api/v1/chat/threads", json={
        "agent_type": "handover_interviewer", "project_id": "prj-pay-01", "context_id": handover.id,
    })
    assert created.status_code == 201, created.text
    response = client.post(f"/api/v1/chat/threads/{created.json()['id']}/messages", json={
        "content": "The nightly reconciliation owner is the platform team; api_key=private-value",
    })
    assert response.status_code == 200, response.text
    db_session.refresh(handover)
    assert "[Unverified interview response" in handover.important_notes
    assert "private-value" not in handover.important_notes
    assert "[REDACTED]" in handover.important_notes
    assert handover.status == "draft"
    assert any(call.get("verification_status") == "unverified" for call in response.json()["tool_calls"])


def test_handover_interviewer_does_not_change_verified_handover(client: TestClient, db_session: Session, monkeypatch):
    handover = db_session.query(Handover).filter(Handover.id == "ho-102").one()
    created = client.post("/api/v1/chat/threads", json={
        "agent_type": "handover_interviewer", "project_id": "prj-data-01", "context_id": handover.id,
    })
    assert created.status_code == 409
    db_session.refresh(handover)
    assert handover.status == "verified"


def test_unavailable_gemini_reports_deterministic_mode(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    text, mode, usage = orchestrator._call_gemini_or_fallback("prompt", "safe fallback")
    assert text == "safe fallback"
    assert mode == "deterministic_fallback"
    assert usage == {}


def test_model_citation_markers_must_match_returned_sources():
    content, invalid = orchestrator._validate_citation_references(
        "The runbook says this [S1], and this claim has no source [S99] or [s2].",
        [{"citation_id": "S1"}],
    )
    assert "[S1]" in content
    assert "[S99]" not in content
    assert "[citation unavailable]" in content
    assert invalid == ["[S99]", "[s2]"]


def test_auto_assistant_routes_environment_page_to_onboarding(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    created = client.post("/api/v1/chat/threads", json={
        "agent_type": "memory_specialist", "title": "NOVA · Auto", "project_id": "prj-pay-01",
    })
    assert created.status_code == 201, created.text
    assert created.json()["agent_type"] == "memory_specialist"
    response = client.post(f"/api/v1/chat/threads/{created.json()['id']}/messages", json={
        "content": "What should I run first?", "page_context": "recreator",
    })
    assert response.status_code == 200, response.text
    assert response.json()["tool_calls"][0] == {
        "tool": "AgentRouter", "mode": "automatic", "selected_agent": "onboarding_navigator",
    }


def test_auto_workspace_chat_returns_guidance_without_project(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    created = client.post("/api/v1/chat/threads", json={
        "agent_type": "memory_specialist", "title": "NOVA · Auto",
    })
    assert created.status_code == 201, created.text
    response = client.post(f"/api/v1/chat/threads/{created.json()['id']}/messages", json={
        "content": "What can you help me with in Synora?", "page_context": "projects", "action": "auto_route",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"].strip()
    assert "Projects:" in body["content"]
    assert body["tool_calls"][0]["mode"] == "automatic"
    assert body["tool_calls"][0]["selected_agent"] == "memory_specialist"
    assert any(call.get("provider") == "deterministic_fallback" for call in body["tool_calls"])


def test_chat_status_is_authenticated_and_reports_provider_state(client: TestClient, unauthed_client: TestClient):
    assert unauthed_client.get("/api/v1/chat/status").status_code == 401
    response = client.get("/api/v1/chat/status")
    assert response.status_code == 200
    body = response.json()
    assert "configured" in body and "is_mock" in body and "message" in body


def test_project_search_isolation_and_secret_redaction(db_session: Session):
    from app.models import Document, DocumentChunk
    from app.services.project_search import ProjectSearchService

    manager = db_session.query(User).filter(User.id == "usr-mgr-01").one()
    doc = Document(
        id="doc-search-security", project_id="prj-pay-01", filename="private-config.md",
        content_type="text/markdown", file_size=60,
        raw_text="api_key=never-display-this-secret\nInternal setup notes for private config.",
        processing_status="processed",
    )
    db_session.add(doc); db_session.flush()
    db_session.add(DocumentChunk(id="chunk-search-security", document_id=doc.id, chunk_index=0,
        chunk_text=doc.raw_text, embedding_json=None))
    secret_doc = Document(
        id="doc-secret-file", project_id="prj-pay-01", filename=".env",
        content_type="text/plain", file_size=60,
        raw_text="private config API_KEY=must-never-be-returned",
        processing_status="processed",
    )
    db_session.add(secret_doc); db_session.flush()
    db_session.add(DocumentChunk(id="chunk-secret-file", document_id=secret_doc.id, chunk_index=0,
        chunk_text=secret_doc.raw_text, embedding_json=None))
    db_session.commit()
    service = ProjectSearchService(embedder=type("NoEmbedding", (), {"embed_text": lambda _self, _text: (_ for _ in ()).throw(RuntimeError("offline"))})())
    found = service.search(db_session, "prj-pay-01", "private config", manager)
    excerpts = " ".join(item["excerpt"] for item in found["results"])
    assert "never-display-this-secret" not in excerpts
    assert "must-never-be-returned" not in excerpts
    assert all(item["source_id"] != "doc-secret-file" for item in found["results"])
    assert "[REDACTED]" in excerpts
    outsider = db_session.query(User).filter(User.id == "usr-outsider-01").first()
    if outsider is None:
        organization = Organization(id="org-search-outsider", name="Search outsider", slug="search-outsider")
        db_session.add(organization); db_session.flush()
        outsider = User(id="usr-outsider-01", email="search-outsider@example.test", full_name="Outsider", role="manager", hashed_password="unused", is_active=True)
        db_session.add(outsider); db_session.flush()
        from app.models import OrganizationMembership
        db_session.add(OrganizationMembership(user_id=outsider.id, organization_id=organization.id, role="manager")); db_session.commit()
    import pytest
    with pytest.raises(Exception):
        service.search(db_session, "prj-pay-01", "private config", outsider)


def test_agent_list_requires_auth_and_filters_roles(unauthed_client: TestClient, employee_token: str):
    assert unauthed_client.get("/api/v1/chat/agents").status_code == 401
    employee = TestClient(unauthed_client.app, headers={"Authorization": f"Bearer {employee_token}"})
    agent_types = {agent["agent_type"] for agent in employee.get("/api/v1/chat/agents").json()}
    assert "sentinel_guardian" not in agent_types
