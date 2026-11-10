import React, { useState, useEffect, useMemo } from 'react'
import type {
  RiskAlert,
  SentinelOverview,
} from '../types'
import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  Flame,
  Check,
  X,
  FileText,
  AlertOctagon,
  Layers,
  ShieldCheck,
  Compass,
  FileQuestion,
  HelpCircle,
  RotateCcw,
} from 'lucide-react'
import {
  fetchSentinelOverview,
  fetchRisks,
  triggerSentinelScan,
  remediateSentinelRisk,
} from '../services/api'

interface SentinelViewProps {
  risks?: RiskAlert[]
  projectId?: string
}

export const SentinelView: React.FC<SentinelViewProps> = ({ projectId }) => {
  const [overview, setOverview] = useState<SentinelOverview | null>(null)
  const [findings, setFindings] = useState<RiskAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [scanningProjectId, setScanningProjectId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Filters
  const [selectedProject, setSelectedProject] = useState<string>('all')
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'resolved'>('active')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Action Modal State
  const [actionFinding, setActionFinding] = useState<RiskAlert | null>(null)
  const [actionType, setActionType] = useState<'resolve' | 'request_changes'>('resolve')
  const [managerName, setManagerName] = useState('Sarah Connor (Engineering Director)')
  const [managerNotes, setManagerNotes] = useState('')
  const [submittingAction, setSubmittingAction] = useState(false)

  // Formula Inspector Modal
  const [showFormulaModal, setShowFormulaModal] = useState(false)

  // Load initial Sentinel data
  const loadSentinelData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, findingsData] = await Promise.all([
        fetchSentinelOverview(),
        fetchRisks(),
      ])
      setOverview(overviewData)
      setFindings(findingsData)
    } catch (err: any) {
      console.error('Failed to load Sentinel intelligence', err)
      setError(err.message || 'Failed to load Sentinel integrity metrics.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSentinelData()
  }, [])

  useEffect(() => {
    if (projectId) setSelectedProject(projectId)
  }, [projectId])

  // Auto-dismiss notifications after 5s
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  // Trigger continuous Sentinel scan
  const handleScan = async (projectId?: string) => {
    if (projectId) {
      setScanningProjectId(projectId)
    } else {
      setScanning(true)
    }
    setError(null)
    try {
      const result = await triggerSentinelScan({
        project_id: projectId,
        actor_name: 'Sentinel Continuous Integrity Observer',
      })
      setSuccessMessage(
        result.message || `Sentinel scan complete. Active integrity score: ${result.integrity_score}%`
      )
      await loadSentinelData()
    } catch (err: any) {
      console.error('Scan failed', err)
      setError(err.message || 'Sentinel integrity scan failed.')
    } finally {
      setScanning(false)
      setScanningProjectId(null)
    }
  }

  // Handle remediation / change request submission
  const handleConfirmAction = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!actionFinding) return

    setSubmittingAction(true)
    try {
      const res = await remediateSentinelRisk(actionFinding.id, {
        action: actionType,
        actor_name: managerName,
        notes: managerNotes || (actionType === 'resolve' ? 'Verified in production.' : 'Handover revisions required.'),
      })

      setSuccessMessage(res.message || 'Finding updated successfully.')
      setActionFinding(null)
      setManagerNotes('')
      await loadSentinelData()
    } catch (err: any) {
      console.error('Action failed', err)
      setError(err.message || 'Failed to update finding.')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Filtered findings list
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      if (selectedProject !== 'all' && f.project_id !== selectedProject) return false
      if (selectedSeverity !== 'all' && f.risk_level.toLowerCase() !== selectedSeverity.toLowerCase()) return false
      if (selectedCategory !== 'all' && f.category !== selectedCategory) return false
      if (statusFilter === 'active' && f.is_resolved) return false
      if (statusFilter === 'resolved' && !f.is_resolved) return false
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchProject = (f.project_name || '').toLowerCase().includes(q)
        const matchCategory = (f.category || '').toLowerCase().includes(q)
        const matchDesc = (f.description || '').toLowerCase().includes(q)
        const matchRec = (f.recommended_action || '').toLowerCase().includes(q)
        if (!matchProject && !matchCategory && !matchDesc && !matchRec) return false
      }
      return true
    })
  }, [findings, selectedProject, selectedSeverity, selectedCategory, statusFilter, searchQuery])

  // Grade color utility
  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A':
        return '#10b981'
      case 'B':
        return '#3b82f6'
      case 'C':
        return '#f59e0b'
      case 'D':
        return '#f97316'
      default:
        return '#ef4444'
    }
  }

  // Severity styling
  const getSeverityBadgeClass = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'badge-critical'
      case 'high':
        return 'badge-high'
      case 'medium':
        return 'badge-medium'
      default:
        return 'badge-low'
    }
  }

  // Finding Type badge
  const getFindingTypePill = (finding: RiskAlert) => {
    const type = finding.finding_type || (
      finding.category.includes('CONTRADICTORY')
        ? 'suspected_inconsistency'
        : finding.category.includes('UNSUPPORTED') || finding.category.includes('MISSING')
        ? 'unverified_claim'
        : 'verified_fact'
    )

    if (type === 'verified_fact') {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-emerald-950/70 text-emerald-400 border border-emerald-800/50 flex items-center gap-1">
          <ShieldCheck size={11} /> Verified Fact
        </span>
      )
    }
    if (type === 'unverified_claim') {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-amber-950/70 text-amber-400 border border-amber-800/50 flex items-center gap-1">
          <FileQuestion size={11} /> Unverified Claim
        </span>
      )
    }
    return (
      <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-red-950/70 text-red-400 border border-red-800/50 flex items-center gap-1">
        <AlertTriangle size={11} /> Suspected Inconsistency
      </span>
    )
  }

  return (
    <div className="section-container">
      {/* Hero Header */}
      <div className="hero-banner">
        <div className="hero-content">
          <div className="flex items-center gap-2 mb-2">
            <span className="hero-badge flex items-center gap-1.5">
              <ShieldAlert size={14} className="text-red-400" />
              Module 7: Continuous Handover Integrity & SPOF Observer
            </span>
            <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-indigo-950/60 text-indigo-400 border border-indigo-800/40">
              Evidence-Driven Verification
            </span>
          </div>

          <h2 className="hero-title">Synora Sentinel</h2>
          <p className="hero-desc">
            Autonomous verification engine that detects unsupported completion claims, contradictory deliverable states,
            missing environment setup runbooks, broken technical references, and single maintainer concentration (Bus Factor $\le 1.0$).
            Ensures leaving employee dossiers are factually grounded before manager sign-off.
          </p>

          <div className="hero-actions">
            <button
              className="primary-btn flex items-center gap-2"
              onClick={() => handleScan()}
              disabled={scanning}
            >
              <RefreshCw size={16} className={scanning ? 'animate-spin' : ''} />
              <span>{scanning ? 'Running Sentinel Inspection...' : 'Trigger Integrity Scan'}</span>
            </button>

            <button
              className="secondary-btn flex items-center gap-2"
              onClick={() => setShowFormulaModal(true)}
            >
              <HelpCircle size={16} />
              <span>Integrity Scoring Rules</span>
            </button>
          </div>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-4 mb-6 rounded-lg bg-red-950/60 border border-red-800 text-red-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertOctagon size={18} className="text-red-400 shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <X size={16} />
          </button>
        </div>
      )}

      {successMessage && (
        <div className="p-4 mb-6 rounded-lg bg-emerald-950/60 border border-emerald-800 text-emerald-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
            <span className="text-sm">{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-400 hover:text-emerald-300">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Top Stat Tiles */}
      <div className="stats-grid mb-6">
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Platform Integrity Score</span>
            <div className="stat-icon-wrapper bg-indigo">
              <ShieldCheck size={20} />
            </div>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="stat-value text-3xl font-bold font-mono">
              {overview ? `${overview.average_integrity_score}%` : '--'}
            </div>
            {overview && (
              <span
                className="px-2 py-0.5 rounded text-xs font-bold font-mono border"
                style={{
                  color: getGradeColor(overview.overall_grade),
                  borderColor: getGradeColor(overview.overall_grade),
                  backgroundColor: `${getGradeColor(overview.overall_grade)}15`,
                }}
              >
                Grade {overview.overall_grade}
              </span>
            )}
          </div>
          <div className="stat-footer">
            <span className="stat-sub">Across {overview?.projects.length || 0} production repositories</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Critical Findings</span>
            <div className="stat-icon-wrapper bg-red">
              <Flame size={20} />
            </div>
          </div>
          <div className="stat-value text-3xl font-bold text-red-400 font-mono">
            {overview?.critical_findings ?? 0}
          </div>
          <div className="stat-footer">
            <span className="stat-sub text-red-400">Contradictions or missing documentation</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">High Severity Warnings</span>
            <div className="stat-icon-wrapper bg-amber">
              <AlertTriangle size={20} />
            </div>
          </div>
          <div className="stat-value text-3xl font-bold text-amber-400 font-mono">
            {overview?.high_findings ?? 0}
          </div>
          <div className="stat-footer">
            <span className="stat-sub text-amber-400">Unsupported task completion claims</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Verified Citations</span>
            <div className="stat-icon-wrapper bg-emerald">
              <CheckCircle2 size={20} />
            </div>
          </div>
          <div className="stat-value text-3xl font-bold text-emerald-400 font-mono">
            {overview?.verified_items_count ?? 0}
          </div>
          <div className="stat-footer">
            <span className="stat-sub text-emerald-400">Corroborated by uploaded docs</span>
          </div>
        </div>
      </div>

      {/* Project Integrity Matrix */}
      <div className="content-card mb-8">
        <div className="card-header flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers size={18} className="text-red-400" />
            <h3 className="card-title text-base font-semibold">Repository Handover Integrity & Bus Factor</h3>
          </div>
          <span className="text-xs text-slate-400">Continuous Observer Active</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-5">
          {overview?.projects.map((prj) => {
            const isScanningThis = scanningProjectId === prj.project_id
            const gradeColor = getGradeColor(prj.grade)

            return (
              <div
                key={prj.project_id}
                className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 hover:border-slate-700 transition flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h4 className="font-semibold text-slate-100 text-sm">{prj.project_name}</h4>
                      <span className="text-xs text-slate-400 font-mono">
                        {prj.handovers_count} Handover(s) on record
                      </span>
                    </div>
                    <span
                      className="px-2 py-0.5 rounded text-xs font-bold font-mono border"
                      style={{
                        color: gradeColor,
                        borderColor: gradeColor,
                        backgroundColor: `${gradeColor}15`,
                      }}
                    >
                      Grade {prj.grade}
                    </span>
                  </div>

                  {/* Integrity Meter */}
                  <div className="mb-3">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-400">Handover Integrity</span>
                      <span className="font-mono font-bold text-slate-200">
                        {prj.integrity_score}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div
                        className="h-full transition-all duration-500 rounded-full"
                        style={{
                          width: `${Math.max(4, prj.integrity_score)}%`,
                          backgroundColor: gradeColor,
                        }}
                      />
                    </div>
                  </div>

                  {/* Metrics */}
                  <div className="grid grid-cols-2 gap-2 text-xs mb-4">
                    <div className="p-2 rounded bg-slate-950/50 border border-slate-800/80">
                      <span className="text-slate-400 block text-[11px]">Bus Factor</span>
                      <span
                        className={`font-mono font-bold ${
                          prj.bus_factor <= 1.0 ? 'text-red-400' : 'text-emerald-400'
                        }`}
                      >
                        {prj.bus_factor.toFixed(1)} {prj.bus_factor <= 1.0 && '⚠️ SPOF'}
                      </span>
                    </div>
                    <div className="p-2 rounded bg-slate-950/50 border border-slate-800/80">
                      <span className="text-slate-400 block text-[11px]">Open Findings</span>
                      <span
                        className={`font-mono font-bold ${
                          prj.active_findings_count > 0 ? 'text-amber-400' : 'text-slate-400'
                        }`}
                      >
                        {prj.active_findings_count} ({prj.critical_count} crit)
                      </span>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-800/80">
                  <button
                    className="w-full text-xs py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition font-medium flex items-center justify-center gap-1.5"
                    onClick={() => handleScan(prj.project_id)}
                    disabled={isScanningThis}
                  >
                    <RefreshCw size={12} className={isScanningThis ? 'animate-spin' : ''} />
                    <span>{isScanningThis ? 'Inspecting...' : 'Audit Handover Integrity'}</span>
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Filter & Search Toolbar */}
      <div className="content-card mb-6">
        <div className="p-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search */}
            <div className="relative min-w-[220px]">
              <Search size={14} className="absolute left-3 top-3 text-slate-400" />
              <input
                type="text"
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-400 focus:outline-none focus:border-red-500"
                placeholder="Search findings, deliverables, or authors..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* Project Filter */}
            <select
              className="py-1.5 px-3 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:border-red-500"
              value={selectedProject}
              onChange={(e) => setSelectedProject(e.target.value)}
            >
              <option value="all">All Projects</option>
              {overview?.projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.project_name}
                </option>
              ))}
            </select>

            {/* Severity Filter */}
            <select
              className="py-1.5 px-3 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:border-red-500"
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>

            {/* Category Filter */}
            <select
              className="py-1.5 px-3 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:border-red-500"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              <option value="all">All Finding Categories</option>
              <option value="MISSING_DOCUMENTATION">Missing Documentation</option>
              <option value="INCOMPLETE_HANDOVER_SECTION">Incomplete Sections</option>
              <option value="BROKEN_OR_MISSING_REFERENCE">Broken References</option>
              <option value="UNSUPPORTED_COMPLETION_CLAIM">Unsupported Claims</option>
              <option value="CONTRADICTORY_HANDOVER_INFO">Contradictory Information</option>
              <option value="MISSING_ENVIRONMENT_SETUP">Missing Environment Setup</option>
              <option value="SPOF_RISK">Single Point of Failure (SPOF)</option>
            </select>
          </div>

          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800">
            <button
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                statusFilter === 'active'
                  ? 'bg-red-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setStatusFilter('active')}
            >
              Active ({findings.filter((f) => !f.is_resolved).length})
            </button>
            <button
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                statusFilter === 'resolved'
                  ? 'bg-red-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setStatusFilter('resolved')}
            >
              Resolved ({findings.filter((f) => f.is_resolved).length})
            </button>
            <button
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                statusFilter === 'all'
                  ? 'bg-red-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setStatusFilter('all')}
            >
              All ({findings.length})
            </button>
          </div>
        </div>
      </div>

      {/* Findings Stream */}
      <div className="space-y-4">
        {loading ? (
          <div className="text-center py-12 text-slate-400">
            <RefreshCw size={24} className="animate-spin mx-auto mb-2 text-red-400" />
            <p className="text-sm">Auditing handover dossiers against institutional records...</p>
          </div>
        ) : filteredFindings.length === 0 ? (
          <div className="text-center py-12 bg-slate-900/40 rounded-xl border border-slate-800 text-slate-400">
            <CheckCircle2 size={32} className="mx-auto mb-2 text-emerald-400" />
            <h4 className="text-slate-200 font-semibold mb-1">Zero Integrity Anomalies Found</h4>
            <p className="text-xs">
              All scanned handover dossiers in this filter scope are backed by verified documentation and valid environment instructions.
            </p>
          </div>
        ) : (
          filteredFindings.map((finding) => {
            const isResolved = finding.is_resolved

            return (
              <div
                key={finding.id}
                className={`p-5 rounded-xl border transition-all ${
                  isResolved
                    ? 'bg-slate-900/30 border-slate-800/60 opacity-80'
                    : 'bg-slate-900/70 border-slate-800 hover:border-slate-700 shadow-sm'
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  <div className="flex-1">
                    {/* Header Badges */}
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider font-mono ${getSeverityBadgeClass(finding.risk_level)}`}>
                        {finding.risk_level}
                      </span>

                      {getFindingTypePill(finding)}

                      <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
                        {finding.category.replace(/_/g, ' ')}
                      </span>

                      <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-red-950/60 text-red-300 border border-red-800/40">
                        {finding.project_name}
                      </span>

                      {isResolved ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 flex items-center gap-1">
                          <Check size={12} /> Resolved
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/60 text-amber-400 border border-amber-800/40">
                          Active Finding
                        </span>
                      )}
                    </div>

                    {/* Grounded Finding Description */}
                    <div className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/80 mb-3 text-xs text-slate-200 leading-relaxed">
                      <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-1 flex items-center gap-1.5">
                        <FileText size={12} className="text-slate-400" />
                        Grounded Sentinel Audit Finding:
                      </div>
                      <p>{finding.description}</p>
                    </div>

                    {/* Prescribed Remediation */}
                    {finding.recommended_action && (
                      <div className="p-3.5 rounded-lg bg-red-950/20 border border-red-900/40 text-xs text-red-200">
                        <div className="text-[11px] uppercase tracking-wider font-semibold text-red-400 mb-1 flex items-center gap-1.5">
                          <Compass size={12} className="text-red-400" />
                          Prescribed Remediation Action:
                        </div>
                        <p className="whitespace-pre-line">{finding.recommended_action}</p>
                      </div>
                    )}
                  </div>

                  {/* Actions & Timestamps */}
                  <div className="flex md:flex-col items-end justify-between md:justify-start gap-3 shrink-0">
                    <div className="text-right text-xs text-slate-500 font-mono">
                      <div>Detected {new Date(finding.detected_at).toLocaleDateString()}</div>
                      {finding.resolved_at && (
                        <div className="text-emerald-500/80">
                          Resolved {new Date(finding.resolved_at).toLocaleDateString()}
                        </div>
                      )}
                    </div>

                    {!isResolved && (
                      <div className="flex items-center gap-2">
                        <button
                          className="py-1.5 px-3 rounded-lg text-xs font-medium bg-amber-600 hover:bg-amber-500 text-white transition flex items-center gap-1.5 shadow-sm"
                          onClick={() => {
                            setActionFinding(finding)
                            setActionType('request_changes')
                            setManagerNotes('')
                          }}
                        >
                          <RotateCcw size={13} />
                          <span>Request Changes</span>
                        </button>

                        <button
                          className="py-1.5 px-3 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow-sm"
                          onClick={() => {
                            setActionFinding(finding)
                            setActionType('resolve')
                            setManagerNotes('')
                          }}
                        >
                          <Check size={13} />
                          <span>Resolve</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Action Modal (Resolve or Request Changes) */}
      {actionFinding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="content-card w-full max-w-lg overflow-hidden border border-slate-700 shadow-2xl">
            <div className="card-header flex items-center justify-between border-b border-slate-800">
              <div className="flex items-center gap-2">
                {actionType === 'resolve' ? (
                  <CheckCircle2 size={18} className="text-emerald-400" />
                ) : (
                  <RotateCcw size={18} className="text-amber-400" />
                )}
                <h3 className="card-title text-base font-semibold">
                  {actionType === 'resolve' ? 'Remediate Sentinel Finding' : 'Request Handover Revisions'}
                </h3>
              </div>
              <button
                onClick={() => setActionFinding(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleConfirmAction} className="p-6 space-y-4">
              {/* Action Type Toggle */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  Manager Action
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    className={`py-2 px-3 rounded-lg text-xs font-semibold border transition flex items-center justify-center gap-1.5 ${
                      actionType === 'resolve'
                        ? 'bg-emerald-950/70 border-emerald-500 text-emerald-200'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                    onClick={() => setActionType('resolve')}
                  >
                    <Check size={14} />
                    <span>Mark Resolved</span>
                  </button>

                  <button
                    type="button"
                    className={`py-2 px-3 rounded-lg text-xs font-semibold border transition flex items-center justify-center gap-1.5 ${
                      actionType === 'request_changes'
                        ? 'bg-amber-950/70 border-amber-500 text-amber-200'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                    onClick={() => setActionType('request_changes')}
                  >
                    <RotateCcw size={14} />
                    <span>Request Changes</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  Reviewing Manager Attribution
                </label>
                <input
                  type="text"
                  required
                  className="w-full px-3 py-2 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-100 focus:outline-none focus:border-red-500"
                  value={managerName}
                  onChange={(e) => setManagerName(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  {actionType === 'resolve' ? 'Resolution Evidence Notes' : 'Handover Revision Instructions'}
                </label>
                <textarea
                  required
                  rows={4}
                  className="w-full px-3 py-2 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-100 focus:outline-none focus:border-red-500 resize-none"
                  placeholder={
                    actionType === 'resolve'
                      ? "Document evidence corroborating resolution (e.g. 'PR #402 merged into main with pass test logs; architecture spec uploaded')."
                      : "Explain required changes to the employee (e.g. 'Please clarify discrepancy between completed Kafka migration and unresolved blocker #2 before resubmitting')."
                  }
                  value={managerNotes}
                  onChange={(e) => setManagerNotes(e.target.value)}
                />
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-400">
                <span className="text-red-400 font-semibold block mb-0.5">Audit Integrity Trail:</span>
                {actionType === 'resolve'
                  ? 'Resolving this finding recalculates the project Handover Integrity Score and records an immutable Audit Log entry.'
                  : 'Requesting changes updates the handover status to changes_requested and returns the dossier to the employee for remediation.'}
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  className="px-4 py-2 text-xs rounded-lg text-slate-400 hover:text-slate-200 transition"
                  onClick={() => setActionFinding(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAction}
                  className={`px-4 py-2 text-xs font-semibold rounded-lg text-white transition flex items-center gap-1.5 shadow ${
                    actionType === 'resolve'
                      ? 'bg-emerald-600 hover:bg-emerald-500'
                      : 'bg-amber-600 hover:bg-amber-500'
                  }`}
                >
                  <Check size={14} />
                  <span>
                    {submittingAction
                      ? 'Recording Action...'
                      : actionType === 'resolve'
                      ? 'Confirm Resolution'
                      : 'Submit Change Request'}
                  </span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Formula Transparency Modal */}
      {showFormulaModal && overview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="content-card w-full max-w-xl max-h-[90vh] overflow-y-auto border border-slate-700 shadow-2xl">
            <div className="card-header flex items-center justify-between border-b border-slate-800">
              <div className="flex items-center gap-2">
                <HelpCircle size={18} className="text-red-400" />
                <h3 className="card-title text-base font-semibold">
                  Handover Integrity Scoring Formula
                </h3>
              </div>
              <button
                onClick={() => setShowFormulaModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-5 text-xs text-slate-300">
              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-red-300">
                {overview.formula}
              </div>

              <div>
                <h4 className="font-semibold text-slate-200 uppercase tracking-wider mb-2">
                  Base Score Components (Max 100 Points)
                </h4>
                <div className="space-y-2">
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between">
                    <span>Handover Section Completeness (6 mandatory sections)</span>
                    <span className="font-mono font-bold text-slate-200">Max 30 pts</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between">
                    <span>Verified Attached Documentation (Specifications / Runbooks)</span>
                    <span className="font-mono font-bold text-slate-200">Max 30 pts</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between">
                    <span>Supported Completed Tasks Evidence Ratio</span>
                    <span className="font-mono font-bold text-slate-200">Max 25 pts</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between">
                    <span>Reproducible Environment Setup Instructions</span>
                    <span className="font-mono font-bold text-slate-200">Max 15 pts</span>
                  </div>
                </div>
              </div>

              <div>
                <h4 className="font-semibold text-slate-200 uppercase tracking-wider mb-2">
                  Finding Penalties
                </h4>
                <div className="space-y-2">
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between text-red-400">
                    <span>Critical (Contradictions, Missing Docs, SPOF $\le 1.0$)</span>
                    <span className="font-mono font-bold">-20 pts per finding</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between text-amber-400">
                    <span>High (Incomplete Sections, Unsupported Claims, Broken URLs)</span>
                    <span className="font-mono font-bold">-10 pts per finding</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between text-yellow-400">
                    <span>Medium (Missing Environment Runbook, Stale Doc Reference)</span>
                    <span className="font-mono font-bold">-5 pts per finding</span>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-slate-800">
                <button
                  type="button"
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
                  onClick={() => setShowFormulaModal(false)}
                >
                  Close Rules
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
