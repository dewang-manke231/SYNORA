from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HealthStatus(BaseModel):
    status: str
    version: str
    service: str
    database: str
    database_type: Optional[str] = "sqlite"
    database_target: Optional[str] = "sqlite:///local"
    pgvector_installed: Optional[bool] = False
    latency_ms: Optional[float] = None
    tables_count: Optional[int] = 0
    timestamp: datetime = Field(default_factory=utc_now)


# ==========================================
# Handover Schemas (Lifecycle & Review)
# ==========================================

class HandoverItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    employee_name: str
    role: str
    department: str
    transition_type: str  # resignation, retirement, internal_transition, project_transfer
    status: str  # draft, submitted, under_review, changes_requested, verified, completed
    readiness_score: float = 0.0

    key_responsibilities: List[str] = Field(default_factory=list)
    critical_dependencies: List[str] = Field(default_factory=list)
    unresolved_blockers: List[str] = Field(default_factory=list)

    completed_tasks: List[str] = Field(default_factory=list)
    pending_tasks: List[str] = Field(default_factory=list)

    important_notes: Optional[str] = None
    recommended_next_actions: List[str] = Field(default_factory=list)

    repository_links: List[str] = Field(default_factory=list)
    documentation_links: List[str] = Field(default_factory=list)
    database_references: List[str] = Field(default_factory=list)

    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_decision: Optional[str] = None
    review_notes: Optional[str] = None

    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    assigned_to_email: Optional[str] = None
    assigned_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HandoverCreate(BaseModel):
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    employee_name: str
    role: str
    department: str
    transition_type: str = "resignation"
    key_responsibilities: List[str] = Field(default_factory=list)
    critical_dependencies: List[str] = Field(default_factory=list)
    unresolved_blockers: List[str] = Field(default_factory=list)
    completed_tasks: List[str] = Field(default_factory=list)
    pending_tasks: List[str] = Field(default_factory=list)
    important_notes: Optional[str] = None
    recommended_next_actions: List[str] = Field(default_factory=list)
    repository_links: List[str] = Field(default_factory=list)
    documentation_links: List[str] = Field(default_factory=list)
    database_references: List[str] = Field(default_factory=list)


class HandoverUpdate(BaseModel):
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    transition_type: Optional[str] = None
    key_responsibilities: Optional[List[str]] = None
    critical_dependencies: Optional[List[str]] = None
    unresolved_blockers: Optional[List[str]] = None
    completed_tasks: Optional[List[str]] = None
    pending_tasks: Optional[List[str]] = None
    important_notes: Optional[str] = None
    recommended_next_actions: Optional[List[str]] = None
    repository_links: Optional[List[str]] = None
    documentation_links: Optional[List[str]] = None
    database_references: Optional[List[str]] = None


class HandoverActionRequest(BaseModel):
    actor_name: str
    notes: Optional[str] = None


class HandoverChangeRequest(BaseModel):
    reviewer_name: str
    reason: str


class HandoverAssignRequest(BaseModel):
    assigned_to: str
    notes: Optional[str] = None


class HandoverExportResponse(BaseModel):
    id: str
    filename: str
    markdown_content: str
    exported_at: datetime = Field(default_factory=utc_now)


# ==========================================
# Other Product Module Schemas
# ==========================================

class RiskAlert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: str
    risk_level: str
    category: str
    description: str
    detected_at: datetime = Field(default_factory=utc_now)
    recommended_action: str
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    confidence_score: Optional[float] = 1.0
    finding_type: Optional[str] = "suspected_inconsistency"  # verified_fact, unverified_claim, suspected_inconsistency
    evidence_source: Optional[str] = None


class ProjectIntegrityDetail(BaseModel):
    project_id: str
    project_name: str
    integrity_score: float
    grade: str
    active_findings_count: int
    critical_count: int
    high_count: int
    handovers_count: int
    bus_factor: float


class SentinelOverviewResponse(BaseModel):
    average_integrity_score: float
    overall_grade: str
    total_active_findings: int
    critical_findings: int
    high_findings: int
    medium_findings: int
    resolved_findings: int
    verified_items_count: int
    projects: List[ProjectIntegrityDetail]
    formula: str


class SentinelScanRequest(BaseModel):
    project_id: Optional[str] = None
    handover_id: Optional[str] = None
    actor_name: Optional[str] = "Sentinel Integrity Scanner"


class SentinelScanResponse(BaseModel):
    message: str
    scanned_handovers_count: int
    new_findings_created: int
    active_findings_total: int
    integrity_score: float
    detected_findings: List[RiskAlert]


class SentinelRemediateRequest(BaseModel):
    action: str = "resolve"  # resolve, acknowledge, request_changes
    actor_name: str = "Reviewing Manager"
    notes: Optional[str] = None


class SentinelRemediateResponse(BaseModel):
    message: str
    risk: RiskAlert
    updated_integrity_score: float


class KnowledgeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    label: str
    category: str
    details: str
    owner: Optional[str] = None
    confidence_score: float = 1.0
    verification_status: str = "unverified"
    source_quote: Optional[str] = None
    metadata_tags: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeVerificationRequest(BaseModel):
    action: str  # verified, modified, rejected
    reviewer_name: str
    notes: Optional[str] = None
    modified_label: Optional[str] = None
    modified_details: Optional[str] = None


class KnowledgeExtractRequest(BaseModel):
    actor_name: Optional[str] = None


class LLMStatusResponse(BaseModel):
    configured: bool
    provider: str
    model: str
    status: str
    message: str


class KnowledgeGapItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    module_name: str
    gap_type: str
    severity: str
    description: str
    recommended_remediation: Optional[str] = None
    is_resolved: bool = False
    detected_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None


class PenaltyDeduction(BaseModel):
    gap_id: str
    module_name: str
    severity: str
    deduction: float


class ScoreFactorBreakdown(BaseModel):
    documentation_points: float
    decision_points: float
    ownership_points: float
    verification_points: float


class CoverageExplanation(BaseModel):
    score: float
    raw_score: float
    penalties: float
    formula: str
    grade: str
    breakdown: ScoreFactorBreakdown
    penalty_breakdown: List[PenaltyDeduction]
    active_gaps_count: int
    critical_gaps_count: int
    high_gaps_count: int
    medium_gaps_count: int
    low_gaps_count: int


class ProjectCoverage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    bus_factor: float
    knowledge_coverage_score: float


class ProjectCoverageDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    bus_factor: float
    knowledge_coverage_score: float
    grade: str
    active_gaps_count: int
    critical_gaps_count: int
    explanation: Optional[CoverageExplanation] = None


class RadarOverviewResponse(BaseModel):
    average_coverage_score: float
    overall_grade: str
    total_active_gaps: int
    critical_gaps: int
    high_gaps: int
    medium_gaps: int
    resolved_gaps: int
    projects: List[ProjectCoverageDetail]
    scoring_formula: str


class RadarScanRequest(BaseModel):
    project_id: Optional[str] = None
    actor_name: Optional[str] = "Radar Automated Observer"


class RadarScanResponse(BaseModel):
    message: str
    project_id: Optional[str] = None
    scanned_projects_count: int
    new_gaps_created: int
    active_gaps_total: int
    coverage_score: float
    explanation: Optional[CoverageExplanation] = None
    detected_risks: List[KnowledgeGapItem]


class RadarRiskRemediateRequest(BaseModel):
    action: str = "resolve"  # resolve, acknowledge
    actor_name: str = "Manager"
    notes: Optional[str] = None


class RadarRiskRemediateResponse(BaseModel):
    message: str
    risk: KnowledgeGapItem
    updated_coverage_score: float
    explanation: Optional[CoverageExplanation] = None


# ==========================================
# Document Ingestion & Chunk Schemas (Module 1)
# ==========================================

class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    chunk_text: str
    token_count: Optional[int] = 0
    page_number: Optional[int] = None
    metadata_tags: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=utc_now)


class DocumentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    handover_id: Optional[str] = None
    filename: str
    content_type: str
    file_size: int
    file_hash: Optional[str] = None
    storage_path: Optional[str] = None
    processing_status: str
    error_message: Optional[str] = None
    chunk_count: int = 0
    metadata_tags: Optional[Dict[str, Any]] = None
    uploaded_at: datetime = Field(default_factory=utc_now)


class DocumentDetailResponse(DocumentItemResponse):
    raw_text: str


class DocumentDeleteResponse(BaseModel):
    success: bool
    deleted_id: str
    message: str


class DocumentDownloadResponse(BaseModel):
    document_id: str
    filename: str
    storage_backend: str  # "supabase" or "local"
    download_url: str
    expires_in: int
    file_size: int
    file_hash: Optional[str] = None


class ProjectIntakeFinding(BaseModel):
    category: str
    severity: str
    evidence_type: str
    source: str
    evidence: str


class ProjectIntakeResponse(BaseModel):
    project_id: str
    project_name: str
    indexed_file_count: int
    skipped_file_count: int
    manifests: List[str]
    detected_technologies: List[str]
    extracted_file_names: List[str] = Field(default_factory=list)
    todo_count: int
    findings: List[ProjectIntakeFinding]
    radar_gaps_created: int
    radar_coverage_score: float
    sentinel_findings_created: int
    sentinel_integrity_score: float



# ==========================================
# Organizational Memory Graph Schemas (Module 3)
# ==========================================

class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str  # task, decision, document, dependency, blocker, owner, config, instruction, architecture, module
    category: Optional[str] = None
    details: Optional[str] = None
    owner: Optional[str] = None
    confidence_score: float = 1.0
    verification_status: str = "verified"  # verified, unverified, modified, rejected
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    source_quote: Optional[str] = None
    project_id: Optional[str] = None
    metadata_tags: Optional[Dict[str, Any]] = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation_type: str  # DEPENDS_ON, IMPLEMENTS, MAINTAINS, DOCUMENTED_IN, BLOCKED_BY, OWNS, INTERACTS_WITH
    confidence: float = 1.0
    metadata_tags: Optional[Dict[str, Any]] = None


class GraphResponse(BaseModel):
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_nodes: int
    total_edges: int
    verified_nodes: int
    unverified_nodes: int


# ==========================================
# AI Knowledge Assistant & Vector RAG Schemas (Module 4)
# ==========================================

class SourceCitation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    chunk_index: int
    page_number: Optional[int] = None
    similarity_score: float
    verification_status: str  # verified, unverified
    snippet: str


class KnowledgeQueryRequest(BaseModel):
    project_id: str
    query: str
    similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeQueryResponse(BaseModel):
    query: str
    project_id: str
    project_name: str
    answer: str
    confidence: float
    is_grounded: bool
    has_verified_knowledge: bool
    uncertainty_warning: Optional[str] = None
    citations: List[SourceCitation]
    retrieved_chunk_count: int
    processing_time_ms: float
    answer_source: str = "unknown"  # gemini or deterministic_fallback


class EmbeddingStatusResponse(BaseModel):
    configured: bool
    provider: str
    model: str
    dimension: int
    status: str
    message: str


# ==========================================
# Environment Recreator Schemas (Module 8)
# ==========================================

class ManifestInspectionResult(BaseModel):
    stack_type: str
    detected_frameworks: List[str]
    python_version: Optional[str] = None
    node_version: Optional[str] = None
    manifest_files_found: List[str]
    backend_dependencies: List[str]
    frontend_dependencies: List[str]
    scripts: Dict[str, str]
    environment_variables_detected: List[str]
    confidence_breakdown: Dict[str, str]  # 'detected', 'inferred', 'unverified'


class EnvironmentBlueprintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    environment_name: str
    stack_type: str
    powershell_quickstart: str
    bash_quickstart: str
    docker_compose_yaml: str
    env_example_content: str
    blueprint_spec: Dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


class PotentialFailureMode(BaseModel):
    risk_factor: str
    description: str
    mitigation: str
    severity: str  # critical, high, medium, low


class PrerequisiteCheck(BaseModel):
    tool: str
    required_version: str
    installed_version: Optional[str] = None
    is_met: bool
    guidance: str


class ReadinessAssessment(BaseModel):
    project_id: str
    status: str  # ready, action_required, warning
    readiness_score: float
    prerequisites: List[PrerequisiteCheck]
    potential_failure_modes: List[PotentialFailureMode]
    detected_vs_inferred: Dict[str, List[str]]
    missing_configurations: List[str]


class OnboardingChecklistStep(BaseModel):
    id: str
    order: int
    title: str
    category: str  # environment, dependencies, database, services, verification
    command_snippet: Optional[str] = None
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None


class OnboardingChecklistResponse(BaseModel):
    project_id: str
    project_name: str
    total_steps: int
    completed_steps: int
    completion_percentage: float
    steps: List[OnboardingChecklistStep]


class OnboardingChecklistUpdateRequest(BaseModel):
    project_id: str
    step_id: str
    is_completed: bool
    actor_name: str = "Incoming Engineer"
    notes: Optional[str] = None


class EnvironmentSnapshotCreateRequest(BaseModel):
    project_id: str
    environment_name: Optional[str] = "development"
    actor_name: Optional[str] = "Recreator Service"


# ==========================================
# Authentication & Security Schemas (Phase 8)
# ==========================================

class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, description="Password must be at least 8 characters")
    full_name: str
    role: str = Field(default="employee", description="Role: employee, manager, or admin")
    organization_name: Optional[str] = "Default Organization"


class EmployeeCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, description="Temporary password must be at least 8 characters")
    full_name: str = Field(min_length=1, max_length=255)


class UserLoginRequest(BaseModel):
    email: str
    password: str


class DemoLoginRequest(BaseModel):
    role: Literal["manager", "employee"]


class PublicDemoCredential(BaseModel):
    email: str
    password: str


class PublicDemoCredentials(BaseModel):
    manager: PublicDemoCredential
    employee: PublicDemoCredential


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


# ==========================================
# 8. Conversational AI Agent Schemas
# ==========================================

class ChatThreadCreate(BaseModel):
    agent_type: str  # onboarding_navigator, handover_interviewer, memory_specialist, sentinel_guardian
    title: Optional[str] = None
    project_id: Optional[str] = None
    context_id: Optional[str] = None


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    action: Optional[str] = None
    page_context: Optional[Literal["dashboard", "projects", "knowledge", "radar", "sentinel", "recreator", "handovers", "chat"]] = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    thread_id: str
    sender_role: str
    content: str
    citations: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    recommended_actions: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    created_at: datetime


class ChatThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    project_id: Optional[str] = None
    user_id: str
    agent_type: str
    title: str
    context_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: Optional[List[ChatMessageResponse]] = Field(default_factory=list)



