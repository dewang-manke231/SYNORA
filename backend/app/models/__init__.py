"""
Base SQLAlchemy Models for Synora

All 15 entity tables specified in PRD & Architecture:
1. User
2. Organization
3. OrganizationMembership
4. Project
5. KnowledgeSource
6. Document
7. DocumentChunk
8. ExtractedKnowledge
9. KnowledgeRelationship
10. VerificationRecord
11. Handover (Enhanced for Complete Lifecycle & Manager Reviews)
12. KnowledgeLossIndicator
13. SentinelEvent
14. EnvironmentSnapshot
15. AuditLog
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base, engine

IS_POSTGRES = engine.dialect.name == "postgresql"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid(prefix: str = "") -> str:
    short_id = uuid.uuid4().hex[:8]
    return f"{prefix}{short_id}" if prefix else str(uuid.uuid4())


# ==========================================
# 1. Organization & User Management
# ==========================================

class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("usr-"))
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="employee")  # admin, manager, employee
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    memberships = relationship("OrganizationMembership", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="uploader")
    verifications = relationship("VerificationRecord", back_populates="verifier")
    audit_logs = relationship("AuditLog", back_populates="user")
    assigned_handovers = relationship("Handover", foreign_keys="[Handover.assigned_to]", back_populates="assignee")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("org-"))
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    memberships = relationship("OrganizationMembership", back_populates="organization", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="organization", cascade="all, delete-orphan")
    handovers = relationship("Handover", back_populates="organization", cascade="all, delete-orphan")


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("mem-"))
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False, default="member")  # owner, admin, manager, member
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
    )


# ==========================================
# 2. Projects & Knowledge Ingestion
# ==========================================

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("prj-"))
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    repository_url = Column(String(512), nullable=True)
    bus_factor = Column(Float, default=1.0, nullable=False)
    knowledge_coverage_score = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organization = relationship("Organization", back_populates="projects")
    knowledge_sources = relationship("KnowledgeSource", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    extracted_knowledge = relationship("ExtractedKnowledge", back_populates="project", cascade="all, delete-orphan")
    handovers = relationship("Handover", back_populates="project", cascade="all, delete-orphan")
    loss_indicators = relationship("KnowledgeLossIndicator", back_populates="project", cascade="all, delete-orphan")
    sentinel_events = relationship("SentinelEvent", back_populates="project", cascade="all, delete-orphan")
    environment_snapshots = relationship("EnvironmentSnapshot", back_populates="project", cascade="all, delete-orphan")


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("src-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # github, local_file, jira, confluence, notion, slack
    configuration = Column(JSON, nullable=True)
    sync_status = Column(String(50), default="idle", nullable=False)  # idle, syncing, failed, completed
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    project = relationship("Project", back_populates="knowledge_sources")
    documents = relationship("Document", back_populates="source", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("doc-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    handover_id = Column(String(64), ForeignKey("handovers.id", ondelete="SET NULL"), nullable=True, index=True)
    source_id = Column(String(64), ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_by_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    file_hash = Column(String(64), nullable=True, index=True)
    storage_path = Column(String(512), nullable=True)
    processing_status = Column(String(50), default="uploaded", nullable=False, index=True)  # uploaded, processing, processed, failed
    error_message = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=False)
    metadata_tags = Column(JSON, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    project = relationship("Project", back_populates="documents")
    handover = relationship("Handover", back_populates="documents")
    source = relationship("KnowledgeSource", back_populates="documents")
    uploader = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    extracted_knowledge = relationship("ExtractedKnowledge", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("chk-"))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True, default=0)
    page_number = Column(Integer, nullable=True)
    metadata_tags = Column(JSON, nullable=True)
    embedding_json = Column(JSON, nullable=True)
    embedding_vector = Column(Vector(), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="chunks")
    extracted_knowledge = relationship("ExtractedKnowledge", back_populates="chunk", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_doc_chunk_index", "document_id", "chunk_index"),
    )


# ==========================================
# 3. Knowledge Extraction, Graph & Verification
# ==========================================

class ExtractedKnowledge(Base):
    __tablename__ = "extracted_knowledge"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("kn-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_id = Column(String(64), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    label = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)  # task, decision, dependency, blocker, config, instruction, architecture
    details = Column(Text, nullable=False)
    owner = Column(String(255), nullable=True)
    confidence_score = Column(Float, default=1.0, nullable=False)
    verification_status = Column(String(50), default="unverified", nullable=False, index=True)  # unverified, verified, modified, rejected
    source_quote = Column(Text, nullable=True)
    metadata_tags = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("Project", back_populates="extracted_knowledge")
    document = relationship("Document", back_populates="extracted_knowledge")
    chunk = relationship("DocumentChunk", back_populates="extracted_knowledge")
    verifications = relationship("VerificationRecord", back_populates="knowledge_item", cascade="all, delete-orphan")
    outgoing_relationships = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.source_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_relationships = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.target_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("rel-"))
    source_id = Column(String(64), ForeignKey("extracted_knowledge.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id = Column(String(64), ForeignKey("extracted_knowledge.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, index=True)  # OWNS, MAINTAINS, DEPENDS_ON, INTERACTS_WITH, DECIDED_BY
    confidence = Column(Float, default=1.0, nullable=False)
    metadata_tags = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    source_node = relationship("ExtractedKnowledge", foreign_keys=[source_id], back_populates="outgoing_relationships")
    target_node = relationship("ExtractedKnowledge", foreign_keys=[target_id], back_populates="incoming_relationships")

    __table_args__ = (
        Index("idx_source_target_rel", "source_id", "target_id", "relation_type"),
    )


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("ver-"))
    knowledge_id = Column(String(64), ForeignKey("extracted_knowledge.id", ondelete="CASCADE"), nullable=False, index=True)
    verified_by_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewer_name = Column(String(255), nullable=True)
    action = Column(String(50), nullable=False)  # verified, modified, rejected
    notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    knowledge_item = relationship("ExtractedKnowledge", back_populates="verifications")
    verifier = relationship("User", back_populates="verifications")


# ==========================================
# 4. Handover & Role Continuity (Enhanced)
# ==========================================

class Handover(Base):
    __tablename__ = "handovers"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("ho-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    employee_name = Column(String(255), nullable=False, index=True)
    role = Column(String(255), nullable=False)
    department = Column(String(255), nullable=False, index=True)
    transition_type = Column(String(50), nullable=False)  # resignation, retirement, internal_transition, project_transfer
    
    # Lifecycle Status: draft, submitted, under_review, changes_requested, verified, completed
    status = Column(String(50), default="draft", nullable=False, index=True)
    readiness_score = Column(Float, default=0.0, nullable=False)
    
    # Project Context
    project_name = Column(String(255), nullable=True)
    project_description = Column(Text, nullable=True)
    
    # Responsibilities & Dependencies
    key_responsibilities = Column(JSON, nullable=False, default=list)
    critical_dependencies = Column(JSON, nullable=False, default=list)
    unresolved_blockers = Column(JSON, nullable=False, default=list)
    
    # Tasks & Evidence
    completed_tasks = Column(JSON, nullable=False, default=list)
    pending_tasks = Column(JSON, nullable=False, default=list)
    
    # Notes & Next Actions
    important_notes = Column(Text, nullable=True)
    recommended_next_actions = Column(JSON, nullable=False, default=list)
    
    # Technical References & Documentation Links
    repository_links = Column(JSON, nullable=False, default=list)
    documentation_links = Column(JSON, nullable=False, default=list)
    database_references = Column(JSON, nullable=False, default=list)
    
    # Manager Review & Approval Tracking
    reviewed_by = Column(String(255), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_decision = Column(String(50), nullable=True)  # approved, changes_requested
    review_notes = Column(Text, nullable=True)  # reason for change request or approval comments

    # Organization scoping — set at creation from the creating user's primary org
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    # New-Joiner Assignment
    assigned_to = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="handovers")
    project = relationship("Project", back_populates="handovers")
    documents = relationship("Document", back_populates="handover")
    assignee = relationship("User", foreign_keys=[assigned_to], back_populates="assigned_handovers")

    @property
    def assigned_to_name(self) -> Optional[str]:
        return self.assignee.full_name if self.assignee else None

    @property
    def assigned_to_email(self) -> Optional[str]:
        return self.assignee.email if self.assignee else None


# ==========================================
# 5. Risk, Radar, Sentinel & Environment
# ==========================================

class KnowledgeLossIndicator(Base):
    __tablename__ = "knowledge_loss_indicators"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("rad-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    module_name = Column(String(255), nullable=False, index=True)
    gap_type = Column(String(50), nullable=False)  # ADR_MISSING, SECONDARY_OWNER_MISSING, STALE_DOCUMENTATION
    severity = Column(String(50), default="medium", nullable=False, index=True)
    description = Column(Text, nullable=False)
    recommended_remediation = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    detected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="loss_indicators")


class SentinelEvent(Base):
    __tablename__ = "sentinel_events"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("risk-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    project_name = Column(String(255), nullable=False, index=True)
    risk_level = Column(String(50), default="medium", nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    detected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="sentinel_events")


class EnvironmentSnapshot(Base):
    __tablename__ = "environment_snapshots"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("env-"))
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_name = Column(String(100), default="development", nullable=False)
    stack_type = Column(String(100), nullable=False)
    blueprint_spec = Column(JSON, nullable=False)
    powershell_quickstart = Column(Text, nullable=True)
    bash_quickstart = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    project = relationship("Project", back_populates="environment_snapshots")


# ==========================================
# 6. Immutable Compliance Audit Trail
# ==========================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("aud-"))
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = relationship("User", back_populates="audit_logs")


# ==========================================
# 7. Conversational AI Agents & Chat Copilot
# ==========================================

class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("th-"))
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False, index=True)  # onboarding_navigator, handover_interviewer, memory_specialist, sentinel_guardian
    title = Column(String(255), nullable=False)
    context_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organization = relationship("Organization")
    project = relationship("Project")
    user = relationship("User")
    messages = relationship("ChatMessage", back_populates="thread", cascade="all, delete-orphan", order_by="ChatMessage.created_at.asc()")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(64), primary_key=True, default=lambda: generate_uuid("msg-"))
    thread_id = Column(String(64), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True, default=list)
    recommended_actions = Column(JSON, nullable=True, default=list)
    tool_calls = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    thread = relationship("ChatThread", back_populates="messages")
