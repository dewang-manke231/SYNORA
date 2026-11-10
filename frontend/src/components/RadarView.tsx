import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import type {
  KnowledgeGapItem,
  ProjectCoverageDetail,
  RadarOverview,
  DocumentItem,
  ProjectRecord,
} from '../types'
import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  Layers,
  Info,
  Check,
  X,
  FileText,
  UserCheck,
  Compass,
  AlertCircle,
  HelpCircle,
  Target,
  FolderKanban,
} from 'lucide-react'
import {
  fetchRadarOverview,
  fetchProjects,
  fetchRadarRisks,
  triggerRadarScan,
  remediateRadarRisk,
  fetchDocuments,
} from '../services/api'

export const RadarView: React.FC<{ projectId?: string }> = ({ projectId }) => {
  const [overview, setOverview] = useState<RadarOverview | null>(null)
  const [risks, setRisks] = useState<KnowledgeGapItem[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [scanningProjectId, setScanningProjectId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [projectDocuments, setProjectDocuments] = useState<DocumentItem[]>([])
  const [projects, setProjects] = useState<ProjectRecord[]>([])
  const radarRequestRef = useRef(0)
  const [activatedProjectId, setActivatedProjectId] = useState('')

  // Filters
  const [selectedProject, setSelectedProject] = useState<string>(projectId || '')
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all')
  const [selectedGapType, setSelectedGapType] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'resolved'>('active')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Modals
  const [resolvingRisk, setResolvingRisk] = useState<KnowledgeGapItem | null>(null)
  const [resolverName, setResolverName] = useState('Marcus Vance (Staff Architect)')
  const [resolutionNotes, setResolutionNotes] = useState('')
  const [submittingResolution, setSubmittingResolution] = useState(false)

  const [explainingProject, setExplainingProject] = useState<ProjectCoverageDetail | null>(null)

  // Load initial data
  const loadRadarData = useCallback(async (projectFilter = '') => {
    const requestId = ++radarRequestRef.current
    setLoading(true)
    setError(null)
    const [overviewResult, risksResult] = await Promise.allSettled([
      fetchRadarOverview(projectFilter || undefined),
      fetchRadarRisks(projectFilter ? { project_id: projectFilter } : undefined),
    ])
    if (requestId !== radarRequestRef.current) return
    const errors: string[] = []
    if (overviewResult.status === 'fulfilled') setOverview(overviewResult.value)
    else errors.push(overviewResult.reason instanceof Error ? overviewResult.reason.message : 'Coverage summary could not load.')
    if (risksResult.status === 'fulfilled') setRisks(risksResult.value)
    else errors.push(risksResult.reason instanceof Error ? risksResult.reason.message : 'Radar findings could not load.')
    if (errors.length) setError(errors.join(' '))
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchProjects().then(setProjects).catch((err) => setError(err instanceof Error ? err.message : 'Project list could not load.'))
  }, [])

  useEffect(() => {
    setSelectedProject(projectId || '')
    setActivatedProjectId('')
    loadRadarData(projectId || '')
  }, [projectId, loadRadarData])

  // Auto-dismiss notification after 5s
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  // Trigger continuous scan
  const handleScan = async (targetProjectId = selectedProject) => {
    if (!targetProjectId) {
      setError('Select a project before activating Knowledge Loss Radar.')
      return
    }
    setScanningProjectId(targetProjectId)
    setScanning(true)
    setError(null)
    try {
      const result = await triggerRadarScan({
        project_id: targetProjectId,
        actor_name: 'Radar Continuous Observer',
      })
      setSuccessMessage(
        result.message || `Scan completed successfully. Active score: ${result.coverage_score}%`
      )
      const refreshedData = await Promise.all([
        loadRadarData(targetProjectId),
        fetchDocuments({ project_id: targetProjectId }),
      ])
      const documents = refreshedData[1]
      setProjectDocuments(documents)
      setActivatedProjectId(targetProjectId)
    } catch (err: any) {
      console.error('Scan failed', err)
      setError(err.message || 'Radar scan failed.')
    } finally {
      setScanning(false)
      setScanningProjectId(null)
    }
  }

  const chooseProject = (id: string) => {
    setSelectedProject(id)
    setActivatedProjectId('')
    setProjectDocuments([])
    setError(null)
    void loadRadarData(id)
  }

  // Handle risk remediation submission
  const handleConfirmResolution = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resolvingRisk) return

    setSubmittingResolution(true)
    try {
      const res = await remediateRadarRisk(resolvingRisk.id, {
        action: 'resolve',
        actor_name: resolverName,
        notes: resolutionNotes || 'Remediated and verified against production standards.',
      })

      setSuccessMessage(res.message || 'Risk resolved successfully.')
      setResolvingRisk(null)
      setResolutionNotes('')
      await loadRadarData(selectedProject)
    } catch (err: any) {
      console.error('Remediation failed', err)
      setError(err.message || 'Failed to resolve risk.')
    } finally {
      setSubmittingResolution(false)
    }
  }

  // Filtered risks
  const filteredRisks = useMemo(() => {
    return risks.filter((r) => {
      if (selectedProject && selectedProject !== 'all' && r.project_id !== selectedProject) return false
      if (selectedSeverity !== 'all' && r.severity.toLowerCase() !== selectedSeverity.toLowerCase()) return false
      if (selectedGapType !== 'all' && r.gap_type !== selectedGapType) return false
      if (statusFilter === 'active' && r.is_resolved) return false
      if (statusFilter === 'resolved' && !r.is_resolved) return false
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchModule = r.module_name.toLowerCase().includes(q)
        const matchDesc = r.description.toLowerCase().includes(q)
        const matchRemediation = (r.recommended_remediation || '').toLowerCase().includes(q)
        if (!matchModule && !matchDesc && !matchRemediation) return false
      }
      return true
    })
  }, [risks, selectedProject, selectedSeverity, selectedGapType, statusFilter, searchQuery])

  const selectedCoverage = overview?.projects.find((p) => p.id === selectedProject)
  const selectedProjectName = selectedCoverage?.name || 'selected project'
  const indexedFileNames = projectDocuments.map((doc) => doc.filename.replaceAll('\\', '/').split('/').pop()?.toLowerCase() || '')
  const missingProjectFiles = activatedProjectId === selectedProject ? [
    !indexedFileNames.some((name) => name.startsWith('readme.')) ? 'README (no README file in the indexed project inventory)' : '',
    !indexedFileNames.some((name) => ['package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'poetry.lock', 'pipfile.lock', 'uv.lock', 'cargo.lock', 'composer.lock'].includes(name)) ? 'Dependency lockfile (no common lockfile in the indexed project inventory)' : '',
  ].filter(Boolean) : []

  // Severity color utility
  const getSeverityBadgeClass = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'badge-critical'
      case 'high':
        return 'badge-high'
      case 'medium':
        return 'badge-medium'
      case 'low':
        return 'badge-low'
      default:
        return 'badge-info'
    }
  }

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

  // Heatmap statistics
  const heatmapStats = useMemo(() => {
    const active = risks.filter((r) => !r.is_resolved)
    const total = active.length || 1
    const crit = active.filter((r) => r.severity.toLowerCase() === 'critical').length
    const high = active.filter((r) => r.severity.toLowerCase() === 'high').length
    const med = active.filter((r) => r.severity.toLowerCase() === 'medium').length
    const low = active.filter((r) => r.severity.toLowerCase() === 'low').length

    return {
      total: active.length,
      crit,
      high,
      med,
      low,
      critPct: Math.round((crit / total) * 100),
      highPct: Math.round((high / total) * 100),
      medPct: Math.round((med / total) * 100),
      lowPct: Math.round((low / total) * 100),
    }
  }, [risks])

  return (
    <div className="section-container">
      {/* Hero / Header */}
      <div className="hero-banner">
        <div className="hero-content">
          <div className="flex items-center gap-2 mb-2">
            <span className="hero-badge flex items-center gap-1.5">
              <Compass size={14} className="text-cyan-400" />
              Module 5: Proactive Risk & Continuity Engine
            </span>
            <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-800/40">
              Zero-Hallucination Evidence Bounds
            </span>
          </div>

          <h2 className="hero-title">Knowledge Loss Radar</h2>
          <p className="hero-desc">
            Autonomous discovery of unrecorded architecture decisions (ADR_MISSING), single maintainer vulnerabilities
            (SECONDARY_OWNER_MISSING), stale technical documentation, and orphaned external dependencies.
            Calculates an auditable, transparent 0-100 Knowledge Coverage Score for every squad and repository.
          </p>

          <div className="hero-actions">
            <label className="radar-project-picker">
              <FolderKanban size={16} />
              <span>Project</span>
              <select aria-label="Select a project for Knowledge Loss Radar" value={selectedProject} onChange={(event) => chooseProject(event.target.value)} disabled={scanning}>
                <option value="">Select a project</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <button
              className="primary-btn flex items-center gap-2"
              onClick={() => void handleScan()}
              disabled={scanning || !selectedProject}
            >
              <RefreshCw size={16} className={scanning ? 'animate-spin' : ''} />
              <span>{scanning ? `Scanning ${selectedProjectName}…` : activatedProjectId === selectedProject ? 'Run Radar Again' : 'Activate Radar'}</span>
            </button>

            <button
              className="secondary-btn flex items-center gap-2"
              onClick={() => {
                if (overview?.projects[0]) {
                  setExplainingProject(overview.projects[0])
                }
              }}
            >
              <HelpCircle size={16} />
              <span>Inspect Scoring Formula</span>
            </button>
          </div>
          {!selectedProject && <p className="radar-project-hint">Choose a project to scan its coverage, knowledge gaps, and indexed files.</p>}
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-4 mb-6 rounded-lg bg-red-950/60 border border-red-800 text-red-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={18} className="text-red-400 shrink-0" />
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

      {/* Overview Stat Cards */}
      <div className="stats-grid mb-6">
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Platform Average Coverage</span>
            <div className="stat-icon-wrapper bg-indigo">
              <Target size={20} />
            </div>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="stat-value text-3xl font-bold font-mono">
              {overview ? `${overview.average_coverage_score}%` : '--'}
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
            <span className="stat-sub">Across {overview?.projects.length || 0} production projects</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Active Critical SPOFs</span>
            <div className="stat-icon-wrapper bg-red">
              <ShieldAlert size={20} />
            </div>
          </div>
          <div className="stat-value text-3xl font-bold text-red-400 font-mono">
            {overview?.critical_gaps ?? 0}
          </div>
          <div className="stat-footer">
            <span className="stat-sub text-red-400">Immediate knowledge loss risk</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">High Severity Gaps</span>
            <div className="stat-icon-wrapper bg-amber">
              <AlertTriangle size={20} />
            </div>
          </div>
          <div className="stat-value text-3xl font-bold text-amber-400 font-mono">
            {overview?.high_gaps ?? 0}
          </div>
          <div className="stat-footer">
            <span className="stat-sub text-amber-400">Missing owners or ADR coverage</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Resolved Remediations</span>
            <div className="stat-icon-wrapper bg-emerald">
              <CheckCircle2 size={20} />
            </div>
          </div>
          <div className="stat-value text-3xl font-bold text-emerald-400 font-mono">
            {overview?.resolved_gaps ?? 0}
          </div>
          <div className="stat-footer">
            <span className="stat-sub text-emerald-400">Audited & recovered by managers</span>
          </div>
        </div>
      </div>

      {activatedProjectId === selectedProject && selectedCoverage && (
        <section className="content-card radar-project-progress mb-6" aria-label={`${selectedCoverage.name} radar progress`}>
          <div className="radar-project-progress-heading"><div><span className="hero-badge">PROJECT RADAR RESULTS</span><h3>{selectedCoverage.name}</h3></div><span className="radar-project-grade" style={{ color: getGradeColor(selectedCoverage.grade), borderColor: getGradeColor(selectedCoverage.grade) }}>Grade {selectedCoverage.grade}</span></div>
          <div className="radar-progress-row"><span>Knowledge coverage</span><strong>{selectedCoverage.knowledge_coverage_score}%</strong></div>
          <div className="radar-progress-track" role="img" aria-label={`Knowledge coverage ${selectedCoverage.knowledge_coverage_score}%`}><span style={{ width: `${Math.max(0, Math.min(100, selectedCoverage.knowledge_coverage_score))}%`, backgroundColor: getGradeColor(selectedCoverage.grade) }} /></div>
          <div className="radar-project-metrics"><span><strong>{selectedCoverage.active_gaps_count}</strong> active gaps</span><span><strong>{projectDocuments.length}</strong> indexed files</span><span><strong>{selectedCoverage.critical_gaps_count}</strong> critical gaps</span></div>
          <div className="radar-missing-files"><strong>File inventory checks</strong>{missingProjectFiles.length ? <ul>{missingProjectFiles.map((file) => <li key={file}>{file}</li>)}</ul> : <p>README and a common dependency lockfile were found in the indexed inventory.</p>}<small>Checks are based on files indexed for this selected project.</small></div>
        </section>
      )}

      {/* Project Coverage Heatmap & Scores */}
      <div className="content-card mb-8">
        <div className="card-header flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers size={18} className="text-indigo-400" />
            <h3 className="card-title text-base font-semibold">Project Knowledge Coverage & Bus Factor</h3>
          </div>
          <span className="text-xs text-slate-400">Audited via AST & Institutional Documentation</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-5">
          {overview?.projects.filter((prj) => !selectedProject || prj.id === selectedProject).map((prj) => {
            const isScanningThis = scanningProjectId === prj.id
            const gradeColor = getGradeColor(prj.grade)

            return (
              <div
                key={prj.id}
                className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 hover:border-slate-700 transition flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h4 className="font-semibold text-slate-100 text-sm">{prj.name}</h4>
                      <span className="text-xs text-slate-400 font-mono">{prj.slug}</span>
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

                  {/* Coverage Health Meter */}
                  <div className="mb-3">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-400">Coverage Score</span>
                      <span className="font-mono font-bold text-slate-200">
                        {prj.knowledge_coverage_score}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div
                        className="h-full transition-all duration-500 rounded-full"
                        style={{
                          width: `${Math.max(4, prj.knowledge_coverage_score)}%`,
                          backgroundColor: gradeColor,
                        }}
                      />
                    </div>
                  </div>

                  {/* Bus Factor & Gap Metrics */}
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
                      <span className="text-slate-400 block text-[11px]">Active Risks</span>
                      <span
                        className={`font-mono font-bold ${
                          prj.active_gaps_count > 0 ? 'text-amber-400' : 'text-slate-400'
                        }`}
                      >
                        {prj.active_gaps_count} ({prj.critical_gaps_count} crit)
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-3 border-t border-slate-800/80">
                  <button
                    className="flex-1 text-xs py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition font-medium flex items-center justify-center gap-1.5"
                    onClick={() => void handleScan(prj.id)}
                    disabled={isScanningThis}
                  >
                    <RefreshCw size={12} className={isScanningThis ? 'animate-spin' : ''} />
                    <span>{isScanningThis ? 'Auditing...' : 'Rescan'}</span>
                  </button>

                  <button
                    className="text-xs py-1.5 px-2 rounded border border-indigo-700/60 text-indigo-300 hover:bg-indigo-950/50 transition font-medium flex items-center gap-1"
                    onClick={() => setExplainingProject(prj)}
                  >
                    <Info size={12} />
                    <span>Formula</span>
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {/* Global Risk Distribution Heatmap Bar */}
        <div className="px-5 pb-5">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="font-medium">Active Risk Severity Spectrum</span>
            <span>{heatmapStats.total} total active gaps</span>
          </div>
          <div className="w-full h-3 rounded-full overflow-hidden flex bg-slate-800">
            {heatmapStats.crit > 0 && (
              <div
                style={{ width: `${heatmapStats.critPct}%` }}
                className="bg-red-500 transition-all"
                title={`Critical: ${heatmapStats.crit} (${heatmapStats.critPct}%)`}
              />
            )}
            {heatmapStats.high > 0 && (
              <div
                style={{ width: `${heatmapStats.highPct}%` }}
                className="bg-amber-500 transition-all"
                title={`High: ${heatmapStats.high} (${heatmapStats.highPct}%)`}
              />
            )}
            {heatmapStats.med > 0 && (
              <div
                style={{ width: `${heatmapStats.medPct}%` }}
                className="bg-yellow-500 transition-all"
                title={`Medium: ${heatmapStats.med} (${heatmapStats.medPct}%)`}
              />
            )}
            {heatmapStats.low > 0 && (
              <div
                style={{ width: `${heatmapStats.lowPct}%` }}
                className="bg-blue-500 transition-all"
                title={`Low: ${heatmapStats.low} (${heatmapStats.lowPct}%)`}
              />
            )}
          </div>
          <div className="flex items-center gap-4 text-xs mt-2 text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" /> Critical ({heatmapStats.crit})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> High ({heatmapStats.high})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500 inline-block" /> Medium ({heatmapStats.med})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" /> Low ({heatmapStats.low})
            </span>
          </div>
        </div>
      </div>

      {/* Filter & Search Toolbar */}
      <div className="content-card mb-6">
        <div className="p-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative min-w-[220px]">
              <Search size={14} className="absolute left-3 top-3 text-slate-400" />
              <input
                type="text"
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-400 focus:outline-none focus:border-indigo-500"
                placeholder="Search module, evidence, or CVE..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* Project Filter */}
            <select
              className="py-1.5 px-3 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500"
              value={selectedProject || 'all'}
              onChange={(e) => chooseProject(e.target.value === 'all' ? '' : e.target.value)}
            >
              <option value="all">All Projects</option>
              {overview?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>

            {/* Severity Filter */}
            <select
              className="py-1.5 px-3 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500"
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>

            {/* Gap Type Filter */}
            <select
              className="py-1.5 px-3 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500"
              value={selectedGapType}
              onChange={(e) => setSelectedGapType(e.target.value)}
            >
              <option value="all">All Gap Categories</option>
              <option value="ADR_MISSING">Missing ADR (ADR_MISSING)</option>
              <option value="SECONDARY_OWNER_MISSING">Single Maintainer (SECONDARY_OWNER_MISSING)</option>
              <option value="STALE_DOCUMENTATION">Stale Documentation (STALE_DOCUMENTATION)</option>
              <option value="UNDOCUMENTED_DEPENDENCY">Undocumented Dependency</option>
            </select>
          </div>

          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800">
            <button
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                statusFilter === 'active'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setStatusFilter('active')}
            >
              Active ({risks.filter((r) => !r.is_resolved).length})
            </button>
            <button
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                statusFilter === 'resolved'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setStatusFilter('resolved')}
            >
              Resolved ({risks.filter((r) => r.is_resolved).length})
            </button>
            <button
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                statusFilter === 'all'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setStatusFilter('all')}
            >
              All ({risks.length})
            </button>
          </div>
        </div>
      </div>

      {/* Discovered Knowledge Risks List */}
      <div className="space-y-4">
        {loading ? (
          <div className="text-center py-12 text-slate-400">
            <RefreshCw size={24} className="animate-spin mx-auto mb-2 text-indigo-400" />
            <p className="text-sm">Synthesizing institutional risk radar...</p>
          </div>
        ) : filteredRisks.length === 0 ? (
          <div className="text-center py-12 bg-slate-900/40 rounded-xl border border-slate-800 text-slate-400">
            <CheckCircle2 size={32} className="mx-auto mb-2 text-emerald-400" />
            <h4 className="text-slate-200 font-semibold mb-1">No Knowledge Risks Found</h4>
            <p className="text-xs">
              All scanned items in this filter criteria meet architecture and documentation coverage standards.
            </p>
          </div>
        ) : (
          filteredRisks.map((risk) => {
            const isResolved = risk.is_resolved
            const project = overview?.projects.find((p) => p.id === risk.project_id)

            return (
              <div
                key={risk.id}
                className={`p-5 rounded-xl border transition-all ${
                  isResolved
                    ? 'bg-slate-900/30 border-slate-800/60 opacity-80'
                    : 'bg-slate-900/70 border-slate-800 hover:border-slate-700 shadow-sm'
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  <div className="flex-1">
                    {/* Header line: Tags & Module Name */}
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider font-mono ${getSeverityBadgeClass(risk.severity)}`}>
                        {risk.severity}
                      </span>

                      <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
                        {risk.gap_type}
                      </span>

                      {project && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-indigo-950/60 text-indigo-300 border border-indigo-800/40">
                          {project.name}
                        </span>
                      )}

                      {isResolved ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 flex items-center gap-1">
                          <Check size={12} /> Resolved
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/60 text-amber-400 border border-amber-800/40">
                          Active Risk
                        </span>
                      )}
                    </div>

                    <h3 className="text-base font-semibold text-slate-100 mb-2 flex items-center gap-2">
                      <span>{risk.module_name}</span>
                    </h3>

                    {/* Evidence & Grounded Description */}
                    <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 mb-3 text-xs text-slate-300 leading-relaxed">
                      <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-1 flex items-center gap-1.5">
                        <FileText size={12} className="text-slate-400" />
                        Grounded Evidence & Finding:
                      </div>
                      <p>{risk.description}</p>
                    </div>

                    {/* Actionable Remediation Protocol */}
                    {risk.recommended_remediation && (
                      <div className="p-3 rounded-lg bg-indigo-950/20 border border-indigo-900/40 text-xs text-indigo-200">
                        <div className="text-[11px] uppercase tracking-wider font-semibold text-indigo-400 mb-1 flex items-center gap-1.5">
                          <Compass size={12} className="text-indigo-400" />
                          Prescribed Remediation Protocol:
                        </div>
                        <p className="whitespace-pre-line">{risk.recommended_remediation}</p>
                      </div>
                    )}
                  </div>

                  {/* Actions & Timestamps */}
                  <div className="flex md:flex-col items-end justify-between md:justify-start gap-3 shrink-0">
                    <div className="text-right text-xs text-slate-500 font-mono">
                      <div>Detected {new Date(risk.detected_at).toLocaleDateString()}</div>
                      {risk.resolved_at && (
                        <div className="text-emerald-500/80">
                          Resolved {new Date(risk.resolved_at).toLocaleDateString()}
                        </div>
                      )}
                    </div>

                    {!isResolved && (
                      <button
                        className="py-1.5 px-3 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5 shadow-sm"
                        onClick={() => {
                          setResolvingRisk(risk)
                          setResolutionNotes('')
                        }}
                      >
                        <UserCheck size={14} />
                        <span>Remediate Risk</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Remediation Action Modal */}
      {resolvingRisk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="content-card w-full max-w-lg overflow-hidden border border-slate-700 shadow-2xl">
            <div className="card-header flex items-center justify-between border-b border-slate-800">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={18} className="text-emerald-400" />
                <h3 className="card-title text-base font-semibold">Remediate Knowledge Risk</h3>
              </div>
              <button
                onClick={() => setResolvingRisk(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleConfirmResolution} className="p-6 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  Target Component
                </label>
                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200">
                  {resolvingRisk.module_name} ({resolvingRisk.gap_type})
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  Manager / Reviewer Attribution
                </label>
                <input
                  type="text"
                  required
                  className="w-full px-3 py-2 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-100 focus:outline-none focus:border-indigo-500"
                  value={resolverName}
                  onChange={(e) => setResolverName(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  Resolution Notes & Evidence Link
                </label>
                <textarea
                  required
                  rows={4}
                  className="w-full px-3 py-2 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-100 focus:outline-none focus:border-indigo-500 resize-none"
                  placeholder="Document how this gap was remediated (e.g. 'ADR-042 committed to repository; Sarah Chen assigned as secondary reviewer on proxy cluster')."
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                />
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-400">
                <span className="text-emerald-400 font-semibold block mb-0.5">Continuous Audit Guarantee:</span>
                Resolving this risk recalculates the project Knowledge Coverage Score immediately and appends a verified
                entry to the immutable institutional Audit Log.
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  className="px-4 py-2 text-xs rounded-lg text-slate-400 hover:text-slate-200 transition"
                  onClick={() => setResolvingRisk(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingResolution}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow"
                >
                  <Check size={14} />
                  <span>{submittingResolution ? 'Logging Resolution...' : 'Confirm Resolution'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Formula Transparency & Score Explanation Modal */}
      {explainingProject && explainingProject.explanation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="content-card w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-slate-700 shadow-2xl">
            <div className="card-header flex items-center justify-between border-b border-slate-800">
              <div className="flex items-center gap-2">
                <HelpCircle size={18} className="text-indigo-400" />
                <h3 className="card-title text-base font-semibold">
                  Knowledge Coverage Score Breakdown: {explainingProject.name}
                </h3>
              </div>
              <button
                onClick={() => setExplainingProject(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Score Banner */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-xs uppercase tracking-wider text-slate-400 block font-semibold">
                    Current Coverage Score
                  </span>
                  <div className="text-3xl font-mono font-bold text-slate-100">
                    {explainingProject.explanation.score}%
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-xs uppercase tracking-wider text-slate-400 block font-semibold">
                    Continuity Grade
                  </span>
                  <span
                    className="text-2xl font-mono font-bold"
                    style={{ color: getGradeColor(explainingProject.explanation.grade) }}
                  >
                    Grade {explainingProject.explanation.grade}
                  </span>
                </div>
              </div>

              {/* Formula Explanation */}
              <div>
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Transparent Mathematical Formula
                </h4>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-indigo-300">
                  {explainingProject.explanation.formula}
                </div>
              </div>

              {/* Factors Breakdown */}
              <div>
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Base Factor Contributions (Raw: {explainingProject.explanation.raw_score} / 100)
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">Documentation (max 35 pts)</span>
                    <span className="text-base font-mono font-bold text-slate-200">
                      +{explainingProject.explanation.breakdown.documentation_points} pts
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">Decisions / ADRs (max 30 pts)</span>
                    <span className="text-base font-mono font-bold text-slate-200">
                      +{explainingProject.explanation.breakdown.decision_points} pts
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">Ownership & Bus Factor (max 20 pts)</span>
                    <span className="text-base font-mono font-bold text-slate-200">
                      +{explainingProject.explanation.breakdown.ownership_points} pts
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-xs text-slate-400 block">Verification Ratio (max 15 pts)</span>
                    <span className="text-base font-mono font-bold text-slate-200">
                      +{explainingProject.explanation.breakdown.verification_points} pts
                    </span>
                  </div>
                </div>
              </div>

              {/* Itemized Penalty Deductions */}
              <div>
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center justify-between">
                  <span>Itemized Penalty Deductions</span>
                  <span className="text-red-400 font-mono">
                    Total: -{explainingProject.explanation.penalties} pts
                  </span>
                </h4>

                {explainingProject.explanation.penalty_breakdown.length === 0 ? (
                  <div className="p-3 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 text-xs">
                    No active penalties! All discovered risks in this project have been resolved.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {explainingProject.explanation.penalty_breakdown.map((p, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between text-xs"
                      >
                        <div>
                          <span className="font-semibold text-slate-200 block">{p.module_name}</span>
                          <span className="text-slate-400 text-[11px] font-mono uppercase">
                            {p.severity} risk
                          </span>
                        </div>
                        <span className="font-mono font-bold text-red-400">-{p.deduction} pts</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex justify-end pt-3 border-t border-slate-800">
                <button
                  type="button"
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
                  onClick={() => setExplainingProject(null)}
                >
                  Close Breakdown
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
