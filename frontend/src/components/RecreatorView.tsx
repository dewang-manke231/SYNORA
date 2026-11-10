import React, { useState, useEffect, useMemo } from 'react'
import type {
  ManifestInspectionResult,
  EnvironmentBlueprint,
  ReadinessAssessment,
  OnboardingChecklist,
  OnboardingChecklistStep,
} from '../types'
import {
  fetchManifestInspection,
  fetchEnvironmentBlueprint,
  generateEnvironmentBlueprint,
  fetchEnvironmentReadiness,
  updateOnboardingChecklist,
  getEnvExampleDownloadUrl,
  getDockerComposeDownloadUrl,
  fetchProjects,
} from '../services/api'
import {
  Terminal,
  Cpu,
  Layers,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Copy,
  Check,
  Download,
  RefreshCw,
  Play,
  FileCode,
  ShieldCheck,
  CheckSquare,
  Square,
  FileText,
  Clock,
  User,
} from 'lucide-react'

export const RecreatorView: React.FC<{ projectId?: string; onAskAssistant?: (projectId: string, projectName?: string) => void }> = ({ projectId, onAskAssistant }) => {
  // Projects state
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')

  // Data states
  const [inspection, setInspection] = useState<ManifestInspectionResult | null>(null)
  const [blueprint, setBlueprint] = useState<EnvironmentBlueprint | null>(null)
  const [readiness, setReadiness] = useState<ReadinessAssessment | null>(null)
  const [checklist, setChecklist] = useState<OnboardingChecklist | null>(null)

  // Loading & Action states
  const [loading, setLoading] = useState<boolean>(true)
  const [generating, setGenerating] = useState<boolean>(false)
  const [updatingStepId, setUpdatingStepId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // UI tabs & toggles
  const [activeTab, setActiveTab] = useState<'quickstart' | 'checklist' | 'readiness' | 'export'>('quickstart')
  const [shellType, setShellType] = useState<'powershell' | 'bash'>('powershell')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [actorName, setActorName] = useState<string>('Incoming Engineer')

  // Copy helper
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 2000)
  }

  // Use authenticated projects returned by the backend; do not invent a workspace project.
  useEffect(() => {
    async function loadProjects() {
      try {
        const rows = await fetchProjects()
        const mapped = rows.map((project) => ({ id: project.id, name: project.name }))
        setProjects(mapped)
        const preferred = projectId && mapped.some((project) => project.id === projectId)
          ? projectId
          : mapped[0]?.id || ''
        setSelectedProjectId(preferred)
      } catch (err: any) {
        console.error('Failed to load project list:', err)
        setProjects([])
        setSelectedProjectId('')
      }
    }
    loadProjects()
  }, [projectId])

  // Load module data whenever selectedProjectId changes
  useEffect(() => {
    if (!selectedProjectId) return
    let cancelled = false

    async function loadModuleData() {
      setLoading(true)
      setError(null)
      setInspection(null)
      setBlueprint(null)
      setReadiness(null)
      setChecklist(null)
      try {
        // These endpoints are independent. Fetch them together instead of making
        // the screen wait for four sequential network round trips.
        const [insp, bp, ready] = await Promise.all([
          fetchManifestInspection(selectedProjectId),
          fetchEnvironmentBlueprint(selectedProjectId),
          fetchEnvironmentReadiness(selectedProjectId),
        ])
        if (cancelled) return

        setInspection(insp)
        setBlueprint(bp)
        setReadiness(ready)

        // The blueprint already contains the persisted checklist, so avoid a
        // second endpoint call that reads/creates the same snapshot.
        const steps = Array.isArray(bp.blueprint_spec?.onboarding_checklist)
          ? bp.blueprint_spec.onboarding_checklist
          : []
        const completedSteps = steps.filter((step: OnboardingChecklistStep) => step.is_completed).length
        setChecklist({
          project_id: selectedProjectId,
          project_name: projects.find((project) => project.id === selectedProjectId)?.name || bp.environment_name,
          total_steps: steps.length,
          completed_steps: completedSteps,
          completion_percentage: steps.length ? Math.round((completedSteps / steps.length) * 100) : 0,
          steps,
        })
      } catch (err: any) {
        if (cancelled) return
        console.error('Failed to load recreator data:', err)
        setError(err.message || 'Failed to load environment configuration')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadModuleData()
    return () => { cancelled = true }
  }, [selectedProjectId, projects])

  // Handle regenerating blueprint
  const handleRegenerateBlueprint = async () => {
    if (!selectedProjectId) return
    setGenerating(true)
    setError(null)
    try {
      const [updatedBp, ready] = await Promise.all([
        generateEnvironmentBlueprint(selectedProjectId, actorName),
        fetchEnvironmentReadiness(selectedProjectId),
      ])
      setBlueprint(updatedBp)
      setReadiness(ready)
      const steps = Array.isArray(updatedBp.blueprint_spec?.onboarding_checklist)
        ? updatedBp.blueprint_spec.onboarding_checklist
        : []
      const completedSteps = steps.filter((step: OnboardingChecklistStep) => step.is_completed).length
      setChecklist({
        project_id: selectedProjectId,
        project_name: projects.find((project) => project.id === selectedProjectId)?.name || updatedBp.environment_name,
        total_steps: steps.length,
        completed_steps: completedSteps,
        completion_percentage: steps.length ? Math.round((completedSteps / steps.length) * 100) : 0,
        steps,
      })

      setSuccessMessage('Deterministic environment blueprint regenerated successfully.')
      setTimeout(() => setSuccessMessage(null), 3500)
    } catch (err: any) {
      setError(err.message || 'Failed to regenerate blueprint')
    } finally {
      setGenerating(false)
    }
  }

  // Handle checklist step toggle
  const handleToggleChecklistStep = async (step: OnboardingChecklistStep) => {
    if (!selectedProjectId) return
    setUpdatingStepId(step.id)
    try {
      const updated = await updateOnboardingChecklist({
        project_id: selectedProjectId,
        step_id: step.id,
        is_completed: !step.is_completed,
        actor_name: actorName,
        notes: step.is_completed ? 'Step unchecked' : 'Completed during ramp-up runbook',
      })
      setChecklist(updated)
    } catch (err: any) {
      setError(err.message || 'Failed to update checklist item')
    } finally {
      setUpdatingStepId(null)
    }
  }

  // Selected project name
  const currentProjectName = useMemo(() => {
    const found = projects.find((p) => p.id === selectedProjectId)
    return found ? found.name : 'Synora Core'
  }, [projects, selectedProjectId])

  // Checklist completion percentage calculation
  const checklistPercent = useMemo(() => {
    if (!checklist || checklist.total_steps === 0) return 0
    return Math.round((checklist.completed_steps / checklist.total_steps) * 100)
  }, [checklist])

  const stackLanguages = useMemo(() => {
    if (!inspection) return []
    const languages: string[] = []
    const pythonVersion = inspection.python_version && !/not specified|unknown/i.test(inspection.python_version)
    const nodeVersion = inspection.node_version && !/not specified|unknown/i.test(inspection.node_version)
    if (pythonVersion || inspection.backend_dependencies?.length) languages.push(pythonVersion ? `Python ${inspection.python_version}` : 'Python')
    if (nodeVersion || inspection.frontend_dependencies?.length) languages.push(nodeVersion ? `JavaScript / Node.js ${inspection.node_version}` : 'JavaScript / Node.js')
    if (inspection.detected_frameworks?.includes('TypeScript')) languages.push('TypeScript')
    return languages
  }, [inspection])

  if (!selectedProjectId) {
    return <div className="section-container"><div className="project-empty-state"><Cpu size={30} /><h3>Select an uploaded project</h3><p>Environment inspection is scoped to a project in your organization. Create or upload one from Projects.</p></div></div>
  }

  return (
    <div className="section-container">
      {/* Hero Header */}
      <div className="hero-banner">
        <div className="hero-content">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="hero-badge flex items-center gap-1.5">
              <Cpu size={14} className="text-cyan-400" />
              Module 8: Environment Recreator & Deterministic Onboarding Engine
            </span>
              <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-emerald-950/70 text-emerald-400 border border-emerald-800/40">
              Uploaded Project Guidance
            </span>
            <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-indigo-950/60 text-indigo-400 border border-indigo-800/40">
              Secret-safe guidance
            </span>
          </div>

          <h2 className="hero-title">Environment Recreator</h2>
          {onAskAssistant && <button className="secondary-btn recreator-ai-help" onClick={() => onAskAssistant(selectedProjectId, projects.find((project) => project.id === selectedProjectId)?.name)}>Ask AI about this setup</button>}
          <p className="hero-desc">
            Inspect uploaded project manifests and generate setup guidance. Commands and prerequisites still require local validation.
            Incoming engineers receive OS startup sequences, redacted configuration runbooks,
            and an interactive onboarding checklist with persistent step attribution.
          </p>

          <div className="hero-actions flex items-center gap-3 flex-wrap">
            <button
              className="primary-btn flex items-center gap-2"
              onClick={handleRegenerateBlueprint}
              disabled={generating || loading}
            >
              <RefreshCw size={16} className={generating ? 'animate-spin' : ''} />
              <span>{generating ? 'Regenerating Blueprint...' : 'Regenerate Blueprint'}</span>
            </button>

            <button
              className="secondary-btn flex items-center gap-2"
              onClick={() => setActiveTab('readiness')}
            >
              <ShieldCheck size={16} className="text-emerald-400" />
              <span>Readiness Score: {readiness?.readiness_score ?? '—'}/100</span>
            </button>

            {/* Project Selector Dropdown */}
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-slate-400 font-medium">Target Project:</span>
              <select
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-3 py-1.5 font-medium focus:outline-none focus:border-indigo-500"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="mb-4 p-3 bg-emerald-950/60 border border-emerald-800 text-emerald-300 rounded text-xs flex items-center gap-2">
          <CheckCircle2 size={16} />
          <span>{successMessage}</span>
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 bg-red-950/60 border border-red-800 text-red-300 rounded text-xs flex items-center gap-2">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Uploaded project technology stack */}
      {inspection && (
        <section className="recreator-stack card" aria-labelledby="recreator-stack-title">
          <div className="recreator-stack-heading">
            <div className="recreator-stack-icon"><Layers size={21} /></div>
            <div>
              <h3 id="recreator-stack-title">Project tech stack</h3>
              <p>Detected from the selected project’s uploaded files and manifests.</p>
            </div>
            <span className="recreator-stack-type">{inspection.stack_type.replace(/_/g, ' ')}</span>
          </div>
          <div className="recreator-stack-grid">
            <div className="recreator-stack-group">
              <h4>Languages &amp; runtimes</h4>
              <div className="recreator-stack-chips">
                {stackLanguages.length ? stackLanguages.map((language) => <span className="recreator-stack-chip" key={language}>{language}</span>) : <span className="recreator-stack-empty">Not detected in the uploaded manifests</span>}
              </div>
            </div>
            <div className="recreator-stack-group">
              <h4>Frameworks &amp; tools</h4>
              <div className="recreator-stack-chips">
                {inspection.detected_frameworks.length ? inspection.detected_frameworks.map((framework) => <span className="recreator-stack-chip" key={framework}>{framework}</span>) : <span className="recreator-stack-empty">No frameworks detected</span>}
              </div>
            </div>
            <div className="recreator-stack-group">
              <h4>Backend dependencies <span>{inspection.backend_dependencies.length}</span></h4>
              <div className="recreator-stack-chips">
                {inspection.backend_dependencies.length ? inspection.backend_dependencies.slice(0, 12).map((dependency) => <span className="recreator-stack-chip" key={dependency}>{dependency}</span>) : <span className="recreator-stack-empty">None detected</span>}
                {inspection.backend_dependencies.length > 12 && <span className="recreator-stack-more">+{inspection.backend_dependencies.length - 12} more</span>}
              </div>
            </div>
            <div className="recreator-stack-group">
              <h4>Frontend dependencies <span>{inspection.frontend_dependencies.length}</span></h4>
              <div className="recreator-stack-chips">
                {inspection.frontend_dependencies.length ? inspection.frontend_dependencies.slice(0, 12).map((dependency) => <span className="recreator-stack-chip" key={dependency}>{dependency}</span>) : <span className="recreator-stack-empty">None detected</span>}
                {inspection.frontend_dependencies.length > 12 && <span className="recreator-stack-more">+{inspection.frontend_dependencies.length - 12} more</span>}
              </div>
            </div>
          </div>
          <div className="recreator-stack-manifests"><FileCode size={15} /><strong>Inspected files:</strong> {inspection.manifest_files_found.length ? inspection.manifest_files_found.join(', ') : 'No supported manifests found'}</div>
        </section>
      )}

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 mb-6 pb-2 overflow-x-auto">
        <button
          onClick={() => setActiveTab('quickstart')}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-xs font-semibold transition-all ${
            activeTab === 'quickstart'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <Terminal size={14} />
          <span>OS Quickstart Sequences</span>
        </button>

        <button
          onClick={() => setActiveTab('checklist')}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-xs font-semibold transition-all ${
            activeTab === 'checklist'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <CheckSquare size={14} />
          <span>Interactive Onboarding Checklist</span>
          {checklist && (
            <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-slate-300">
              {checklist.completed_steps}/{checklist.total_steps}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('readiness')}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-xs font-semibold transition-all ${
            activeTab === 'readiness'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <ShieldCheck size={14} />
          <span>Readiness & Diagnostics</span>
          {readiness && (
            <span
              className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                readiness.status === 'ready'
                  ? 'bg-emerald-950 text-emerald-300'
                  : 'bg-amber-950 text-amber-300'
              }`}
            >
              {readiness.readiness_score}%
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('export')}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-xs font-semibold transition-all ${
            activeTab === 'export'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          <FileCode size={14} />
          <span>Export Configurations & Docker</span>
        </button>
      </div>

      {/* TAB 1: OS QUICKSTART SEQUENCES */}
      {activeTab === 'quickstart' && (
        <div className="space-y-6">
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="flex items-center justify-between flex-wrap gap-4 mb-4">
              <div>
                <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                  <Play size={18} className="text-indigo-400" />
                  Deterministic Developer Ramp-Up Sequence
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Validated commands tailored specifically to the project runtime. Run these in two separate terminal windows.
                </p>
              </div>

              {/* OS Shell Pill Switcher */}
              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded border border-slate-800">
                <button
                  onClick={() => setShellType('powershell')}
                  className={`px-3 py-1 rounded text-xs font-mono font-medium transition-colors ${
                    shellType === 'powershell'
                      ? 'bg-indigo-600 text-white shadow'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Windows PowerShell
                </button>
                <button
                  onClick={() => setShellType('bash')}
                  className={`px-3 py-1 rounded text-xs font-mono font-medium transition-colors ${
                    shellType === 'bash'
                      ? 'bg-indigo-600 text-white shadow'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Linux / macOS Bash
                </button>
              </div>
            </div>

            {/* Code Block with Copy Button */}
            <div className="relative group">
              <div className="absolute top-3 right-3 z-10">
                <button
                  className="copy-btn flex items-center gap-1.5 text-xs bg-slate-800/90 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded border border-slate-700"
                  onClick={() =>
                    handleCopy(
                      shellType === 'powershell'
                        ? blueprint?.powershell_quickstart || ''
                        : blueprint?.bash_quickstart || '',
                      'quickstart'
                    )
                  }
                >
                  {copiedKey === 'quickstart' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  <span>{copiedKey === 'quickstart' ? 'Copied Sequence!' : 'Copy Script'}</span>
                </button>
              </div>

              <pre className="code-block font-mono text-xs bg-slate-950 p-4 rounded-lg border border-slate-800 overflow-x-auto text-slate-200 leading-relaxed">
                <code>
                  {shellType === 'powershell'
                    ? blueprint?.powershell_quickstart || '# Loading PowerShell script...'
                    : blueprint?.bash_quickstart || '# Loading Bash script...'}
                </code>
              </pre>
            </div>

            {/* Key Technical Execution Notes */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-xs">
              <div className="p-3 bg-slate-950/70 border border-slate-800/60 rounded">
                <strong className="text-slate-200 block mb-1">
                  {shellType === 'powershell' ? 'PowerShell Virtual Environment Activation' : 'Bash Virtualenv Activation'}
                </strong>
                <p className="text-slate-400">
                  {shellType === 'powershell'
                    ? 'Uses .\\.venv\\Scripts\\activate.ps1. If script execution is restricted, run: Set-ExecutionPolicy -Scope Process RemoteSigned'
                    : 'Uses source .venv/bin/activate to cleanly isolate runtime dependencies in POSIX shells.'}
                </p>
              </div>
              <div className="p-3 bg-slate-950/70 border border-slate-800/60 rounded">
                <strong className="text-slate-200 block mb-1">Dual-Terminal Orchestration</strong>
                <p className="text-slate-400">
                  Terminal 1 runs the FastAPI backend on port 8000. Terminal 2 runs the Vite dev server with hot-module reload on port 5173.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: INTERACTIVE ONBOARDING CHECKLIST */}
      {activeTab === 'checklist' && (
        <div className="space-y-6">
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            {/* Header & Progress Bar */}
            <div className="flex items-center justify-between flex-wrap gap-4 mb-4">
              <div>
                <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                  <CheckSquare size={18} className="text-indigo-400" />
                  Interactive Onboarding Checklist & Continuity Log
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Track and persist setup milestones for project: <strong className="text-slate-200">{currentProjectName}</strong>.
                  All step updates are immutably persisted in the environment snapshot.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <div className="text-right">
                  <span className="text-xs font-mono text-slate-400">Completion</span>
                  <p className="text-base font-bold text-slate-100 font-mono">{checklistPercent}%</p>
                </div>
                <div className="w-28 bg-slate-800 rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-indigo-500 h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${checklistPercent}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Actor attribution input */}
            <div className="mb-4 p-3 bg-slate-950/70 border border-slate-800 rounded flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <User size={14} className="text-slate-400" />
                <span className="text-xs text-slate-300">Acting Onboarding Engineer:</span>
              </div>
              <input
                type="text"
                value={actorName}
                onChange={(e) => setActorName(e.target.value)}
                placeholder="Enter engineer name or email..."
                className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-3 py-1 font-mono focus:outline-none focus:border-indigo-500 w-64"
              />
            </div>

            {/* Checklist Step Items */}
            <div className="space-y-3">
              {checklist?.steps.map((step) => {
                const isUpdating = updatingStepId === step.id
                return (
                  <div
                    key={step.id}
                    className={`p-4 rounded-lg border transition-all ${
                      step.is_completed
                        ? 'bg-slate-950/40 border-slate-800/80 text-slate-400'
                        : 'bg-slate-900/80 border-slate-700/80 text-slate-200 shadow-sm'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Checkbox */}
                      <button
                        onClick={() => handleToggleChecklistStep(step)}
                        disabled={isUpdating}
                        className="mt-0.5 text-slate-400 hover:text-indigo-400 focus:outline-none transition-colors"
                      >
                        {isUpdating ? (
                          <RefreshCw size={18} className="animate-spin text-indigo-400" />
                        ) : step.is_completed ? (
                          <CheckSquare size={18} className="text-emerald-400" />
                        ) : (
                          <Square size={18} />
                        )}
                      </button>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="text-xs font-mono font-bold text-slate-500">#{step.order}</span>
                          <h4
                            className={`text-sm font-semibold ${
                              step.is_completed ? 'line-through text-slate-400' : 'text-slate-100'
                            }`}
                          >
                            {step.title}
                          </h4>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-slate-800 text-slate-400 border border-slate-700">
                            {step.category.replace(/_/g, ' ')}
                          </span>
                        </div>

                        {/* Command Snippet with Copy */}
                        {step.command_snippet && (
                          <div className="my-2 flex items-center justify-between gap-2 bg-slate-950 px-3 py-1.5 rounded border border-slate-800 font-mono text-xs text-indigo-300">
                            <span className="truncate">{step.command_snippet}</span>
                            <button
                              onClick={() => handleCopy(step.command_snippet || '', step.id)}
                              className="text-slate-400 hover:text-slate-200 p-1"
                              title="Copy command"
                            >
                              {copiedKey === step.id ? (
                                <Check size={13} className="text-emerald-400" />
                              ) : (
                                <Copy size={13} />
                              )}
                            </button>
                          </div>
                        )}

                        {/* Completion Attribution Metadata */}
                        {step.is_completed && step.completed_by && (
                          <div className="flex items-center gap-2 text-[11px] text-emerald-400/80 font-mono mt-1">
                            <Clock size={11} />
                            <span>
                              Completed by {step.completed_by}
                              {step.completed_at ? ` on ${new Date(step.completed_at).toLocaleString()}` : ''}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: READINESS & PRE-FLIGHT DIAGNOSTICS */}
      {activeTab === 'readiness' && (
        <div className="space-y-6">
          {/* Readiness Score Banner */}
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-3">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center font-bold text-lg font-mono ${
                    readiness?.status === 'ready'
                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                      : 'bg-amber-950 text-amber-400 border border-amber-800'
                  }`}
                >
                  {readiness?.readiness_score ?? 100}%
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold text-slate-100">
                      Machine Readiness Assessment
                    </h3>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-mono font-bold uppercase tracking-wider ${
                        readiness?.status === 'ready'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : 'bg-amber-950 text-amber-400 border border-amber-800'
                      }`}
                    >
                      {readiness?.status === 'ready' ? 'Ready for Ramp-Up' : readiness?.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    Evaluates local compiler toolchains, package managers, and port availability.
                  </p>
                </div>
              </div>

              <button
                className="secondary-btn flex items-center gap-2 text-xs"
                onClick={handleRegenerateBlueprint}
                disabled={generating}
              >
                <RefreshCw size={14} className={generating ? 'animate-spin' : ''} />
                <span>Rerun Pre-Flight Checks</span>
              </button>
            </div>
          </div>

          {/* Prerequisite Checks Grid */}
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <h4 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
              <ShieldCheck size={16} className="text-indigo-400" />
              Runtime Prerequisite Checks
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {readiness?.prerequisites.map((chk, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-lg border flex items-start gap-3 ${
                    chk.is_met
                      ? 'bg-slate-950/60 border-slate-800'
                      : 'bg-red-950/20 border-red-800/60'
                  }`}
                >
                  {chk.is_met ? (
                    <CheckCircle2 size={18} className="text-emerald-400 mt-0.5 shrink-0" />
                  ) : (
                    <XCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <strong className="text-xs font-semibold text-slate-200">{chk.tool}</strong>
                      <span className="text-[11px] font-mono text-slate-400">
                        Required: {chk.required_version}
                      </span>
                    </div>
                    {chk.installed_version && (
                      <p className="text-[11px] font-mono text-indigo-300 mt-0.5">
                        Detected: {chk.installed_version}
                      </p>
                    )}
                    <p className="text-xs text-slate-400 mt-1.5">{chk.guidance}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Potential Failure Modes & Mitigations */}
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <h4 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
              <AlertTriangle size={16} className="text-amber-400" />
              Potential Failure Modes & Preventative Mitigations
            </h4>
            <div className="space-y-3">
              {readiness?.potential_failure_modes.map((pfm, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-slate-950/70 border border-slate-800 rounded flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-slate-200">{pfm.risk_factor}</span>
                      <span
                        className={`px-1.5 py-0.2 rounded text-[10px] font-mono uppercase ${
                          pfm.severity === 'high'
                            ? 'bg-red-950 text-red-400 border border-red-800/50'
                            : 'bg-amber-950 text-amber-400 border border-amber-800/50'
                        }`}
                      >
                        {pfm.severity}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">{pfm.description}</p>
                  </div>
                  <div className="sm:max-w-xs bg-slate-900 p-2 rounded border border-slate-800 text-[11px] font-mono text-emerald-400">
                    <span className="text-slate-500 block text-[9px] uppercase tracking-wider font-sans">
                      Mitigation:
                    </span>
                    {pfm.mitigation}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Detected vs Inferred Integrity Ledger */}
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <h4 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
              <FileText size={16} className="text-cyan-400" />
              Evidence-Based Ingestion Audit (Detected vs Inferred)
            </h4>
            <p className="text-xs text-slate-400 mb-4">
              Synora guarantees that all dependencies, frameworks, and commands are extracted directly from committed manifests. Unevidenced packages or external services are never invented.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
              <div className="p-3 bg-slate-950 rounded border border-slate-800">
                <span className="text-emerald-400 font-semibold block mb-2 font-sans">
                  Confirmed Manifest Files (On Disk):
                </span>
                <ul className="space-y-1 text-slate-300">
                  {inspection?.manifest_files_found.map((f, i) => (
                    <li key={i} className="flex items-center gap-1.5">
                      <Check size={12} className="text-emerald-400" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="p-3 bg-slate-950 rounded border border-slate-800">
                <span className="text-cyan-400 font-semibold block mb-2 font-sans">
                  Environment Variables Redacted:
                </span>
                <div className="text-slate-400 text-[11px] leading-relaxed">
                  {inspection?.environment_variables_detected.length ? (
                    inspection.environment_variables_detected.map((envVar) => (
                      <span
                        key={envVar}
                        className="inline-block bg-slate-900 px-2 py-0.5 rounded mr-1.5 mb-1.5 border border-slate-800 text-slate-300"
                      >
                        {envVar}
                      </span>
                    ))
                  ) : (
                    <span>No unredacted variables detected.</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: EXPORT CONFIGURATIONS & DOCKER */}
      {activeTab === 'export' && (
        <div className="space-y-6">
          {/* Secret Redaction Guarantee Banner */}
          <div className="card p-4 bg-emerald-950/30 border border-emerald-800/60 rounded-lg flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <ShieldCheck size={24} className="text-emerald-400" />
              <div>
                <h4 className="text-sm font-semibold text-emerald-200">
                  Zero Credential Leakage Guarantee
                </h4>
                <p className="text-xs text-emerald-300/80">
                  Database passwords, Gemini API keys, JWT secret keys, and credentials are replaced with safe placeholders before export.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <a
                href={getEnvExampleDownloadUrl(selectedProjectId)}
                download=".env.example"
                className="secondary-btn flex items-center gap-1.5 text-xs py-1.5 px-3"
              >
                <Download size={14} />
                <span>Export .env.example</span>
              </a>
              <a
                href={getDockerComposeDownloadUrl(selectedProjectId)}
                download="docker-compose.yml"
                className="secondary-btn flex items-center gap-1.5 text-xs py-1.5 px-3"
              >
                <Download size={14} />
                <span>Export docker-compose.yml</span>
              </a>
            </div>
          </div>

          {/* Docker Compose YAML Viewer */}
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-200">
                  Containerized Environment (docker-compose.yml)
                </h4>
                <p className="text-xs text-slate-400">
                  Multi-container development orchestrator with health probes and shared network bindings.
                </p>
              </div>

              <button
                className="copy-btn flex items-center gap-1 text-xs"
                onClick={() => handleCopy(blueprint?.docker_compose_yaml || '', 'docker')}
              >
                {copiedKey === 'docker' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                <span>{copiedKey === 'docker' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            <pre className="code-block font-mono text-xs bg-slate-950 p-4 rounded-lg border border-slate-800 overflow-x-auto text-slate-300">
              <code>{blueprint?.docker_compose_yaml || '# No docker compose generated yet'}</code>
            </pre>
          </div>

          {/* .env.example Viewer */}
          <div className="card p-5 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-200">
                  Redacted Environment Variable Template (.env.example)
                </h4>
                <p className="text-xs text-slate-400">
                  Safe configuration template showing required keys and formats with dummy values.
                </p>
              </div>

              <button
                className="copy-btn flex items-center gap-1 text-xs"
                onClick={() => handleCopy(blueprint?.env_example_content || '', 'env')}
              >
                {copiedKey === 'env' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                <span>{copiedKey === 'env' ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            <pre className="code-block font-mono text-xs bg-slate-950 p-4 rounded-lg border border-slate-800 overflow-x-auto text-emerald-300">
              <code>{blueprint?.env_example_content || '# No env content generated yet'}</code>
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
