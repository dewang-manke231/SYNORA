import React, { useState, useEffect } from 'react'
import type {
  KnowledgeNode,
  LLMStatus,
  DocumentItem,
  GraphData,
  GraphNode,
  KnowledgeQueryResponse,
  EmbeddingStatus,
} from '../types'
import {
  fetchLLMStatus,
  fetchEmbeddingStatus,
  fetchDocuments,
  extractKnowledgeFromDocument,
  verifyKnowledgeNode,
  fetchKnowledgeNodes,
  fetchKnowledgeGraph,
  queryKnowledgeAssistant,
  fetchProjects,
} from '../services/api'
import {
  Network,
  Search,
  Filter,
  Layers,
  User,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Edit3,
  Quote,
  FileText,
  ShieldAlert,
  Cpu,
  Bot,
  Send,
  HelpCircle,
  Clock,
  ArrowRight,
  Database,
} from 'lucide-react'

interface KnowledgeViewProps {
  nodes: KnowledgeNode[]
  onRefreshNodes?: () => void
  projectId?: string
}

type SubTab = 'graph' | 'assistant' | 'cards'

export const KnowledgeView: React.FC<KnowledgeViewProps> = ({ nodes: initialNodes, onRefreshNodes, projectId }) => {
  // Navigation sub-tabs
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('graph')

  // Nodes list state
  const [nodes, setNodes] = useState<KnowledgeNode[]>(initialNodes)
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')

  // Persona switcher
  const [userRole, setUserRole] = useState<'manager' | 'engineer'>('manager')
  const [actorName, setActorName] = useState('Sarah Connor (Engineering Director)')

  // Provider Statuses
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null)
  const [embStatus, setEmbStatus] = useState<EmbeddingStatus | null>(null)

  // Document extraction modal
  const [showExtractModal, setShowExtractModal] = useState(false)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [selectedDocId, setSelectedDocId] = useState<string>('')
  const [extracting, setExtracting] = useState(false)
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null)

  // Verification modal states
  const [modifyingNode, setModifyingNode] = useState<KnowledgeNode | null>(null)
  const [modLabel, setModLabel] = useState('')
  const [modDetails, setModDetails] = useState('')
  const [modNotes, setModNotes] = useState('')
  const [rejectingNode, setRejectingNode] = useState<KnowledgeNode | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [verifyingId, setVerifyingId] = useState<string | null>(null)

  // ==========================================
  // Module 3: Organizational Memory Graph State
  // ==========================================
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [graphLoading, setGraphLoading] = useState(true)
  const [graphError, setGraphError] = useState<string | null>(null)
  const [graphProjectFilter, setGraphProjectFilter] = useState<string>(projectId || 'all')
  const [availableProjects, setAvailableProjects] = useState<Array<{ id: string; name: string }>>([])
  const [selectedGraphNode, setSelectedGraphNode] = useState<GraphNode | null>(null)

  // ==========================================
  // Module 4: AI Knowledge Assistant State
  // ==========================================
  const [assistantProject, setAssistantProject] = useState<string>(projectId || '')
  const [assistantQuery, setAssistantQuery] = useState('')
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantResponse, setAssistantResponse] = useState<KnowledgeQueryResponse | null>(null)
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0.65)

  useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes])

  useEffect(() => {
    let cancelled = false
    fetchProjects().then((projects) => {
      if (cancelled) return
      const choices = projects.map(({ id, name }) => ({ id, name }))
      setAvailableProjects(choices)
      const target = projectId && choices.some((p) => p.id === projectId) ? projectId : 'all'
      setGraphProjectFilter(target)
      setAssistantProject(projectId && choices.some((p) => p.id === projectId) ? projectId : choices[0]?.id || '')
    }).catch(() => { if (!cancelled) setAvailableProjects([]) })
    return () => { cancelled = true }
  }, [projectId])

  useEffect(() => {
    if (activeSubTab === 'assistant') loadProvidersStatus()
  }, [activeSubTab])

  useEffect(() => {
    if (!graphProjectFilter) return
    void loadGraph()
  }, [graphProjectFilter])

  useEffect(() => {
    if (projectId) {
      setGraphProjectFilter(projectId)
      setAssistantProject(projectId)
    }
  }, [projectId])

  const loadProvidersStatus = async () => {
    try {
      const [lStatus, eStatus] = await Promise.all([
        fetchLLMStatus().catch(() => null),
        fetchEmbeddingStatus().catch(() => null),
      ])
      if (lStatus) setLlmStatus(lStatus)
      if (eStatus) setEmbStatus(eStatus)
    } catch (err) {
      console.warn('Failed loading provider statuses:', err)
    }
  }

  const loadGraph = async () => {
    setGraphLoading(true)
    setGraphError(null)
    try {
      const data = await fetchKnowledgeGraph(graphProjectFilter)
      setGraphData(data)
      setSelectedGraphNode((selected) => data.nodes.find((node) => node.id === selected?.id) || data.nodes[0] || null)
    } catch (err) {
      console.error('Failed to load knowledge graph', err)
      setGraphError(err instanceof Error ? err.message : 'Failed to load the knowledge graph.')
    } finally {
      setGraphLoading(false)
    }
  }

  const handleOpenExtractModal = async () => {
    setShowExtractModal(true)
    setDocsLoading(true)
    try {
      const docs = await fetchDocuments()
      setDocuments(docs)
      if (docs.length > 0) {
        setSelectedDocId(docs[0].id)
      }
    } catch (err) {
      console.error('Failed to load documents for extraction', err)
    } finally {
      setDocsLoading(false)
    }
  }

  const handleTriggerExtraction = async () => {
    if (!selectedDocId) return
    setExtracting(true)
    setFeedbackMsg({ type: 'info', text: 'Analyzing document chunks and extracting structured knowledge records...' })
    try {
      const extracted = await extractKnowledgeFromDocument(selectedDocId, actorName)
      setFeedbackMsg({
        type: 'success',
        text: `Extracted ${extracted.length} grounded knowledge item(s) with source citations.`
      })
      setShowExtractModal(false)
      loadGraph()
      if (onRefreshNodes) {
        onRefreshNodes()
      } else {
        const refreshed = await fetchKnowledgeNodes()
        setNodes(refreshed)
      }
    } catch (err: any) {
      setFeedbackMsg({
        type: 'error',
        text: err.message || 'Knowledge extraction failed'
      })
    } finally {
      setExtracting(false)
    }
  }

  const handleVerify = async (node: KnowledgeNode) => {
    setVerifyingId(node.id)
    try {
      const updated = await verifyKnowledgeNode(node.id, {
        action: 'verified',
        reviewer_name: actorName,
        notes: 'Verified directly by manager after inspecting source grounding.'
      })
      setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)))
      setFeedbackMsg({ type: 'success', text: `Node "${node.label}" marked as verified.` })
      loadGraph()
      if (onRefreshNodes) onRefreshNodes()
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err.message || 'Verification failed.' })
    } finally {
      setVerifyingId(null)
    }
  }

  const handleOpenModifyModal = (node: KnowledgeNode) => {
    setModifyingNode(node)
    setModLabel(node.label)
    setModDetails(node.details)
    setModNotes('')
  }

  const handleSaveModification = async () => {
    if (!modifyingNode) return
    setVerifyingId(modifyingNode.id)
    try {
      const updated = await verifyKnowledgeNode(modifyingNode.id, {
        action: 'modified',
        reviewer_name: actorName,
        notes: modNotes || 'Refined during manager review.',
        modified_label: modLabel,
        modified_details: modDetails
      })
      setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)))
      setFeedbackMsg({ type: 'success', text: `Node "${updated.label}" updated and verified.` })
      setModifyingNode(null)
      loadGraph()
      if (onRefreshNodes) onRefreshNodes()
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err.message || 'Modification failed.' })
    } finally {
      setVerifyingId(null)
    }
  }

  const handleOpenRejectModal = (node: KnowledgeNode) => {
    setRejectingNode(node)
    setRejectReason('')
  }

  const handleConfirmRejection = async () => {
    if (!rejectingNode) return
    setVerifyingId(rejectingNode.id)
    try {
      const updated = await verifyKnowledgeNode(rejectingNode.id, {
        action: 'rejected',
        reviewer_name: actorName,
        notes: rejectReason || 'Factually inaccurate or irrelevant to core handoff.'
      })
      setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)))
      setFeedbackMsg({ type: 'info', text: `Node "${rejectingNode.label}" rejected.` })
      setRejectingNode(null)
      loadGraph()
      if (onRefreshNodes) onRefreshNodes()
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err.message || 'Rejection failed.' })
    } finally {
      setVerifyingId(null)
    }
  }

  // ==========================================
  // RAG Assistant Query Handler
  // ==========================================
  const handleAssistantSubmit = async (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault()
    const q = customQuery || assistantQuery
    if (!q.trim()) return
    if (!assistantProject) {
      setFeedbackMsg({ type: 'error', text: 'Select an authorized project before asking a question.' })
      return
    }

    setAssistantLoading(true)
    setAssistantResponse(null)
    try {
      const res = await queryKnowledgeAssistant({
        project_id: assistantProject,
        query: q.trim(),
        similarity_threshold: similarityThreshold,
        top_k: 4,
      })
      setAssistantResponse(res)
    } catch (err: any) {
      setFeedbackMsg({
        type: 'error',
        text: err.message || 'Assistant query failed'
      })
    } finally {
      setAssistantLoading(false)
    }
  }

  const filteredNodes = nodes.filter((n) => {
    const matchesCategory = categoryFilter === 'all' || n.category === categoryFilter
    const matchesStatus =
      statusFilter === 'all'
        ? true
        : statusFilter === 'flagged'
        ? n.is_flagged_for_review || (n.confidence ?? n.confidence_score ?? 1.0) < 0.65
        : (n.verification_status || 'unverified') === statusFilter
    const matchesSearch =
      n.label.toLowerCase().includes(search.toLowerCase()) ||
      n.details.toLowerCase().includes(search.toLowerCase()) ||
      (n.owner && n.owner.toLowerCase().includes(search.toLowerCase())) ||
      (n.source_quote && n.source_quote.toLowerCase().includes(search.toLowerCase()))
    return matchesCategory && matchesStatus && matchesSearch
  })

  const getNodeColor = (nodeType: string) => {
    switch (nodeType.toLowerCase()) {
      case 'decision':
      case 'architecture':
        return '#818cf8' // Indigo/Purple
      case 'task':
        return '#38bdf8' // Blue
      case 'document':
        return '#34d399' // Emerald
      case 'blocker':
        return '#f87171' // Red
      case 'dependency':
        return '#fbbf24' // Amber
      case 'owner':
        return '#22d3ee' // Cyan
      case 'module':
        return '#c084fc' // Violet
      default:
        return '#94a3b8' // Slate
    }
  }

  // Helper for computing node coordinates inside SVG
  const getNodePosition = (index: number, total: number) => {
    const radius = Math.min(220, 90 + total * 18)
    const angle = (index / total) * 2 * Math.PI
    const cx = 350
    const cy = 250
    return {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    }
  }

  return (
    <div className="section-container">
      {/* Platform Header with Provider Badges and Persona Switcher */}
      <div className="section-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2>Institutional Memory & AI Knowledge Engine</h2>
            {llmStatus && (
              <span
                className={`llm-indicator-pill ${llmStatus.configured ? 'live' : 'mock'}`}
                title={llmStatus.message}
              >
                <Cpu size={12} />
                <span>
                  LLM: {llmStatus.provider.toUpperCase()}{' '}
                  {llmStatus.configured ? `(${llmStatus.model})` : '[Safe Deterministic Fallback]'}
                </span>
              </span>
            )}
            {embStatus && (
              <span
                className="llm-indicator-pill mock"
                style={{ background: 'rgba(52, 211, 153, 0.1)', borderColor: 'rgba(52, 211, 153, 0.3)', color: '#34d399' }}
                title={embStatus.message}
              >
                <Database size={12} />
                <span>Vector: {embStatus.dimension}D Dense</span>
              </span>
            )}
          </div>
          <p className="section-desc">
            Connects extracted architecture decisions, documents, tasks, and attested maintainers into a relational graph and grounded AI assistant.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {/* Persona selector */}
          <div className="role-switcher" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: '#f8fafc', padding: '0.35rem 0.75rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            <User size={15} color="#475569" />
            <select
              value={userRole}
              onChange={(e) => {
                const role = e.target.value as 'manager' | 'engineer'
                setUserRole(role)
                setActorName(role === 'manager' ? 'Sarah Connor (Engineering Director)' : 'Alex Chen (Staff Engineer)')
              }}
              style={{ border: 'none', background: 'transparent', fontWeight: 600, color: '#1e293b', fontSize: '0.85rem' }}
            >
              <option value="manager">Reviewing Manager (Sarah Connor)</option>
              <option value="engineer">Viewing Engineer (Alex Chen)</option>
            </select>
          </div>

          <button
            className="btn btn-primary"
            onClick={handleOpenExtractModal}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
          >
            <Sparkles size={16} />
            <span>Extract from Document</span>
          </button>
        </div>
      </div>

      {feedbackMsg && (
        <div
          className={`alert-banner ${
            feedbackMsg.type === 'success' ? 'alert-success' : feedbackMsg.type === 'error' ? 'alert-error' : 'alert-info'
          }`}
          style={{ marginBottom: '1.25rem' }}
        >
          <span>{feedbackMsg.text}</span>
          <button
            onClick={() => setFeedbackMsg(null)}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', marginLeft: 'auto', fontWeight: 'bold' }}
          >
            &times;
          </button>
        </div>
      )}

      {/* Sub-Tabs: Graph vs Assistant vs Cards */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <div className="view-subtabs">
          <button
            className={`subtab-btn ${activeSubTab === 'graph' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('graph')}
          >
            <Network size={15} />
            <span>Memory Graph Explorer (Module 3)</span>
          </button>
          <button
            className={`subtab-btn ${activeSubTab === 'assistant' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('assistant')}
          >
            <Bot size={15} />
            <span>AI Knowledge Assistant (Module 4)</span>
          </button>
          <button
            className={`subtab-btn ${activeSubTab === 'cards' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('cards')}
          >
            <Layers size={15} />
            <span>Knowledge Verification Cards (Module 2)</span>
          </button>
        </div>

        {activeSubTab === 'graph' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.82rem', color: '#64748b', fontWeight: 600 }}>Scope:</span>
            <select
              value={graphProjectFilter}
              onChange={(e) => setGraphProjectFilter(e.target.value)}
              disabled={Boolean(projectId)}
              className="form-control"
              style={{ fontSize: '0.82rem', padding: '0.35rem 0.65rem' }}
            >
              {projectId ? <option value={projectId}>{graphData?.project_name || 'Selected Project'}</option> : <>
                <option value="all">All Projects (Authorized)</option>
                {availableProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </>}
            </select>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* SUB-TAB 1: ORGANIZATIONAL MEMORY GRAPH EXPLORER (MODULE 3) */}
      {/* ========================================================================= */}
      {activeSubTab === 'graph' && (
        <div className="graph-container">
          {/* Main Visual SVG Graph Canvas */}
          <div className="graph-canvas-wrapper">
            <div className="graph-canvas-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <Network size={16} color="#6366f1" />
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>
                  {graphData?.project_name || 'Loading Graph...'}
                </span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  ({graphData?.total_nodes || 0} nodes, {graphData?.total_edges || 0} grounded edges)
                </span>
              </div>

              {/* Node Type Legend */}
              <div className="graph-legend">
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#818cf8' }} />
                  <span>Decisions</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#34d399' }} />
                  <span>Docs</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#38bdf8' }} />
                  <span>Tasks</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#22d3ee' }} />
                  <span>Owners</span>
                </div>
              </div>
            </div>

            {graphLoading ? (
              <div style={{ minHeight: '480px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '0.75rem' }}>
                <span className="spinner" />
                <span style={{ color: '#64748b', fontSize: '0.85rem' }}>Loading project intelligence network...</span>
              </div>
            ) : graphError ? (
              <div style={{ minHeight: '480px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', padding: '2rem', gap: '0.75rem' }}>
                <p className="error-banner" role="alert">{graphError}</p>
                <button className="secondary-btn" onClick={() => void loadGraph()}>Retry graph</button>
              </div>
            ) : !graphData || graphData.nodes.length === 0 ? (
              <div style={{ minHeight: '480px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', padding: '2rem' }}>
                <Network size={40} color="#94a3b8" style={{ marginBottom: '1rem' }} />
                <h4>No Graph Entities in Selected Scope</h4>
                <p style={{ color: '#64748b', fontSize: '0.82rem' }}>
                  Upload documents or extract knowledge nodes to generate relational edges.
                </p>
              </div>
            ) : (
              <svg className="graph-svg-area" viewBox="0 0 700 500">
                <defs>
                  <marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
                  </marker>
                  <marker id="arrow-selected" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#818cf8" />
                  </marker>
                </defs>

                {/* Render Edges */}
                {(() => {
                  const nodePosMap = new Map<string, { x: number; y: number }>()
                  graphData.nodes.forEach((n, idx) => {
                    nodePosMap.set(n.id, getNodePosition(idx, graphData.nodes.length))
                  })

                  return graphData.edges.map((edge) => {
                    const srcPos = nodePosMap.get(edge.source)
                    const tgtPos = nodePosMap.get(edge.target)
                    if (!srcPos || !tgtPos) return null

                    const isConnected = selectedGraphNode && (edge.source === selectedGraphNode.id || edge.target === selectedGraphNode.id)
                    const strokeColor = isConnected ? '#818cf8' : 'rgba(148, 163, 184, 0.35)'
                    const strokeWidth = isConnected ? 2.5 : 1.2

                    // Midpoint for relationship label
                    const midX = (srcPos.x + tgtPos.x) / 2
                    const midY = (srcPos.y + tgtPos.y) / 2

                    return (
                      <g key={edge.id}>
                        <line
                          x1={srcPos.x}
                          y1={srcPos.y}
                          x2={tgtPos.x}
                          y2={tgtPos.y}
                          stroke={strokeColor}
                          strokeWidth={strokeWidth}
                          markerEnd={isConnected ? 'url(#arrow-selected)' : 'url(#arrow)'}
                          strokeDasharray={edge.relation_type === 'DEPENDS_ON' ? '4 2' : undefined}
                        />
                        {isConnected && (
                          <text
                            x={midX}
                            y={midY - 4}
                            fill="#c7d2fe"
                            fontSize="9"
                            fontWeight="600"
                            textAnchor="middle"
                            style={{ background: 'rgba(0,0,0,0.8)' }}
                          >
                            {edge.relation_type}
                          </text>
                        )}
                      </g>
                    )
                  })
                })()}

                {/* Render Nodes */}
                {graphData.nodes.map((node, idx) => {
                  const pos = getNodePosition(idx, graphData.nodes.length)
                  const isSelected = selectedGraphNode?.id === node.id
                  const nodeColor = getNodeColor(node.node_type)

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${pos.x}, ${pos.y})`}
                      onClick={() => setSelectedGraphNode(node)}
                      style={{ cursor: 'pointer' }}
                    >
                      {/* Selection Glow Ring */}
                      {isSelected && (
                        <circle
                          r="26"
                          fill="none"
                          stroke="#6366f1"
                          strokeWidth="2.5"
                          strokeDasharray="4 2"
                        />
                      )}

                      {/* Main Node Circle */}
                      <circle
                        r="18"
                        fill={nodeColor}
                        stroke={isSelected ? '#ffffff' : 'rgba(255,255,255,0.4)'}
                        strokeWidth={isSelected ? 2 : 1}
                        style={{ filter: isSelected ? 'drop-shadow(0 0 8px rgba(99, 102, 241, 0.6))' : undefined }}
                      />

                      {/* Verification Status Small Indicator */}
                      {node.verification_status === 'verified' && (
                        <circle cx="12" cy="-12" r="5" fill="#10b981" stroke="#ffffff" strokeWidth="1" />
                      )}
                      {node.verification_status === 'unverified' && (
                        <circle cx="12" cy="-12" r="5" fill="#f59e0b" stroke="#ffffff" strokeWidth="1" />
                      )}

                      {/* Label Text */}
                      <text
                        y="32"
                        fill={isSelected ? '#ffffff' : '#cbd5e1'}
                        fontSize="10"
                        fontWeight={isSelected ? '700' : '500'}
                        textAnchor="middle"
                        style={{ pointerEvents: 'none' }}
                      >
                        {node.label.length > 20 ? `${node.label.slice(0, 18)}...` : node.label}
                      </text>
                    </g>
                  )
                })}
              </svg>
            )}
          </div>

          {/* Graph Inspector Sidebar */}
          <div className="graph-inspector-panel">
            <div className="inspector-header">
              <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f1f5f9' }}>
                Entity Inspector
              </span>
              {selectedGraphNode && (
                <span
                  className={`verification-status-tag ${selectedGraphNode.verification_status || 'unverified'}`}
                  style={{ fontSize: '0.68rem' }}
                >
                  {selectedGraphNode.verification_status?.toUpperCase() || 'UNVERIFIED'}
                </span>
              )}
            </div>

            {selectedGraphNode ? (
              <>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
                    <span
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        backgroundColor: getNodeColor(selectedGraphNode.node_type)
                      }}
                    />
                    <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 700, color: '#94a3b8' }}>
                      {selectedGraphNode.node_type} &bull; {selectedGraphNode.category || 'General'}
                    </span>
                  </div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#f8fafc', margin: '0 0 0.5rem' }}>
                    {selectedGraphNode.label}
                  </h3>
                  <p style={{ fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.5, margin: 0 }}>
                    {selectedGraphNode.details || 'No detailed description available.'}
                  </p>
                </div>

                {selectedGraphNode.owner && (
                  <div className="inspector-section">
                    <h4>Assigned Maintainer</h4>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', color: '#e2e8f0' }}>
                      <User size={14} color="#38bdf8" />
                      <span>{selectedGraphNode.owner}</span>
                    </div>
                  </div>
                )}

                {selectedGraphNode.source_quote && (
                  <div className="inspector-section">
                    <h4>Verbatim Source Grounding</h4>
                    <div style={{ background: 'rgba(0,0,0,0.25)', borderLeft: '3px solid #6366f1', padding: '0.5rem 0.65rem', borderRadius: '0 4px 4px 0' }}>
                      <p style={{ fontSize: '0.76rem', fontStyle: 'italic', color: '#cbd5e1', margin: 0, lineHeight: 1.4 }}>
                        "{selectedGraphNode.source_quote}"
                      </p>
                    </div>
                  </div>
                )}

                {/* Connected Relationships List */}
                <div className="inspector-section">
                  <h4>Active Graph Relationships</h4>
                  {(() => {
                    const connectedEdges = (graphData?.edges || []).filter(
                      (e) => e.source === selectedGraphNode.id || e.target === selectedGraphNode.id
                    )

                    if (connectedEdges.length === 0) {
                      return <span style={{ fontSize: '0.78rem', color: '#64748b' }}>No direct connections found.</span>
                    }

                    return (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                        {connectedEdges.map((e) => {
                          const isSource = e.source === selectedGraphNode.id
                          const otherNodeId = isSource ? e.target : e.source
                          const otherNode = graphData?.nodes.find((n) => n.id === otherNodeId)
                          const otherLabel = otherNode?.label || otherNodeId

                          let relClass = 'depends-on'
                          if (e.relation_type === 'DOCUMENTED_IN') relClass = 'documented-in'
                          if (e.relation_type === 'MAINTAINS') relClass = 'maintains'
                          if (e.relation_type === 'BLOCKED_BY') relClass = 'blocked-by'

                          return (
                            <div
                              key={e.id}
                              className="connection-item"
                              onClick={() => otherNode && setSelectedGraphNode(otherNode)}
                              style={{ cursor: otherNode ? 'pointer' : 'default' }}
                              title="Click to focus connected entity"
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                <ArrowRight size={11} color="#94a3b8" />
                                <span style={{ color: '#f1f5f9', fontWeight: 500 }}>
                                  {otherLabel.length > 20 ? `${otherLabel.slice(0, 18)}...` : otherLabel}
                                </span>
                              </div>
                              <span className={`rel-badge ${relClass}`}>{e.relation_type}</span>
                            </div>
                          )
                        })}
                      </div>
                    )
                  })()}
                </div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '2rem 1rem', color: '#64748b' }}>
                <HelpCircle size={28} style={{ marginBottom: '0.5rem' }} />
                <p style={{ fontSize: '0.82rem', margin: 0 }}>Select any node in the graph to view its source evidence and dependency trail.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUB-TAB 2: AI KNOWLEDGE ASSISTANT (MODULE 4) */}
      {/* ========================================================================= */}
      {activeSubTab === 'assistant' && (
        <div className="assistant-container">
          <div className="assistant-search-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Bot size={20} color="#6366f1" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#f8fafc' }}>
                  Ask Synora AI Knowledge Assistant
                </h3>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Min Similarity:</span>
                  <input
                    type="range"
                    min="0.50"
                    max="0.90"
                    step="0.05"
                    value={similarityThreshold}
                    onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                    style={{ width: '80px', accentColor: '#6366f1' }}
                    title={`Cosine threshold: ${(similarityThreshold * 100).toFixed(0)}%`}
                  />
                  <span style={{ fontSize: '0.75rem', color: '#c7d2fe', fontWeight: 600 }}>
                    {(similarityThreshold * 100).toFixed(0)}%
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Target Project:</span>
                  <select
                    value={assistantProject}
                    onChange={(e) => setAssistantProject(e.target.value)}
                    disabled={Boolean(projectId)}
                    className="form-control"
                    style={{ fontSize: '0.82rem', padding: '0.3rem 0.6rem' }}
                  >
                    {projectId ? <option value={projectId}>{availableProjects.find((p) => p.id === projectId)?.name || 'Selected Project'}</option> : availableProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                  </select>
                </div>
              </div>
            </div>

            <form onSubmit={handleAssistantSubmit} className="assistant-input-row">
              <input
                type="text"
                className="assistant-input"
                placeholder="Ask any technical, architecture, or operational handover question..."
                value={assistantQuery}
                onChange={(e) => setAssistantQuery(e.target.value)}
                disabled={assistantLoading}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={assistantLoading || !assistantQuery.trim()}
                style={{ padding: '0.85rem 1.4rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}
              >
                {assistantLoading ? (
                  <span className="spinner" style={{ width: '16px', height: '16px' }} />
                ) : (
                  <>
                    <Send size={15} />
                    <span>Query</span>
                  </>
                )}
              </button>
            </form>

            {/* Quick Sample Prompts */}
            {!projectId && <div className="sample-queries">
              <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Suggested Queries:</span>
              <button
                type="button"
                className="sample-chip"
                onClick={() => {
                  setAssistantQuery('What is the Raft consensus heartbeat interval?')
                  handleAssistantSubmit(undefined, 'What is the Raft consensus heartbeat interval?')
                }}
              >
                Raft Heartbeat & Election Timeout
              </button>
              <button
                type="button"
                className="sample-chip"
                onClick={() => {
                  setAssistantQuery('How do we recover from a network partition in Payments?')
                  handleAssistantSubmit(undefined, 'How do we recover from a network partition in Payments?')
                }}
              >
                Quorum Recovery Runbook
              </button>
              <button
                type="button"
                className="sample-chip"
                onClick={() => {
                  setAssistantQuery('What are the quantum cryptographic teleportation codes?')
                  handleAssistantSubmit(undefined, 'What are the quantum cryptographic teleportation codes?')
                }}
              >
                Uncertainty Check (No Evidence Test)
              </button>
            </div>}
          </div>

          {/* Assistant Answer Card */}
          {assistantResponse && (
            <div className="assistant-response-card">
              <div className="response-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                  <span
                    className={`grounded-badge ${
                      !assistantResponse.is_grounded
                        ? 'uncertain'
                        : assistantResponse.has_verified_knowledge
                        ? 'verified'
                        : 'unverified'
                    }`}
                  >
                    {!assistantResponse.is_grounded ? (
                      <>
                        <ShieldAlert size={12} />
                        <span>Uncertainty Declared</span>
                      </>
                    ) : assistantResponse.has_verified_knowledge ? (
                      <>
                        <CheckCircle2 size={12} />
                        <span>Grounded in Verified Project Docs</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle size={12} />
                        <span>Grounded (Unverified Extraction)</span>
                      </>
                    )}
                  </span>
                  <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                    Confidence: {(assistantResponse.confidence * 100).toFixed(0)}%
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.75rem', color: '#64748b' }}>
                  <Clock size={12} />
                  <span>Latency: {assistantResponse.processing_time_ms} ms</span>
                </div>
              </div>

              {assistantResponse.uncertainty_warning && (
                <div style={{ background: 'rgba(239, 68, 68, 0.08)', borderLeft: '3px solid #ef4444', padding: '0.65rem 0.85rem', borderRadius: '0 4px 4px 0', fontSize: '0.82rem', color: '#fca5a5' }}>
                  {assistantResponse.uncertainty_warning}
                </div>
              )}

              {/* Synthesized Answer Text */}
              <div className="response-body">
                {assistantResponse.answer}
              </div>

              {/* Structured Source Citations */}
              {assistantResponse.citations.length > 0 && (
                <div className="citations-block">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>
                    <Quote size={13} color="#6366f1" />
                    <span>Verifiable Source Citations ({assistantResponse.citations.length})</span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                    {assistantResponse.citations.map((cit, idx) => (
                      <div key={idx} className="citation-card">
                        <div className="citation-meta">
                          <span style={{ fontWeight: 600, color: '#f1f5f9' }}>
                            [Doc: {cit.document_name} &bull; Chunk #{cit.chunk_index}]
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span className={`verification-status-tag ${cit.verification_status}`}>
                              {cit.verification_status}
                            </span>
                            <span style={{ color: '#818cf8', fontWeight: 600 }}>
                              {(cit.similarity_score * 100).toFixed(0)}% Similarity
                            </span>
                          </div>
                        </div>
                        <p className="citation-snippet">
                          "{cit.snippet}"
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUB-TAB 3: KNOWLEDGE VERIFICATION CARDS (MODULE 2) */}
      {/* ========================================================================= */}
      {activeSubTab === 'cards' && (
        <>
          {/* Toolbar / Filters */}
          <div className="toolbar" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
            <div className="search-box">
              <Search size={16} />
              <input
                type="text"
                placeholder="Search knowledge nodes, source quotes, owners..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="filter-group">
              <Filter size={16} />
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <option value="all">All Categories</option>
                <option value="task">Tasks & Deliverables</option>
                <option value="architecture">Architecture Decisions</option>
                <option value="blocker">Blockers & Risks</option>
                <option value="config">Technical Config</option>
                <option value="module">Modules</option>
                <option value="process">Processes</option>
                <option value="tooling">Tooling</option>
              </select>
            </div>

            <div className="filter-group">
              <ShieldAlert size={16} />
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="all">All Verification Statuses</option>
                <option value="flagged">Needs Review / Low Confidence (&lt;65%)</option>
                <option value="unverified">Unverified</option>
                <option value="verified">Verified</option>
                <option value="modified">Modified & Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
          </div>

          {/* Grid of Knowledge Cards */}
          <div className="knowledge-grid">
            {filteredNodes.length === 0 ? (
              <div className="empty-state" style={{ gridColumn: '1 / -1', padding: '3rem', textAlign: 'center' }}>
                <FileText size={48} color="#94a3b8" style={{ marginBottom: '1rem' }} />
                <h3>No Knowledge Nodes Match Your Filters</h3>
                <p style={{ color: '#64748b', maxWidth: '480px', margin: '0 auto 1.5rem' }}>
                  Upload handoff documents or run knowledge extraction to populate institutional knowledge with grounded source citations.
                </p>
                <button className="btn btn-secondary" onClick={handleOpenExtractModal}>
                  <Sparkles size={15} style={{ marginRight: '0.35rem' }} />
                  Extract from Document
                </button>
              </div>
            ) : (
              filteredNodes.map((node) => {
                const conf = node.confidence ?? node.confidence_score ?? 1.0
                const isLowConf = conf < 0.65 || node.is_flagged_for_review
                const confLevel = conf >= 0.85 ? 'high' : conf >= 0.65 ? 'med' : 'low'

                return (
                  <div
                    key={node.id}
                    className={`knowledge-card ${isLowConf ? 'flagged-card' : ''}`}
                    style={{
                      border: isLowConf ? '1px solid #f59e0b' : '1px solid var(--border-color)',
                      boxShadow: isLowConf ? '0 0 0 1px rgba(245, 158, 11, 0.15)' : undefined
                    }}
                  >
                    {/* Card Top: Category and Verification Tag */}
                    <div className="card-top" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span className="cat-icon" style={{ display: 'flex', alignItems: 'center', color: '#818cf8' }}>
                          <Layers size={16} />
                        </span>
                        <span className="cat-tag" style={{ textTransform: 'capitalize', fontWeight: 600, fontSize: '0.75rem', background: 'rgba(99, 102, 241, 0.15)', color: '#c7d2fe', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                          {node.category}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        {(() => {
                          const vStatus = node.verification_status || 'unverified'
                          return (
                            <span className={`verification-status-tag ${vStatus}`}>
                              {vStatus === 'verified' && <CheckCircle2 size={12} />}
                              {vStatus === 'modified' && <Edit3 size={12} />}
                              {vStatus === 'rejected' && <XCircle size={12} />}
                              {vStatus === 'unverified' && <AlertTriangle size={12} />}
                              <span>{vStatus.toUpperCase()}</span>
                            </span>
                          )
                        })()}

                        <span
                          className={`confidence-pill ${confLevel}`}
                          title={isLowConf ? 'Confidence under 65%: Flagged for human verification' : `Confidence: ${(conf * 100).toFixed(0)}%`}
                        >
                          {isLowConf && <AlertTriangle size={11} />}
                          {(conf * 100).toFixed(0)}% Conf
                        </span>
                      </div>
                    </div>

                    <h3 style={{ fontSize: '1.02rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
                      {node.label}
                    </h3>
                    <p style={{ fontSize: '0.85rem', color: '#94a3b8', lineHeight: 1.5, marginBottom: '0.85rem' }}>
                      {node.details}
                    </p>

                    {node.source_quote && (
                      <div className="source-citation-box" style={{ background: 'rgba(0,0,0,0.25)', borderLeft: '3px solid #6366f1', padding: '0.6rem 0.75rem', borderRadius: '0 6px 6px 0', marginBottom: '0.85rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.72rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                          <Quote size={12} color="#818cf8" />
                          <span>Verbatim Grounding Source</span>
                          {node.document_id && <span style={{ marginLeft: 'auto', fontFamily: 'monospace' }}>Doc: {node.document_id.slice(0, 8)}...</span>}
                        </div>
                        <p className="citation-quote" style={{ fontSize: '0.8rem', fontStyle: 'italic', color: '#cbd5e1', margin: 0, lineHeight: 1.4 }}>
                          "{node.source_quote}"
                        </p>
                      </div>
                    )}

                    <div className="card-footer" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div className="owner" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', color: '#94a3b8' }}>
                        <User size={13} />
                        <span>Owner: {node.owner || 'Unassigned'}</span>
                      </div>

                      {userRole === 'manager' && (
                        <div className="verification-actions" style={{ display: 'flex', gap: '0.35rem' }}>
                          {node.verification_status !== 'verified' && (
                            <button
                              className="btn-tiny btn-verify"
                              disabled={verifyingId === node.id}
                              onClick={() => handleVerify(node)}
                              title="Verify as factually grounded"
                            >
                              <CheckCircle2 size={13} />
                              <span>Verify</span>
                            </button>
                          )}

                          <button
                            className="btn-tiny btn-modify"
                            disabled={verifyingId === node.id}
                            onClick={() => handleOpenModifyModal(node)}
                            title="Edit label or details before approving"
                          >
                            <Edit3 size={13} />
                            <span>Modify</span>
                          </button>

                          {node.verification_status !== 'rejected' && (
                            <button
                              className="btn-tiny btn-reject"
                              disabled={verifyingId === node.id}
                              onClick={() => handleOpenRejectModal(node)}
                              title="Reject extraction"
                            >
                              <XCircle size={13} />
                              <span>Reject</span>
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </>
      )}

      {/* Modal: Extract Knowledge from Document */}
      {showExtractModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '540px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Sparkles size={20} color="#6366f1" />
                <h3 style={{ margin: 0 }}>Extract Structured Knowledge</h3>
              </div>
              <button
                className="btn-close"
                onClick={() => !extracting && setShowExtractModal(false)}
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginBottom: '1.25rem' }}>
                Select an ingested document. Synora will analyze its chunks to extract architecture decisions, tasks, dependencies, and configs with verbatim citations.
              </p>

              {docsLoading ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <span className="spinner" />
                  <p style={{ color: '#94a3b8', marginTop: '0.5rem' }}>Loading ingested documents...</p>
                </div>
              ) : documents.length === 0 ? (
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1.5rem', borderRadius: '8px', textAlign: 'center', border: '1px dashed var(--border-color)' }}>
                  <FileText size={32} color="#94a3b8" style={{ marginBottom: '0.5rem' }} />
                  <p style={{ color: '#f8fafc', fontWeight: 600, margin: '0 0 0.5rem' }}>No Documents Available</p>
                  <p style={{ color: '#94a3b8', fontSize: '0.825rem', margin: 0 }}>
                    Please upload a handover document in the Handover Documents tab first.
                  </p>
                </div>
              ) : (
                <div className="form-group">
                  <label style={{ fontWeight: 600, fontSize: '0.85rem', color: '#f8fafc', marginBottom: '0.4rem', display: 'block' }}>
                    Select Source Document:
                  </label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '240px', overflowY: 'auto' }}>
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        onClick={() => setSelectedDocId(doc.id)}
                        className={`doc-select-card ${selectedDocId === doc.id ? 'selected' : ''}`}
                      >
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f8fafc' }}>{doc.filename}</div>
                          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                            Chunks: {doc.chunk_count} &bull; Type: {(doc.content_type || 'document').toUpperCase()} &bull; Status: {doc.processing_status}
                          </div>
                        </div>
                        {selectedDocId === doc.id && <CheckCircle2 size={18} color="#6366f1" />}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={extracting}
                onClick={() => setShowExtractModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={extracting || !selectedDocId || documents.length === 0}
                onClick={handleTriggerExtraction}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              >
                {extracting ? (
                  <>
                    <span className="spinner" style={{ width: '14px', height: '14px' }} />
                    <span>Extracting Knowledge...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    <span>Run Extraction</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Modify & Approve Node */}
      {modifyingNode && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '520px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Edit3 size={18} color="#6366f1" />
                <h3 style={{ margin: 0 }}>Modify & Verify Knowledge Item</h3>
              </div>
              <button className="btn-close" onClick={() => setModifyingNode(null)}>&times;</button>
            </div>

            <div className="modal-body">
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label style={{ fontWeight: 600, fontSize: '0.85rem' }}>Label / Headline:</label>
                <input
                  type="text"
                  className="form-control"
                  value={modLabel}
                  onChange={(e) => setModLabel(e.target.value)}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label style={{ fontWeight: 600, fontSize: '0.85rem' }}>Details / Description:</label>
                <textarea
                  className="form-control"
                  rows={3}
                  value={modDetails}
                  onChange={(e) => setModDetails(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label style={{ fontWeight: 600, fontSize: '0.85rem' }}>Reviewer Notes:</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Corrected technical wording per Q3 architecture spec"
                  value={modNotes}
                  onChange={(e) => setModNotes(e.target.value)}
                />
              </div>
            </div>

            <div className="modal-footer" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setModifyingNode(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSaveModification}
                disabled={!modLabel.trim()}
              >
                Save & Verify
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Reject Knowledge Node */}
      {rejectingNode && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <XCircle size={18} color="#ef4444" />
                <h3 style={{ margin: 0 }}>Reject Knowledge Item</h3>
              </div>
              <button className="btn-close" onClick={() => setRejectingNode(null)}>&times;</button>
            </div>

            <div className="modal-body">
              <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                Are you sure you want to reject <strong>"{rejectingNode.label}"</strong>? This will mark the extraction as rejected and record the audit rationale.
              </p>
              <div className="form-group">
                <label style={{ fontWeight: 600, fontSize: '0.85rem' }}>Rejection Rationale:</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Unsupported extrapolation or obsolete task"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
              </div>
            </div>

            <div className="modal-footer" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setRejectingNode(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleConfirmRejection}
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
