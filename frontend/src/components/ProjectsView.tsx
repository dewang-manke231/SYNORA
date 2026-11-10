import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft, BookOpen, CheckCircle2, ChevronRight, CircleHelp, ExternalLink, GitBranch, Link2, Plus, Trash2,
  Cpu, FileArchive, FileText, FolderKanban, LoaderCircle, Radar, ShieldAlert,
  Terminal, UploadCloud, X,
} from 'lucide-react'
import {
  fetchDocuments, fetchSentinelOverview,
  fetchProject,
  fetchProjects, fetchRadarOverview, fetchRadarRisks, fetchRisks,
  intakeProjectZip, extractProjectZip, remediateRadarRisk, remediateSentinelRisk, updateProjectRepository,
} from '../services/api'
import type {
  DocumentItem, KnowledgeGapItem, ProjectIntakeFinding, ProjectIntakeResult,
  ProjectRecord, RiskAlert,
} from '../types'

type ProjectMetrics = { integrity?: number; grade?: string; radar?: number; gaps: number; risks: number; radarAvailable: boolean; sentinelAvailable: boolean }
type ProjectViewProps = {
  userId: string
  managerMode?: boolean
  activeProjectId: string
  onSelectProject: (id: string, name?: string) => void
  onOpenModule: (tab: string, projectId: string, projectName?: string) => void
}

const MAX_ZIP_BYTES = 50 * 1024 * 1024

export const ProjectsView: React.FC<ProjectViewProps> = ({ userId, activeProjectId, onSelectProject, onOpenModule, managerMode = false }) => {
  const [projects, setProjects] = useState<ProjectRecord[]>([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<Record<string, ProjectMetrics>>({})
  const [selectedProject, setSelectedProject] = useState<ProjectRecord | null>(null)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [analysis, setAnalysis] = useState<ProjectIntakeResult | null>(null)
  const [gaps, setGaps] = useState<KnowledgeGapItem[]>([])
  const [risks, setRisks] = useState<RiskAlert[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [extractProgress, setExtractProgress] = useState(0)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [reviewedLocal, setReviewedLocal] = useState<string[]>([])
  const [projectLinks, setProjectLinks] = useState<Array<{ label: string; url: string; kind: 'link' | 'repository' }>>([])
  const [newLinkLabel, setNewLinkLabel] = useState('')
  const [newLinkUrl, setNewLinkUrl] = useState('')
  const [repositoryUrl, setRepositoryUrl] = useState('')
  const [savingRepository, setSavingRepository] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const extractFileInput = useRef<HTMLInputElement>(null)
  const activeProjectRef = useRef(activeProjectId)
  activeProjectRef.current = activeProjectId

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true)
    setLoadError(null)
    try {
      const rows = await fetchProjects()
      setProjects(rows)
      setMetrics({})
      setLoadingProjects(false)
      if (activeProjectRef.current && !rows.some((project) => project.id === activeProjectRef.current)) onSelectProject('')
      void Promise.all([
        fetchRadarOverview().catch(() => null),
        fetchSentinelOverview().catch(() => null),
      ]).then(([radar, sentinel]) => {
        const entries = rows.map((project) => {
          const rProject = radar?.projects.find((item) => item.id === project.id)
          const sProject = sentinel?.projects.find((item) => item.project_id === project.id)
          return [project.id, {
            integrity: sProject?.integrity_score,
            grade: sProject?.grade,
            radar: rProject?.knowledge_coverage_score,
            gaps: rProject?.active_gaps_count ?? 0,
            risks: sProject?.active_findings_count ?? 0,
            radarAvailable: Boolean(radar),
            sentinelAvailable: Boolean(sentinel),
          }] as const
        })
        setMetrics(Object.fromEntries(entries))
      })
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Unable to load projects.')
    } finally {
      setLoadingProjects(false)
    }
  }, [onSelectProject])

  useEffect(() => { void loadProjects() }, [loadProjects])

  const chooseArchive = (candidate?: File) => {
    if (!candidate) return
    setUploadError(null)
    if (!candidate.name.toLowerCase().endsWith('.zip')) {
      setZipFile(null)
      setUploadError('Choose a .zip project archive.')
      return
    }
    if (candidate.size === 0) {
      setZipFile(null)
      setUploadError('The selected ZIP archive is empty.')
      return
    }
    if (candidate.size > MAX_ZIP_BYTES) {
      setZipFile(null)
      setUploadError('The archive must be 50 MB or smaller.')
      return
    }
    setZipFile(candidate)
  }

  const handleUpload = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!projectName.trim() || !zipFile) {
      setUploadError('Enter a project name and choose a ZIP archive.')
      return
    }
    setUploading(true)
    setUploadProgress(0)
    setUploadError(null)
    try {
      const result = await intakeProjectZip(projectName.trim(), zipFile, setUploadProgress)
      try { sessionStorage.setItem(analysisStorageKey(userId, result.project_id), JSON.stringify(result)) } catch { /* Intake still succeeds if browser storage is unavailable. */ }
      await loadProjects()
      onSelectProject(result.project_id, result.project_name)
      setShowCreate(false)
      setProjectName('')
      setZipFile(null)
      setAnalysis(result)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Project upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const handleExtractProjectArchive = async (candidate?: File) => {
    if (!candidate || !activeProjectId) return
    setExtractError(null)
    if (!candidate.name.toLowerCase().endsWith('.zip')) {
      setExtractError('Choose a .zip project archive.')
      return
    }
    if (candidate.size === 0 || candidate.size > MAX_ZIP_BYTES) {
      setExtractError('Choose a non-empty ZIP archive no larger than 50 MB.')
      return
    }
    setExtracting(true)
    setExtractProgress(0)
    try {
      const result = await extractProjectZip(activeProjectId, candidate, setExtractProgress)
      setAnalysis(result)
      try { sessionStorage.setItem(analysisStorageKey(userId, activeProjectId), JSON.stringify(result)) } catch { /* Extraction data is still shown for this session. */ }
      const [docs, radarRows, sentinelRows] = await Promise.all([
        fetchDocuments({ project_id: activeProjectId }),
        fetchRadarRisks({ project_id: activeProjectId }),
        fetchRisks({ project_id: activeProjectId }),
      ])
      setDocuments(docs)
      setGaps(radarRows)
      setRisks(sentinelRows)
      await loadProjects()
    } catch (err) {
      setExtractError(err instanceof Error ? err.message : 'Project extraction failed.')
    } finally {
      setExtracting(false)
    }
  }

  useEffect(() => {
    setRepositoryUrl(selectedProject?.repository_url || '')
    try { setProjectLinks(JSON.parse(localStorage.getItem(`synora_project_links_${userId}_${activeProjectId}`) || '[]')) } catch { setProjectLinks([]) }
  }, [selectedProject?.id, selectedProject?.repository_url, activeProjectId, userId])

  const addProjectLink = (kind: 'link' | 'repository') => {
    const url = newLinkUrl.trim()
    try { const parsed = new URL(url); if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error() } catch { setDetailError('Enter a valid http(s) link.'); return }
    const link = { label: newLinkLabel.trim() || (kind === 'repository' ? 'Git repository' : new URL(url).hostname), url, kind }
    const next = [link, ...projectLinks.filter((item) => item.url !== url)]
    setProjectLinks(next)
    localStorage.setItem(`synora_project_links_${userId}_${activeProjectId}`, JSON.stringify(next))
    if (kind === 'repository' && !repositoryUrl.trim()) void saveRepository(url)
    setNewLinkLabel(''); setNewLinkUrl(''); setDetailError(null)
  }

  const saveRepository = async (value = repositoryUrl) => {
    setSavingRepository(true)
    try { const updated = await updateProjectRepository(activeProjectId, value.trim()); setSelectedProject((current) => current ? { ...current, repository_url: updated.repository_url } : current); setRepositoryUrl(updated.repository_url || '') }
    catch (err) { setDetailError(err instanceof Error ? err.message : 'Could not save Git repository URL.') }
    finally { setSavingRepository(false) }
  }

  const removeProjectLink = (url: string) => {
    const next = projectLinks.filter((item) => item.url !== url)
    setProjectLinks(next)
    localStorage.setItem(`synora_project_links_${userId}_${activeProjectId}`, JSON.stringify(next))
  }

  useEffect(() => {
    if (!activeProjectId) {
      setSelectedProject(null)
      setDocuments([])
      setAnalysis(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setDetailError(null)
    const cached = readAnalysisCache(userId, activeProjectId)
    setAnalysis(cached)
    const reviewedKey = `synora_reviewed_${userId}_${activeProjectId}`
    try { setReviewedLocal(JSON.parse(sessionStorage.getItem(reviewedKey) || '[]')) } catch { setReviewedLocal([]) }
    const recover = <T,>(request: Promise<T>, fallback: T, label: string) => request.catch((error: unknown) => {
      if (!cancelled) setDetailError((current) => current || `${label} could not be loaded: ${error instanceof Error ? error.message : 'request failed'}`)
      return fallback
    })
    Promise.all([
      fetchProject(activeProjectId),
      recover(fetchDocuments({ project_id: activeProjectId }), [], 'Project documents'),
      recover(fetchRadarRisks({ project_id: activeProjectId }), [], 'Radar findings'),
      recover(fetchRisks({ project_id: activeProjectId }), [], 'Sentinel findings'),
    ]).then(([project, docs, radarRows, sentinelRows]) => {
      if (cancelled) return
      setSelectedProject(project)
      setDocuments(docs)
      setGaps(radarRows)
      setRisks(sentinelRows)
    }).catch((err: unknown) => {
      if (!cancelled) setDetailError(err instanceof Error ? err.message : 'Unable to load project details.')
    }).finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [activeProjectId, userId])

  const analysisFindings = useMemo(() => {
    const fromIntake: Array<ProjectIntakeFinding & { id: string; kind: 'archive' | 'radar' | 'sentinel'; resolved?: boolean; recommendedAction?: string }> =
      (analysis?.findings || []).map((finding, index) => ({ ...finding, id: `archive-${index}`, kind: 'archive', recommendedAction: '' }))
    const fromRadar = gaps.map((gap) => ({
      id: gap.id, category: gap.gap_type, severity: gap.severity, evidence_type: 'observed',
      source: 'Radar knowledge gap', evidence: gap.description, kind: 'radar' as const, resolved: gap.is_resolved,
      recommendedAction: gap.recommended_remediation || '',
    }))
    const fromSentinel = risks.map((risk) => ({
      id: risk.id, category: risk.category, severity: risk.risk_level,
      evidence_type: risk.finding_type === 'verified_fact' ? 'observed' : 'inference',
      source: risk.evidence_source || 'Sentinel project scan', evidence: risk.description,
      kind: 'sentinel' as const, resolved: Boolean(risk.is_resolved), recommendedAction: risk.recommended_action,
    }))
    return [...fromIntake, ...fromRadar, ...fromSentinel]
  }, [analysis, gaps, risks])

  const handleReview = async (finding: (typeof analysisFindings)[number]) => {
    setReviewingId(finding.id)
    try {
      if (finding.kind === 'sentinel') {
        const updated = await remediateSentinelRisk(finding.id, {
          action: finding.resolved ? 'acknowledge' : 'resolve',
          actor_name: 'Project Reviewer', notes: 'Reviewed in the project workspace.',
        })
        setRisks((current) => current.map((risk) => risk.id === finding.id ? updated.risk : risk))
      } else if (finding.kind === 'radar') {
        const updated = await remediateRadarRisk(finding.id, {
          action: finding.resolved ? 'acknowledge' : 'resolve',
          actor_name: 'Project Reviewer', notes: 'Reviewed in the project workspace.',
        })
        setGaps((current) => current.map((gap) => gap.id === finding.id ? updated.risk : gap))
      } else {
        const next = [...reviewedLocal, finding.id]
        setReviewedLocal(next)
        if (activeProjectId) sessionStorage.setItem(`synora_reviewed_${userId}_${activeProjectId}`, JSON.stringify(next))
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Unable to update finding status.')
    } finally {
      setReviewingId(null)
    }
  }

  const activeMetrics = activeProjectId ? metrics[activeProjectId] : undefined
  const docsCount = documents.length
  const observedFindings = analysisFindings.filter((finding) => finding.evidence_type === 'observed').length
  const inferredFindings = analysisFindings.filter((finding) => finding.evidence_type !== 'observed').length

  return (
    <section className="section-container projects-workspace" aria-labelledby="projects-heading">
      {!activeProjectId ? (
        <>
          <div className="section-header projects-heading-row">
            <div>
              <h2 id="projects-heading">Projects</h2>
              <p className="section-desc">Upload a project archive to review its documents, continuity gaps, risks, and setup guidance.</p>
            </div>
            <button className="primary-btn flex items-center gap-2" onClick={() => { setShowCreate(true); setUploadError(null) }}>
              <UploadCloud size={16} /> Create Project
            </button>
          </div>
          {loadError && <div className="error-banner" role="alert">{loadError}</div>}
          {loadingProjects ? <LoadingState label="Loading projects…" /> : projects.length === 0 ? (
            <div className="project-empty-state">
              <FolderKanban size={34} aria-hidden="true" />
              <h3>No projects yet</h3>
              <p>Create a project by uploading its ZIP archive. Synora will index supported files and report what it finds.</p>
              <button className="primary-btn" onClick={() => setShowCreate(true)}>Create your first project</button>
            </div>
          ) : (
            <div className="project-card-grid">
              {projects.map((project) => {
                const metric = metrics[project.id]
                return (
                  <button className="project-card" key={project.id} onClick={() => onSelectProject(project.id, project.name)}>
                    <div className="project-card-top"><FolderKanban size={20} /><span>{new Date(project.created_at).toLocaleDateString()}</span></div>
                    <h3>{project.name}</h3>
                    <p>{project.description || 'No project description provided.'}</p>
                    <div className="project-card-stats">
                      <span>Integrity <strong>{metric?.integrity == null ? '—' : `${metric.integrity}%`}</strong></span>
                      <span>Grade <strong>{metric?.grade || 'Not assessed'}</strong></span>
                    </div>
                    <div className="project-card-bottom"><span>{metric && (metric.radarAvailable || metric.sentinelAvailable) ? `${metric.radarAvailable ? `${metric.gaps} Radar gaps` : 'Radar unavailable'} · ${metric.sentinelAvailable ? `${metric.risks} Sentinel findings` : 'Sentinel unavailable'}` : metric ? 'Analysis status unavailable' : 'Analysis status loading'}</span><ChevronRight size={16} /></div>
                  </button>
                )
              })}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="section-header project-detail-heading">
            <div>
              <button className="project-back-button" onClick={() => onSelectProject('')}><ArrowLeft size={15} /> All projects</button>
              <h2 id="projects-heading">{selectedProject?.name || projects.find((p) => p.id === activeProjectId)?.name || 'Project'}</h2>
              <p className="section-desc">{selectedProject?.description || 'Project health and uploaded archive analysis.'}</p>
            </div>
            <label className="project-switcher-label">Switch project
              <select value={activeProjectId} onChange={(event) => { const id = event.target.value; onSelectProject(id, projects.find((project) => project.id === id)?.name) }} aria-label="Switch project">
                {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
            </label>
          </div>
          {detailError && <div className="error-banner" role="alert">{detailError}</div>}
          {detailLoading ? <LoadingState label="Loading project analysis…" /> : (
            <>
              <div className="project-health-grid">
                <MetricCard label="Sentinel integrity" value={activeMetrics?.integrity == null ? '—' : `${activeMetrics.integrity}%`} detail={activeMetrics?.grade || 'No Sentinel grade returned'} icon={<ShieldAlert size={18} />} />
                <MetricCard label="Radar coverage" value={activeMetrics?.radar == null ? '—' : `${activeMetrics.radar}%`} detail={`${activeMetrics?.gaps ?? gaps.length} active Radar gap(s)`} icon={<Radar size={18} />} />
                <MetricCard label="Indexed files" value={String(docsCount)} detail={`${documents.filter((doc) => doc.processing_status === 'processed' || doc.processing_status === 'completed').length} processed`} icon={<FileText size={18} />} />
              </div>

              {!managerMode && <div className="project-module-links" aria-label="Project modules">
                <button onClick={() => onOpenModule('knowledge', activeProjectId, selectedProject?.name)}><BookOpen size={16} /> Knowledge</button>
                <button onClick={() => onOpenModule('radar', activeProjectId, selectedProject?.name)}><Radar size={16} /> Radar</button>
                <button onClick={() => onOpenModule('sentinel', activeProjectId, selectedProject?.name)}><ShieldAlert size={16} /> Sentinel</button>
                <button onClick={() => onOpenModule('recreator', activeProjectId, selectedProject?.name)}><Terminal size={16} /> Environment Recreator</button>
                <button onClick={() => onOpenModule('handovers', activeProjectId, selectedProject?.name)}><FileText size={16} /> Handovers</button>
              </div>}

              <section className="project-panel">
                <div className="project-panel-heading"><div><h3>Project analysis</h3><p>Extract a ZIP into this project and review exactly what Synora indexed.</p></div><div className="project-analysis-actions"><span className="analysis-status-pill">{analysis ? 'Archive analyzed' : 'Existing project data'}</span><button type="button" className="secondary-btn" onClick={() => { setExtractError(null); extractFileInput.current?.click() }} disabled={extracting}><FileArchive size={15} />{extracting ? 'Extracting…' : 'Extract project ZIP'}</button><input ref={extractFileInput} type="file" accept=".zip,application/zip" hidden onChange={(event) => { const candidate = event.target.files?.[0]; event.target.value = ''; void handleExtractProjectArchive(candidate) }} /></div></div>
                {extractError && <div className="error-banner" role="alert">{extractError}</div>}
                {extracting && <div className="project-progress"><div><span>Extracting, indexing, and analyzing project files…</span><strong>{extractProgress}%</strong></div><progress value={extractProgress} max={100} aria-label="Project extraction progress" /></div>}
                {analysis ? (
                  <>
                    <div className="analysis-summary-row">
                      <span><strong>{analysis.indexed_file_count}</strong> extracted and indexed</span><span><strong>{analysis.skipped_file_count}</strong> skipped or duplicate</span>
                      <span><strong>{analysis.todo_count}</strong> TODO / FIXME markers</span><span>{observedFindings} observed · {inferredFindings} inferred</span>
                    </div>
                    <div className="project-extraction-summary"><strong>Extraction summary</strong><span>{analysis.detected_technologies.length ? `Detected: ${analysis.detected_technologies.join(', ')}` : 'No technology detected from the extracted manifests.'}</span><span>{analysis.manifests.length ? `Manifests: ${analysis.manifests.join(', ')}` : 'No supported dependency manifest found.'}</span><span>Radar gaps added: {analysis.radar_gaps_created} · Sentinel findings added: {analysis.sentinel_findings_created}</span>{!!analysis.extracted_file_names?.length && <div className="project-extracted-name-list"><span>Files extracted:</span>{analysis.extracted_file_names.slice(0, 12).map((name) => <code key={name}>{name}</code>)}{analysis.extracted_file_names.length > 12 && <small>and {analysis.extracted_file_names.length - 12} more — see Uploaded file inventory below.</small>}</div>}</div>
                    <div className="project-chip-row">
                      {analysis.detected_technologies.length ? analysis.detected_technologies.map((tech) => <span className="project-chip" key={tech}><Cpu size={13} />{tech}</span>) : <span className="muted-empty">No technology was detected in the uploaded manifests.</span>}
                    </div>
                    <p className="project-manifest-line"><strong>Detected manifests:</strong> {analysis.manifests.length ? analysis.manifests.join(', ') : 'None recognized'}</p>
                  </>
                ) : (
                  <div className="project-limitation-note"><CircleHelp size={17} /><p>No extraction summary is saved for this project yet. Choose <strong>Extract project ZIP</strong> to securely scan and index its supported files. Secrets, private keys, and generated folders remain excluded.</p></div>
                )}
              </section>

              <section className="project-panel">
                <div className="project-panel-heading"><div><h3>Uploaded file inventory</h3><p>Files returned for this project only.</p></div><span>{documents.length} files</span></div>
                {documents.length ? <div className="project-file-list">{documents.map((doc) => <div className="project-file-row" key={doc.id}><FileText size={15} /><span className="project-file-name">{doc.filename}</span><span>{doc.chunk_count} chunks</span><span className={`file-status ${doc.processing_status}`}>{doc.processing_status}</span></div>)}</div> : <p className="muted-empty">No indexed documents are available for this project.</p>}
              </section>

              <section className="project-panel project-links-panel">
                <div className="project-panel-heading"><div><h3>Project links & Git repositories</h3><p>Keep the source repository and useful project resources close at hand.</p></div><Link2 size={18} /></div>
                <form className="project-repository-form" onSubmit={(event) => { event.preventDefault(); void saveRepository() }}>
                  <label><GitBranch size={15} /> Primary Git repository URL</label>
                  <div><input type="url" value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} placeholder="https://github.com/organization/repository" /><button className="secondary-btn" type="submit" disabled={savingRepository}>{savingRepository ? 'Saving…' : 'Save repository'}</button></div>
                </form>
                <form className="project-link-add-form" onSubmit={(event) => { event.preventDefault(); addProjectLink('link') }}>
                  <input value={newLinkLabel} onChange={(event) => setNewLinkLabel(event.target.value)} placeholder="Link name (e.g. API docs)" aria-label="Link name" />
                  <input type="url" value={newLinkUrl} onChange={(event) => setNewLinkUrl(event.target.value)} placeholder="https://…" aria-label="Project link URL" required />
                  <button className="primary-btn" type="submit"><Plus size={15} /> Add link</button>
                  <button className="secondary-btn" type="button" onClick={() => addProjectLink('repository')} disabled={!newLinkUrl.trim()}><GitBranch size={15} /> Add Git repo</button>
                </form>
                <div className="project-link-list">
                  {repositoryUrl && <div className="project-link-row"><GitBranch size={15} /><span><strong>Primary repository</strong><small>{repositoryUrl}</small></span><a href={repositoryUrl} target="_blank" rel="noreferrer" aria-label="Open primary repository"><ExternalLink size={15} /></a></div>}
                  {projectLinks.map((link) => <div className="project-link-row" key={link.url}>{link.kind === 'repository' ? <GitBranch size={15} /> : <Link2 size={15} />}<span><strong>{link.label}</strong><small>{link.url}</small></span><a href={link.url} target="_blank" rel="noreferrer" aria-label={`Open ${link.label}`}><ExternalLink size={15} /></a><button type="button" onClick={() => removeProjectLink(link.url)} aria-label={`Remove ${link.label}`}><Trash2 size={14} /></button></div>)}
                  {!repositoryUrl && !projectLinks.length && <p className="muted-empty">No repository or project links added yet.</p>}
                </div>
                <small className="project-links-storage-note">The primary repository is saved to the project. Additional links are saved in this browser for this project.</small>
              </section>

              <section className="project-panel">
                <div className="project-panel-heading"><div><h3>Continuity findings</h3><p>Evidence and inference are labelled separately. Server-backed findings can be reviewed below.</p></div><span>{analysisFindings.length} findings</span></div>
                {analysisFindings.length ? <div className="project-finding-list">{analysisFindings.map((finding) => {
                  const localReviewed = reviewedLocal.includes(finding.id)
                  const resolved = Boolean(finding.resolved) || localReviewed
                  return <article className="project-finding" key={`${finding.kind}-${finding.id}`}>
                    <div className="project-finding-top"><div><span className={`finding-severity ${finding.severity.toLowerCase()}`}>{finding.severity}</span><span className="finding-kind">{finding.category.replaceAll('_', ' ')}</span></div><span className={`evidence-type ${finding.evidence_type}`}>{finding.evidence_type === 'observed' ? 'Observed' : 'Inference'}</span></div>
                    <p>{finding.evidence}</p><small>Source: {finding.source}</small>
                    {finding.recommendedAction && <p className="project-recommendation"><strong>Recommended action:</strong> {finding.recommendedAction}</p>}
                    <div className="project-finding-actions">{finding.kind !== 'archive' && !resolved ? <button disabled={reviewingId === finding.id} onClick={() => void handleReview(finding)}>{reviewingId === finding.id ? 'Saving…' : 'Mark resolved'}</button> : finding.kind === 'archive' && !resolved ? <button onClick={() => void handleReview(finding)}>Mark reviewed in this browser</button> : <span className="reviewed-label"><CheckCircle2 size={14} />{localReviewed ? 'Reviewed in this browser' : 'Resolved'}</span>}</div>
                  </article>
                })}</div> : <div className="muted-empty project-no-findings">{detailLoading ? 'Loading findings…' : 'No findings were returned by the available project services.'}</div>}
              </section>
            </>
          )}
        </>
      )}

      {showCreate && <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !uploading) setShowCreate(false) }}>
        <form className="project-create-modal" onSubmit={(event) => void handleUpload(event)} aria-labelledby="create-project-title">
          <div className="project-modal-heading"><div><h3 id="create-project-title">Create project</h3><p>Upload the project archive you want Synora to analyze.</p></div><button type="button" className="project-icon-button" onClick={() => setShowCreate(false)} disabled={uploading} aria-label="Close create project dialog"><X size={18} /></button></div>
          <label className="project-form-label">Project name<input autoFocus maxLength={255} value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="e.g. Mobile Banking API" required /></label>
          <div className={`project-dropzone ${dragging ? 'dragging' : ''}`} role="button" tabIndex={0} onClick={() => fileInput.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') fileInput.current?.click() }} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseArchive(event.dataTransfer.files[0]) }}>
            <FileArchive size={27} /><strong>{zipFile?.name || 'Drop a ZIP archive here'}</strong><span>{zipFile ? `${(zipFile.size / (1024 * 1024)).toFixed(1)} MB` : 'or click to browse · ZIP up to 50 MB'}</span>
            <input ref={fileInput} type="file" accept=".zip,application/zip" hidden onChange={(event) => chooseArchive(event.target.files?.[0])} />
          </div>
          <p className="project-upload-privacy">Environment secrets, private keys, generated files, and unsupported file types are excluded before indexing.</p>
          {uploadError && <div className="error-banner" role="alert">{uploadError}</div>}
          {uploading && <div className="project-progress"><div><span>Uploading and analyzing archive…</span><strong>{uploadProgress}%</strong></div><progress value={uploadProgress} max={100} aria-label="Project upload progress" /></div>}
          <div className="project-modal-actions"><button type="button" className="secondary-btn" disabled={uploading} onClick={() => setShowCreate(false)}>Cancel</button><button type="submit" className="primary-btn" disabled={uploading || !projectName.trim() || !zipFile}>{uploading ? <><LoaderCircle size={15} className="spin" /> Processing…</> : <><UploadCloud size={15} /> Upload and analyze</>}</button></div>
        </form>
      </div>}
    </section>
  )
}

function analysisStorageKey(userId: string, projectId: string) { return `synora_intake_${userId}_${projectId}` }
function readAnalysisCache(userId: string, projectId: string): ProjectIntakeResult | null {
  try {
    const value = sessionStorage.getItem(analysisStorageKey(userId, projectId))
    return value ? JSON.parse(value) as ProjectIntakeResult : null
  } catch { return null }
}

const MetricCard: React.FC<{ label: string; value: string; detail: string; icon: React.ReactNode }> = ({ label, value, detail, icon }) => (
  <div className="project-metric-card"><div className="project-metric-icon">{icon}</div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
)

const LoadingState: React.FC<{ label: string }> = ({ label }) => <div className="project-loading-state"><LoaderCircle size={19} className="spin" />{label}</div>
