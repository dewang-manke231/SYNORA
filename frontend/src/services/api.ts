import type {
  HealthStatus,
  HandoverItem,
  HandoverCreatePayload,
  HandoverUpdatePayload,
  HandoverExportResponse,
  AssigneeUser,
  RiskAlert,
  SentinelOverview,
  SentinelScanResponse,
  SentinelRemediatePayload,
  SentinelRemediateResponse,
  KnowledgeNode,
  KnowledgeGapItem,
  ProjectCoverageDetail,
  RadarOverview,
  RadarScanResponse,
  RadarRiskRemediatePayload,
  RadarRiskRemediateResponse,
  DocumentItem,
  DocumentDetail,
  DocumentChunkItem,
  LLMStatus,
  GraphData,
  KnowledgeQueryResponse,
  EmbeddingStatus,
  ManifestInspectionResult,
  EnvironmentBlueprint,
  ReadinessAssessment,
  OnboardingChecklist,
  OnboardingChecklistUpdatePayload,
  UserProfile,
  AuthTokenResponse,
  LoginPayload,
  RegisterPayload,
  ProjectRecord,
  ProjectIntakeResult,
  ChatAgent,
  ChatThread,
  ChatMessage,
  ChatAgentType,
  ChatServiceStatus,
} from '../types'

const VITE_API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')
const API_BASE = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'
const PROJECT_CACHE_TTL_MS = 20_000
let projectsCache: { token: string; expiresAt: number; rows: ProjectRecord[] } | null = null
let projectsInFlight: { token: string; request: Promise<ProjectRecord[]> } | null = null

function authFetchWithTimeout(input: RequestInfo | URL, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  return authFetch(input, { ...init, signal: controller.signal }).finally(() => window.clearTimeout(timeout))
}

async function chatRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(`${API_BASE}/chat${path}`, init)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(getApiError(err, `Chat request failed (${res.status})`))
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const fetchChatAgents = () => chatRequest<ChatAgent[]>('/agents')
export const fetchChatStatus = () => chatRequest<ChatServiceStatus>('/status')
export const fetchChatThreads = (projectId?: string) => chatRequest<ChatThread[]>(projectId ? `/threads?project_id=${encodeURIComponent(projectId)}` : '/threads')
export const fetchChatThread = (threadId: string) => chatRequest<ChatThread>(`/threads/${encodeURIComponent(threadId)}`)
const BACKEND_CHAT_AGENT_TYPES = ['onboarding_navigator', 'handover_interviewer', 'memory_specialist', 'sentinel_guardian'] as const

export const createChatThread = (agentType: ChatAgentType, projectId?: string, contextId?: string, title?: string) => {
  if (agentType !== 'auto' && !BACKEND_CHAT_AGENT_TYPES.includes(agentType)) {
    return Promise.reject(new Error('Choose one of the available Synora specialists.'))
  }
  const backendAgentType = agentType === 'auto' ? 'memory_specialist' : agentType
  const threadTitle = agentType === 'auto' ? title || 'NOVA · Auto' : title
  return chatRequest<ChatThread>('/threads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ agent_type: backendAgentType, project_id: projectId, context_id: contextId, title: threadTitle }) })
}
export const sendChatMessage = (threadId: string, content: string, pageContext?: string, action?: string) =>
  chatRequest<ChatMessage>(`/threads/${encodeURIComponent(threadId)}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, page_context: pageContext, action }) })

export function getAuthToken(): string | null {
  return localStorage.getItem('synora_auth_token')
}

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem('synora_auth_token', token)
  } else {
    localStorage.removeItem('synora_auth_token')
  }
}

export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const token = getAuthToken()
  const headers = new Headers(init.headers || {})
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await window.fetch(input, { ...init, headers })
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('synora-unauthorized'))
  }
  return response
}

export async function loginUser(payload: LoginPayload): Promise<AuthTokenResponse> {
  const res = await window.fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Authentication failed' }))
    throw new Error(err.detail || 'Login failed. Please check your email and password.')
  }
  const data: AuthTokenResponse = await res.json()
  setAuthToken(data.access_token)
  return data
}

export interface PublicDemoCredentials {
  manager: { email: string; password: string }
  employee: { email: string; password: string }
}

export async function fetchPublicDemoCredentials(): Promise<PublicDemoCredentials> {
  const res = await window.fetch(`${API_BASE}/auth/demo-credentials`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Public demo credentials are unavailable.')
  }
  return res.json()
}

export async function demoLoginUser(role: 'manager' | 'employee'): Promise<AuthTokenResponse> {
  const res = await window.fetch(`${API_BASE}/auth/demo-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Demo sign-in is unavailable.' }))
    if (res.status === 404 && err.detail === 'Not Found') {
      throw new Error('The backend has not loaded prototype sign-in yet. Restart the Synora backend, then try again.')
    }
    throw new Error(err.detail || 'Demo sign-in is unavailable.')
  }
  const data: AuthTokenResponse = await res.json()
  setAuthToken(data.access_token)
  return data
}

export async function registerUser(payload: RegisterPayload): Promise<AuthTokenResponse> {
  const res = await window.fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Registration failed' }))
    throw new Error(err.detail || 'Registration failed. Please check your details.')
  }
  const data: AuthTokenResponse = await res.json()
  setAuthToken(data.access_token)
  return data
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  const res = await authFetch(`${API_BASE}/auth/me`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unauthorized' }))
    throw new Error(err.detail || 'Session expired. Please sign in again.')
  }
  return res.json()
}

export function logoutUser(): void {
  setAuthToken(null)
  localStorage.removeItem('synora_user')
  window.dispatchEvent(new CustomEvent('synora-logged-out'))
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await authFetch(`${API_BASE}/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

function getApiError(payload: any, fallback: string): string {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback
}

export async function fetchProjects(): Promise<ProjectRecord[]> {
  const token = getAuthToken() || ''
  if (projectsCache?.token === token && projectsCache.expiresAt > Date.now()) return projectsCache.rows
  if (projectsInFlight?.token === token) return projectsInFlight.request

  const request = (async () => {
    let res: Response
    try {
      res = await authFetchWithTimeout(`${API_BASE}/projects`, {}, 10_000)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('Loading projects timed out. Check the Synora backend and try again.')
      }
      throw error
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(getApiError(err, 'Failed to load projects'))
    }
    const rows = await res.json() as ProjectRecord[]
    projectsCache = { token, expiresAt: Date.now() + PROJECT_CACHE_TTL_MS, rows }
    return rows
  })()
  projectsInFlight = { token, request }
  try {
    return await request
  } finally {
    if (projectsInFlight?.request === request) projectsInFlight = null
  }
}

export function invalidateProjectsCache(): void {
  projectsCache = null
}

export async function fetchProject(projectId: string): Promise<ProjectRecord> {
  const res = await authFetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(getApiError(err, 'Failed to load project'))
  }
  return res.json()
}

export async function updateProjectRepository(projectId: string, repositoryUrl: string): Promise<ProjectRecord> {
  const res = await authFetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/repository`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repository_url: repositoryUrl || null }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(getApiError(err, 'Failed to save repository URL'))
  }
  const project = await res.json() as ProjectRecord
  invalidateProjectsCache()
  return project
}

export async function intakeProjectZip(
  projectName: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<ProjectIntakeResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('project_name', projectName)
    form.append('file', file)
    xhr.open('POST', `${API_BASE}/projects/intake`)
    const token = getAuthToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onerror = () => reject(new Error('Network error while uploading the project archive.'))
    xhr.onabort = () => reject(new Error('Project upload was cancelled.'))
    xhr.onload = () => {
      const response = (() => {
        try { return JSON.parse(xhr.responseText) } catch { return {} }
      })()
      if (xhr.status === 401) window.dispatchEvent(new CustomEvent('synora-unauthorized'))
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(getApiError(response, `Project upload failed (${xhr.status})`)))
        return
      }
      invalidateProjectsCache()
      resolve(response as ProjectIntakeResult)
    }
    xhr.send(form)
  })
}

export async function extractProjectZip(
  projectId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<ProjectIntakeResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file)
    xhr.open('POST', `${API_BASE}/projects/${encodeURIComponent(projectId)}/extract`)
    const token = getAuthToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onerror = () => reject(new Error('Network error while extracting the project archive.'))
    xhr.onabort = () => reject(new Error('Project extraction was cancelled.'))
    xhr.onload = () => {
      const response = (() => { try { return JSON.parse(xhr.responseText) } catch { return {} } })()
      if (xhr.status === 401) window.dispatchEvent(new CustomEvent('synora-unauthorized'))
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(getApiError(response, `Project extraction failed (${xhr.status})`)))
        return
      }
      resolve(response as ProjectIntakeResult)
    }
    xhr.send(form)
  })
}

// Handover APIs
export async function fetchHandovers(status?: string, assignedTo?: string): Promise<HandoverItem[]> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  if (assignedTo) params.append('assigned_to', assignedTo)
  const queryStr = params.toString() ? `?${params.toString()}` : ''
  const res = await authFetch(`${API_BASE}/handovers/${queryStr}`)
  if (!res.ok) throw new Error('Failed to load handovers')
  return res.json()
}

export async function fetchEligibleAssignees(): Promise<AssigneeUser[]> {
  const res = await authFetch(`${API_BASE}/handovers/assignees`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to load assignees' }))
    throw new Error(err.detail || 'Failed to load eligible assignees')
  }
  return res.json()
}

export async function createOrganizationEmployee(payload: { full_name: string; email: string; password: string }): Promise<AssigneeUser> {
  const res = await authFetch(`${API_BASE}/auth/employees`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(getApiError(err, 'Could not add employee'))
  }
  return res.json()
}

export async function assignHandover(
  handoverId: string,
  assignedTo: string,
  notes?: string
): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(handoverId)}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assigned_to: assignedTo, notes }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Assignment failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to assign handover')
  }
  return res.json()
}

export async function getHandover(id: string): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error(`Failed to load handover ${id}`)
  return res.json()
}

export async function createHandover(payload: HandoverCreatePayload): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Creation failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to create handover')
  }
  return res.json()
}

export async function updateHandover(id: string, payload: HandoverUpdatePayload): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Update failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to update handover')
  }
  return res.json()
}

export async function submitHandover(id: string, actorName: string): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_name: actorName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Submission failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to submit handover')
  }
  return res.json()
}

export async function startHandoverReview(id: string, actorName: string): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}/start-review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_name: actorName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Review start failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to start review')
  }
  return res.json()
}

export async function approveHandover(id: string, actorName: string, notes?: string): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_name: actorName, notes }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Approval failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to approve handover')
  }
  return res.json()
}

export async function requestHandoverChanges(id: string, reviewerName: string, reason: string): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}/request-changes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reviewer_name: reviewerName, reason }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Change request failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to request changes')
  }
  return res.json()
}

export async function completeHandover(id: string, actorName: string): Promise<HandoverItem> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_name: actorName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Completion failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to complete handover')
  }
  return res.json()
}

export async function exportHandoverMarkdown(id: string): Promise<HandoverExportResponse> {
  const res = await authFetch(`${API_BASE}/handovers/${encodeURIComponent(id)}/export`)
  if (!res.ok) throw new Error('Failed to export handover markdown')
  return res.json()
}

export function getHandoverDownloadUrl(id: string): string {
  return `${API_BASE}/handovers/${encodeURIComponent(id)}/export?download=true`
}

// Sentinel APIs (Module 7)
export async function fetchRisks(filters?: {
  project_id?: string
  severity?: string
  category?: string
  is_resolved?: boolean
}): Promise<RiskAlert[]> {
  const params = new URLSearchParams()
  if (filters?.project_id) params.append('project_id', filters.project_id)
  if (filters?.severity && filters.severity !== 'all') params.append('severity', filters.severity)
  if (filters?.category && filters.category !== 'all') params.append('category', filters.category)
  if (filters?.is_resolved !== undefined) params.append('is_resolved', String(filters.is_resolved))

  const qs = params.toString()
  const url = qs ? `${API_BASE}/sentinel/risks?${qs}` : `${API_BASE}/sentinel/risks`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to load risks')
  return res.json()
}

export async function fetchSentinelOverview(projectId?: string): Promise<SentinelOverview> {
  const url = projectId
    ? `${API_BASE}/sentinel/overview?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/sentinel/overview`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to fetch sentinel overview')
  return res.json()
}

export async function triggerSentinelScan(payload?: {
  project_id?: string
  handover_id?: string
  actor_name?: string
}): Promise<SentinelScanResponse> {
  const res = await authFetch(`${API_BASE}/sentinel/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Sentinel scan failed' }))
    throw new Error(err.detail?.message || err.detail || 'Sentinel scan execution failed')
  }
  return res.json()
}

export async function remediateSentinelRisk(
  riskId: string,
  payload: SentinelRemediatePayload
): Promise<SentinelRemediateResponse> {
  const res = await authFetch(`${API_BASE}/sentinel/risks/${encodeURIComponent(riskId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Remediation failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to remediate finding')
  }
  return res.json()
}

export async function fetchKnowledgeNodes(params?: {
  category?: string
  verification_status?: string
  document_id?: string
  project_id?: string
}): Promise<KnowledgeNode[]> {
  const searchParams = new URLSearchParams()
  if (params?.category && params.category !== 'all') searchParams.append('category', params.category)
  if (params?.verification_status && params.verification_status !== 'all') {
    searchParams.append('verification_status', params.verification_status)
  }
  if (params?.document_id) searchParams.append('document_id', params.document_id)
  if (params?.project_id) searchParams.append('project_id', params.project_id)

  const query = searchParams.toString()
  const url = query ? `${API_BASE}/knowledge/nodes?${query}` : `${API_BASE}/knowledge/nodes`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to load knowledge nodes')
  return res.json()
}

export async function fetchLLMStatus(): Promise<LLMStatus> {
  const res = await authFetch(`${API_BASE}/knowledge/llm-status`)
  if (!res.ok) throw new Error('Failed to check LLM status')
  return res.json()
}

export async function extractKnowledgeFromDocument(
  documentId: string,
  actorName?: string
): Promise<KnowledgeNode[]> {
  const res = await authFetch(`${API_BASE}/knowledge/extract/${encodeURIComponent(documentId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_name: actorName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Extraction failed' }))
    const msg = typeof err.detail === 'string' ? err.detail : 'Failed to extract knowledge from document'
    throw new Error(msg)
  }
  return res.json()
}

export async function verifyKnowledgeNode(
  nodeId: string,
  payload: {
    action: string
    reviewer_name: string
    notes?: string
    modified_label?: string
    modified_details?: string
  }
): Promise<KnowledgeNode> {
  const res = await authFetch(`${API_BASE}/knowledge/nodes/${encodeURIComponent(nodeId)}/verify`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Verification failed' }))
    const msg = typeof err.detail === 'string' ? err.detail : 'Failed to verify knowledge node'
    throw new Error(msg)
  }
  return res.json()
}

export async function fetchKnowledgeGraph(projectId?: string): Promise<GraphData> {
  const url = projectId && projectId !== 'all'
    ? `${API_BASE}/knowledge/graph?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/knowledge/graph`
  let res: Response
  try {
    res = await authFetchWithTimeout(url, {}, 15_000)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Knowledge graph took too long to load. Retry or choose a smaller project scope.')
    }
    throw error
  }
  if (!res.ok) throw new Error('Failed to load knowledge graph')
  return res.json()
}

export async function queryKnowledgeAssistant(payload: {
  project_id: string
  query: string
  similarity_threshold?: number
  top_k?: number
}): Promise<KnowledgeQueryResponse> {
  const res = await authFetch(`${API_BASE}/knowledge/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Assistant query failed' }))
    const msg = typeof err.detail === 'string' ? err.detail : 'Failed to query Knowledge Assistant'
    throw new Error(msg)
  }
  return res.json()
}

export async function fetchEmbeddingStatus(): Promise<EmbeddingStatus> {
  const res = await authFetch(`${API_BASE}/knowledge/embedding-status`)
  if (!res.ok) throw new Error('Failed to load embedding status')
  return res.json()
}

export async function fetchRadarGaps(): Promise<KnowledgeGapItem[]> {
  const res = await authFetch(`${API_BASE}/radar/gaps`)
  if (!res.ok) throw new Error('Failed to load radar gaps')
  return res.json()
}

export async function fetchProjectCoverage(projectId?: string): Promise<ProjectCoverageDetail[]> {
  const url = projectId
    ? `${API_BASE}/radar/coverage?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/radar/coverage`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to load project coverage')
  return res.json()
}

// Document Ingestion APIs (Module 1)
export async function fetchDocuments(params?: {
  project_id?: string
  handover_id?: string
  status?: string
}): Promise<DocumentItem[]> {
  const searchParams = new URLSearchParams()
  if (params?.project_id) searchParams.append('project_id', params.project_id)
  if (params?.handover_id) searchParams.append('handover_id', params.handover_id)
  if (params?.status) searchParams.append('status_filter', params.status)

  const query = searchParams.toString()
  const url = query ? `${API_BASE}/documents/?${query}` : `${API_BASE}/documents/`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to load documents')
  return res.json()
}

export async function fetchDocumentDetail(id: string): Promise<DocumentDetail> {
  const res = await authFetch(`${API_BASE}/documents/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error('Failed to load document details')
  return res.json()
}

export async function fetchDocumentChunks(id: string): Promise<DocumentChunkItem[]> {
  const res = await authFetch(`${API_BASE}/documents/${encodeURIComponent(id)}/chunks`)
  if (!res.ok) throw new Error('Failed to load document chunks')
  return res.json()
}

export async function uploadDocument(
  file: File,
  options?: {
    project_id?: string
    handover_id?: string
    uploader_name?: string
  }
): Promise<DocumentDetail> {
  const formData = new FormData()
  formData.append('file', file)
  if (options?.project_id) formData.append('project_id', options.project_id)
  if (options?.handover_id) formData.append('handover_id', options.handover_id)
  if (options?.uploader_name) formData.append('uploader_name', options.uploader_name)

  const res = await authFetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: 'Upload failed' }))
    const msg =
      typeof errorData.detail === 'object' && errorData.detail?.message
        ? errorData.detail.message
        : typeof errorData.detail === 'string'
        ? errorData.detail
        : 'Failed to upload document'
    throw new Error(msg)
  }

  return res.json()
}

export async function deleteDocument(
  id: string,
  actorName?: string
): Promise<{ success: boolean; deleted_id: string }> {
  const url = actorName
    ? `${API_BASE}/documents/${encodeURIComponent(id)}?actor_name=${encodeURIComponent(actorName)}`
    : `${API_BASE}/documents/${encodeURIComponent(id)}`
  const res = await authFetch(url, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete document')
  return res.json()
}

// ==========================================
// Module 5: Knowledge Loss Radar APIs
// ==========================================

export async function fetchRadarOverview(projectId?: string): Promise<RadarOverview> {
  const url = projectId
    ? `${API_BASE}/radar/overview?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/radar/overview`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to fetch radar overview')
  return res.json()
}

export async function fetchRadarRisks(filters?: {
  project_id?: string
  severity?: string
  gap_type?: string
  is_resolved?: boolean
}): Promise<KnowledgeGapItem[]> {
  const params = new URLSearchParams()
  if (filters?.project_id) params.append('project_id', filters.project_id)
  if (filters?.severity && filters.severity !== 'all') params.append('severity', filters.severity)
  if (filters?.gap_type && filters.gap_type !== 'all') params.append('gap_type', filters.gap_type)
  if (filters?.is_resolved !== undefined) params.append('is_resolved', String(filters.is_resolved))

  const qs = params.toString()
  const url = qs ? `${API_BASE}/radar/risks?${qs}` : `${API_BASE}/radar/risks`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to fetch radar risks')
  return res.json()
}

export async function triggerRadarScan(payload?: {
  project_id?: string
  actor_name?: string
}): Promise<RadarScanResponse> {
  const res = await authFetch(`${API_BASE}/radar/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Radar scan failed' }))
    throw new Error(err.detail?.message || err.detail || 'Radar scan execution failed')
  }
  return res.json()
}

export async function remediateRadarRisk(
  riskId: string,
  payload: RadarRiskRemediatePayload
): Promise<RadarRiskRemediateResponse> {
  const res = await authFetch(`${API_BASE}/radar/risks/${encodeURIComponent(riskId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Remediation failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to remediate risk')
  }
  return res.json()
}

// ==========================================
// Module 8: Environment Recreator APIs
// ==========================================

export async function fetchManifestInspection(projectId?: string): Promise<ManifestInspectionResult> {
  const url = projectId
    ? `${API_BASE}/recreator/inspect?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/recreator/inspect`
  const res = await authFetch(url)
  if (!res.ok) throw new Error('Failed to inspect repository manifests')
  return res.json()
}

export async function fetchEnvironmentBlueprint(projectId: string): Promise<EnvironmentBlueprint> {
  const res = await authFetch(`${API_BASE}/recreator/blueprint?project_id=${encodeURIComponent(projectId)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to load blueprint' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to load environment blueprint')
  }
  return res.json()
}

export async function generateEnvironmentBlueprint(
  projectId: string,
  actorName = 'Developer'
): Promise<EnvironmentBlueprint> {
  const res = await authFetch(`${API_BASE}/recreator/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, actor_name: actorName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Blueprint generation failed' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to generate blueprint')
  }
  return res.json()
}

export async function fetchEnvironmentReadiness(projectId: string): Promise<ReadinessAssessment> {
  const res = await authFetch(`${API_BASE}/recreator/readiness?project_id=${encodeURIComponent(projectId)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch readiness assessment' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to evaluate readiness')
  }
  return res.json()
}

export async function fetchOnboardingChecklist(projectId: string): Promise<OnboardingChecklist> {
  const res = await authFetch(`${API_BASE}/recreator/checklist?project_id=${encodeURIComponent(projectId)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch onboarding checklist' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to load onboarding checklist')
  }
  return res.json()
}

export async function updateOnboardingChecklist(
  payload: OnboardingChecklistUpdatePayload
): Promise<OnboardingChecklist> {
  const res = await authFetch(`${API_BASE}/recreator/checklist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to update checklist step' }))
    throw new Error(err.detail?.message || err.detail || 'Failed to update checklist step')
  }
  return res.json()
}

export function getEnvExampleDownloadUrl(projectId: string): string {
  return `${API_BASE}/recreator/export/env?project_id=${encodeURIComponent(projectId)}`
}

export function getDockerComposeDownloadUrl(projectId: string): string {
  return `${API_BASE}/recreator/export/docker?project_id=${encodeURIComponent(projectId)}`
}




