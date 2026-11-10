export interface HealthStatus {
  status: string
  version: string
  service: string
  database?: string
  database_type?: string
  database_target?: string
  pgvector_installed?: boolean
  latency_ms?: number
  tables_count?: number
  timestamp: string
}

export interface ProjectRecord {
  id: string
  name: string
  organization_id: string | null
  description?: string | null
  repository_url?: string | null
  created_at: string
}

export interface ProjectIntakeFinding {
  category: string
  severity: string
  evidence_type: 'observed' | 'inference' | string
  source: string
  evidence: string
}

export interface ProjectIntakeResult {
  project_id: string
  project_name: string
  indexed_file_count: number
  skipped_file_count: number
  manifests: string[]
  detected_technologies: string[]
  extracted_file_names?: string[]
  todo_count: number
  findings: ProjectIntakeFinding[]
  radar_gaps_created: number
  radar_coverage_score: number
  sentinel_findings_created: number
  sentinel_integrity_score: number
}

export type ChatAgentType = 'auto' | 'onboarding_navigator' | 'handover_interviewer' | 'memory_specialist' | 'sentinel_guardian'
export interface ChatAgent { agent_type: ChatAgentType; name: string; description: string; allowed_roles: string[] }
export interface ChatCitation { citation_id?: string; source_type?: string; source_id?: string; document_id?: string; document_name?: string; file_path?: string; chunk_id?: string; chunk_index?: number; snippet?: string; relevance?: number; retrieval_methods?: string[]; verification_status?: string; source_quote?: string }
export interface ChatMessage { id: string; thread_id: string; sender_role: string; content: string; citations?: ChatCitation[]; recommended_actions?: Array<Record<string, any>>; tool_calls?: Array<Record<string, any>>; created_at: string }
export interface ChatThread { id: string; organization_id: string; project_id?: string | null; user_id: string; agent_type: ChatAgentType; title: string; context_id?: string | null; created_at: string; updated_at: string; messages: ChatMessage[] }
export interface ChatServiceStatus { provider?: string; model?: string; configured: boolean; is_mock: boolean; status: string; message: string }

export type HandoverStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'changes_requested'
  | 'verified'
  | 'completed'

export interface HandoverItem {
  id: string
  organization_id?: string | null
  project_id?: string | null
  project_name?: string | null
  project_description?: string | null
  employee_name: string
  role: string
  department: string
  transition_type: string
  status: HandoverStatus
  readiness_score: number
  key_responsibilities: string[]
  critical_dependencies: string[]
  unresolved_blockers: string[]
  completed_tasks: string[]
  pending_tasks: string[]
  important_notes?: string | null
  recommended_next_actions: string[]
  repository_links: string[]
  documentation_links: string[]
  database_references: string[]
  reviewed_by?: string | null
  reviewed_at?: string | null
  review_decision?: string | null
  review_notes?: string | null
  assigned_to?: string | null
  assigned_to_name?: string | null
  assigned_to_email?: string | null
  assigned_at?: string | null
  created_at: string
  updated_at: string
}

export interface AssigneeUser {
  id: string
  email: string
  full_name: string
  role: string
  organization_id?: string | null
  organization_name?: string | null
  is_active: boolean
  created_at: string
}

export interface HandoverCreatePayload {
  organization_id?: string | null
  project_id?: string | null
  project_name?: string | null
  project_description?: string | null
  employee_name: string
  role: string
  department: string
  transition_type: string
  key_responsibilities: string[]
  critical_dependencies: string[]
  unresolved_blockers: string[]
  completed_tasks: string[]
  pending_tasks: string[]
  important_notes?: string | null
  recommended_next_actions: string[]
  repository_links: string[]
  documentation_links: string[]
  database_references: string[]
}

export interface HandoverUpdatePayload {
  project_name?: string | null
  project_description?: string | null
  role?: string
  department?: string
  transition_type?: string
  key_responsibilities?: string[]
  critical_dependencies?: string[]
  unresolved_blockers?: string[]
  completed_tasks?: string[]
  pending_tasks?: string[]
  important_notes?: string | null
  recommended_next_actions?: string[]
  repository_links?: string[]
  documentation_links?: string[]
  database_references?: string[]
}

export interface HandoverExportResponse {
  id: string
  filename: string
  markdown_content: string
  exported_at: string
}

export interface RiskAlert {
  id: string
  project_id?: string | null
  project_name: string
  risk_level: 'critical' | 'high' | 'medium' | 'low' | string
  category: string
  description: string
  detected_at: string
  recommended_action: string
  is_resolved?: boolean
  resolved_at?: string | null
  confidence_score?: number
  finding_type?: 'verified_fact' | 'unverified_claim' | 'suspected_inconsistency' | string
  evidence_source?: string | null
}

export interface ProjectIntegrityDetail {
  project_id: string
  project_name: string
  integrity_score: number
  grade: string
  active_findings_count: number
  critical_count: number
  high_count: number
  handovers_count: number
  bus_factor: number
}

export interface SentinelOverview {
  average_integrity_score: number
  overall_grade: string
  total_active_findings: number
  critical_findings: number
  high_findings: number
  medium_findings: number
  resolved_findings: number
  verified_items_count: number
  projects: ProjectIntegrityDetail[]
  formula: string
}

export interface SentinelScanResponse {
  message: string
  scanned_handovers_count: number
  new_findings_created: number
  active_findings_total: number
  integrity_score: number
  detected_findings: RiskAlert[]
}

export interface SentinelRemediatePayload {
  action?: 'resolve' | 'acknowledge' | 'request_changes' | string
  actor_name: string
  notes?: string | null
}

export interface SentinelRemediateResponse {
  message: string
  risk: RiskAlert
  updated_integrity_score: number
}

export interface KnowledgeNode {
  id: string
  project_id?: string | null
  document_id?: string | null
  chunk_id?: string | null
  label: string
  category: string
  details: string
  owner?: string | null
  confidence?: number
  confidence_score?: number
  is_flagged_for_review?: boolean
  verification_status?: string
  source_quote?: string | null
  metadata_tags?: Record<string, any> | null
  created_at?: string
  updated_at?: string
}

export interface LLMStatus {
  configured: boolean
  provider: string
  model: string
  status: string
  message: string
}

export interface KnowledgeGapItem {
  id: string
  project_id: string
  module_name: string
  gap_type: string
  severity: 'critical' | 'high' | 'medium' | 'low' | string
  description: string
  recommended_remediation?: string | null
  is_resolved: boolean
  detected_at: string
  resolved_at?: string | null
}

export interface ScoreFactorBreakdown {
  documentation_points: number
  decision_points: number
  ownership_points: number
  verification_points: number
}

export interface PenaltyDeduction {
  gap_id: string
  module_name: string
  severity: string
  deduction: number
}

export interface CoverageExplanation {
  score: number
  raw_score: number
  penalties: number
  formula: string
  grade: string
  breakdown: ScoreFactorBreakdown
  penalty_breakdown: PenaltyDeduction[]
  active_gaps_count: number
  critical_gaps_count: number
  high_gaps_count: number
  medium_gaps_count: number
  low_gaps_count: number
}

export interface ProjectCoverage {
  id: string
  name: string
  slug: string
  bus_factor: number
  knowledge_coverage_score: number
}

export interface ProjectCoverageDetail {
  id: string
  name: string
  slug: string
  bus_factor: number
  knowledge_coverage_score: number
  grade: string
  active_gaps_count: number
  critical_gaps_count: number
  explanation?: CoverageExplanation | null
}

export interface RadarOverview {
  average_coverage_score: number
  overall_grade: string
  total_active_gaps: number
  critical_gaps: number
  high_gaps: number
  medium_gaps: number
  resolved_gaps: number
  projects: ProjectCoverageDetail[]
  scoring_formula: string
}

export interface RadarScanResponse {
  message: string
  project_id?: string | null
  scanned_projects_count: number
  new_gaps_created: number
  active_gaps_total: number
  coverage_score: number
  explanation?: CoverageExplanation | null
  detected_risks: KnowledgeGapItem[]
}

export interface RadarRiskRemediatePayload {
  action?: string
  actor_name: string
  notes?: string | null
}

export interface RadarRiskRemediateResponse {
  message: string
  risk: KnowledgeGapItem
  updated_coverage_score: number
  explanation?: CoverageExplanation | null
}

export interface DocumentItem {
  id: string
  project_id: string
  handover_id?: string | null
  filename: string
  content_type: string
  file_size: number
  file_hash?: string | null
  storage_path?: string | null
  processing_status: 'uploaded' | 'processing' | 'processed' | 'completed' | 'failed'
  error_message?: string | null
  chunk_count: number
  metadata_tags?: Record<string, any> | null
  uploaded_at: string
}

export interface DocumentDetail extends DocumentItem {
  raw_text: string
}

export interface DocumentChunkItem {
  id: string
  document_id: string
  chunk_index: number
  chunk_text: string
  token_count?: number
  page_number?: number | null
  metadata_tags?: Record<string, any> | null
  created_at: string
}

export interface GraphNode {
  id: string
  label: string
  node_type: string
  category?: string | null
  details?: string | null
  owner?: string | null
  confidence_score: number
  verification_status: string
  document_id?: string | null
  chunk_id?: string | null
  source_quote?: string | null
  project_id?: string | null
  metadata_tags?: Record<string, any> | null
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation_type: string
  confidence: number
  metadata_tags?: Record<string, any> | null
}

export interface GraphData {
  project_id?: string | null
  project_name?: string | null
  nodes: GraphNode[]
  edges: GraphEdge[]
  total_nodes: number
  total_edges: number
  verified_nodes: number
  unverified_nodes: number
}

export interface SourceCitation {
  document_id: string
  document_name: string
  chunk_id: string
  chunk_index: number
  page_number?: number | null
  similarity_score: number
  verification_status: string
  snippet: string
}

export interface KnowledgeQueryResponse {
  query: string
  project_id: string
  project_name: string
  answer: string
  confidence: number
  is_grounded: boolean
  has_verified_knowledge: boolean
  uncertainty_warning?: string | null
  citations: SourceCitation[]
  retrieved_chunk_count: number
  processing_time_ms: number
}

export interface EmbeddingStatus {
  configured: boolean
  provider: string
  model: string
  dimension: number
  status: string
  message: string
}

// ==========================================
// Module 8: Environment Recreator Types
// ==========================================

export interface ManifestInspectionResult {
  stack_type: string
  detected_frameworks: string[]
  python_version?: string | null
  node_version?: string | null
  manifest_files_found: string[]
  backend_dependencies: string[]
  frontend_dependencies: string[]
  scripts: Record<string, string>
  environment_variables_detected: string[]
  confidence_breakdown: Record<string, string>
}

export interface EnvironmentBlueprint {
  id: string
  project_id: string
  environment_name: string
  stack_type: string
  powershell_quickstart: string
  bash_quickstart: string
  docker_compose_yaml: string
  env_example_content: string
  blueprint_spec: Record<string, any>
  created_at: string
}

export interface PrerequisiteCheck {
  tool: string
  required_version: string
  installed_version?: string | null
  is_met: boolean
  guidance: string
}

export interface PotentialFailureMode {
  risk_factor: string
  description: string
  mitigation: string
  severity: string
}

export interface ReadinessAssessment {
  project_id: string
  status: 'ready' | 'action_required' | 'warning' | string
  readiness_score: number
  prerequisites: PrerequisiteCheck[]
  potential_failure_modes: PotentialFailureMode[]
  detected_vs_inferred: Record<string, string[]>
  missing_configurations: string[]
}

export interface OnboardingChecklistStep {
  id: string
  order: number
  title: string
  category: string
  command_snippet?: string | null
  is_completed: boolean
  completed_at?: string | null
  completed_by?: string | null
  notes?: string | null
}

export interface OnboardingChecklist {
  project_id: string
  project_name: string
  total_steps: number
  completed_steps: number
  completion_percentage: number
  steps: OnboardingChecklistStep[]
}

export interface OnboardingChecklistUpdatePayload {
  project_id: string
  step_id: string
  is_completed: boolean
  actor_name: string
  notes?: string | null
}

export type UserRole = 'manager' | 'employee' | 'admin'

export interface UserProfile {
  id: string
  email: string
  full_name: string
  role: UserRole
  organization_id?: string | null
  organization_name?: string | null
  is_active: boolean
  created_at: string
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: UserProfile
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  password: string
  full_name: string
  role?: string
  organization_name?: string
}


