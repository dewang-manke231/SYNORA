import React, { useState, useEffect } from 'react'
import type {
  HandoverItem,
  HandoverCreatePayload,
  HandoverStatus,
  DocumentItem,
  DocumentDetail,
  DocumentChunkItem,
  AssigneeUser,
  ProjectRecord,
} from '../types'
import {
  PlusCircle,
  CheckCircle,
  Clock,
  AlertTriangle,
  ArrowRight,
  FileText,
  Download,
  Send,
  MessageSquare,
  ShieldCheck,
  Edit3,
  ExternalLink,
  Layers,
  UserCheck,
  UsersRound,
  CheckSquare,
  Square,
  X,
  FileCheck2,
  UploadCloud,
  FileCode,
  Trash2,
  Eye,
  RefreshCw,
} from 'lucide-react'
import {
  submitHandover,
  startHandoverReview,
  approveHandover,
  requestHandoverChanges,
  completeHandover,
  updateHandover,
  exportHandoverMarkdown,
  getHandoverDownloadUrl,
  fetchDocuments,
  fetchDocumentDetail,
  fetchDocumentChunks,
  uploadDocument,
  deleteDocument,
  fetchEligibleAssignees,
  assignHandover,
  fetchProjects,
  createOrganizationEmployee,
} from '../services/api'

interface HandoverViewProps {
  handovers: HandoverItem[]
  onCreateHandover: (payload: HandoverCreatePayload) => Promise<void>
  onRefreshHandovers?: () => Promise<void>
  activeProjectId?: string
  activeProjectName?: string
  managerMode?: boolean
  currentUserName?: string
  currentUserId?: string
  onProjectChange?: (projectId: string, projectName?: string) => void
}

export const HandoverView: React.FC<HandoverViewProps> = ({
  handovers,
  onCreateHandover,
  onRefreshHandovers,
  activeProjectId,
  activeProjectName,
  managerMode = false,
  currentUserName = 'Synora User',
  currentUserId = '',
  onProjectChange,
}) => {
  const activePersona: 'employee' | 'manager' = managerMode ? 'manager' : 'employee'
  const currentUser = { employeeName: currentUserName, managerName: currentUserName }

  // Modals & Drawers state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [selectedHandover, setSelectedHandover] = useState<HandoverItem | null>(null)
  const [showChangeRequestModal, setShowChangeRequestModal] = useState(false)
  const [changeRequestReason, setChangeRequestReason] = useState('')
  const [showExportModal, setShowExportModal] = useState(false)
  const [exportMarkdown, setExportMarkdown] = useState<string>('')
  const [submittingAction, setSubmittingAction] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  // New-Joiner Assignment State
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [assignees, setAssignees] = useState<AssigneeUser[]>([])
  const [loadingAssignees, setLoadingAssignees] = useState(false)
  const [selectedAssigneeId, setSelectedAssigneeId] = useState('')
  const [assignNotes, setAssignNotes] = useState('')
  const [filterTab, setFilterTab] = useState<'all' | 'assigned_to_me' | 'unassigned'>('all')
  const [roleFilter, setRoleFilter] = useState('all')
  const [autoRoleSegregation, setAutoRoleSegregation] = useState(true)
  const [managerProjects, setManagerProjects] = useState<ProjectRecord[]>([])
  const [showEmployeePanel, setShowEmployeePanel] = useState(false)
  const [employeeRows, setEmployeeRows] = useState<AssigneeUser[]>([])
  const [employeeForm, setEmployeeForm] = useState({ full_name: '', email: '', password: '' })
  const [creatingEmployee, setCreatingEmployee] = useState(false)

  // Document Ingestion State (Module 1)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [uploadingDoc, setUploadingDoc] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
  const [inspectingDoc, setInspectingDoc] = useState<DocumentDetail | null>(null)
  const [inspectingChunks, setInspectingChunks] = useState<DocumentChunkItem[]>([])
  const [loadingDocDetails, setLoadingDocDetails] = useState(false)
  const [docViewTab, setDocViewTab] = useState<'text' | 'chunks'>('text')

  const loadDocuments = async () => {
    try {
      const docs = await fetchDocuments()
      setDocuments(docs)
    } catch (err) {
      console.warn('Failed to load documents', err)
    }
  }

  useEffect(() => {
    loadDocuments()
  }, [])

  const scopedHandovers = managerMode
    ? (activeProjectId ? handovers.filter((item) => item.project_id === activeProjectId) : [])
    : handovers.filter((item) => item.employee_name.trim().toLowerCase() === currentUserName.trim().toLowerCase() || (!!currentUserId && item.assigned_to === currentUserId))
  const roleGroups = Array.from(new Set(scopedHandovers.map((item) => item.role.trim()).filter(Boolean))).sort()

  useEffect(() => {
    if (!managerMode) return
    fetchProjects().then(setManagerProjects).catch((error) => setActionError(error.message || 'Could not load projects.'))
  }, [managerMode])

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedHandover) return

    setUploadingDoc(true)
    setUploadError(null)
    setUploadSuccess(null)

    try {
      const newDoc = await uploadDocument(file, {
        handover_id: selectedHandover.id,
        project_id: selectedHandover.project_id || undefined,
        uploader_name: activePersona === 'employee' ? currentUser.employeeName : currentUser.managerName,
      })
      setUploadSuccess(`'${newDoc.filename}' successfully uploaded and indexed into ${newDoc.chunk_count} chunks.`)
      await loadDocuments()
      if (onRefreshHandovers) {
        await onRefreshHandovers()
      }
    } catch (err: any) {
      setUploadError(err.message || 'Document upload failed. Please try again.')
    } finally {
      setUploadingDoc(false)
      e.target.value = ''
    }
  }

  const handleInspectDoc = async (docItem: DocumentItem) => {
    setLoadingDocDetails(true)
    setDocViewTab('text')
    try {
      const [detail, chunks] = await Promise.all([
        fetchDocumentDetail(docItem.id),
        fetchDocumentChunks(docItem.id),
      ])
      setInspectingDoc(detail)
      setInspectingChunks(chunks)
    } catch (err: any) {
      setUploadError(`Failed to load document content: ${err.message}`)
    } finally {
      setLoadingDocDetails(false)
    }
  }

  const handleDeleteDoc = async (docId: string) => {
    if (!window.confirm('Are you sure you want to delete this document and its indexed chunks?')) {
      return
    }
    try {
      await deleteDocument(docId, activePersona === 'employee' ? currentUser.employeeName : currentUser.managerName)
      setDocuments((prev) => prev.filter((d) => d.id !== docId))
      if (inspectingDoc?.id === docId) {
        setInspectingDoc(null)
        setInspectingChunks([])
      }
      setUploadSuccess('Document deleted successfully.')
      if (onRefreshHandovers) {
        await onRefreshHandovers()
      }
    } catch (err: any) {
      setUploadError(`Failed to delete document: ${err.message}`)
    }
  }

  // Edit state within detail drawer
  const [isEditing, setIsEditing] = useState(false)
  const [editNotes, setEditNotes] = useState('')
  const [newCompletedTask, setNewCompletedTask] = useState('')
  const [newPendingTask, setNewPendingTask] = useState('')
  const [newBlocker, setNewBlocker] = useState('')

  // Create Form State
  const [form, setForm] = useState({
    project_id: activeProjectId || '',
    employee_name: currentUserName,
    role: '',
    department: '',
    transition_type: 'resignation',
    project_name: activeProjectName || '',
    project_description: '',
    responsibilities: '',
    dependencies: '',
    blockers: '',
    completed_tasks: '',
    pending_tasks: '',
    important_notes: '',
    recommended_next_actions: '',
    repository_links: '',
    documentation_links: '',
    database_references: '',
  })

  useEffect(() => {
    if (activeProjectId) setForm((current) => ({
      ...current,
      project_id: activeProjectId,
      project_name: activeProjectName || current.project_name,
      project_description: '',
    }))
  }, [activeProjectId, activeProjectName])

  useEffect(() => { setSelectedHandover(null) }, [activeProjectId])

  const getStatusBadge = (status: HandoverStatus) => {
    switch (status) {
      case 'completed':
        return (
          <span className="badge badge-success">
            <CheckCircle size={12} /> Completed
          </span>
        )
      case 'verified':
        return (
          <span className="badge badge-success">
            <ShieldCheck size={12} /> Verified &amp; Approved
          </span>
        )
      case 'under_review':
        return (
          <span className="badge badge-warning">
            <Clock size={12} /> Under Review
          </span>
        )
      case 'submitted':
        return (
          <span className="badge badge-info">
            <Send size={12} /> Submitted
          </span>
        )
      case 'changes_requested':
        return (
          <span className="badge badge-critical">
            <AlertTriangle size={12} /> Changes Requested
          </span>
        )
      default:
        return (
          <span className="badge badge-neutral">
            <FileText size={12} /> Draft
          </span>
        )
    }
  }

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.employee_name || !form.role) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      await onCreateHandover({
        project_id: activeProjectId || undefined,
        employee_name: form.employee_name,
        role: form.role,
        department: form.department,
        transition_type: form.transition_type,
        project_name: form.project_name,
        project_description: form.project_description,
        key_responsibilities: form.responsibilities.split('\n').map((s) => s.trim()).filter(Boolean),
        critical_dependencies: form.dependencies.split('\n').map((s) => s.trim()).filter(Boolean),
        unresolved_blockers: form.blockers.split('\n').map((s) => s.trim()).filter(Boolean),
        completed_tasks: form.completed_tasks.split('\n').map((s) => s.trim()).filter(Boolean),
        pending_tasks: form.pending_tasks.split('\n').map((s) => s.trim()).filter(Boolean),
        important_notes: form.important_notes,
        recommended_next_actions: form.recommended_next_actions.split('\n').map((s) => s.trim()).filter(Boolean),
        repository_links: form.repository_links.split('\n').map((s) => s.trim()).filter(Boolean),
        documentation_links: form.documentation_links.split('\n').map((s) => s.trim()).filter(Boolean),
        database_references: form.database_references.split('\n').map((s) => s.trim()).filter(Boolean),
      })
      setShowCreateModal(false)
      setActionSuccess('Handover dossier created successfully in draft status.')
      setTimeout(() => setActionSuccess(null), 3000)
    } catch (err: any) {
      setActionError(err.message || 'Failed to create handover')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Open Handover Detail
  const handleOpenDetail = (item: HandoverItem) => {
    setSelectedHandover(item)
    setIsEditing(false)
    setEditNotes(item.important_notes || '')
    setActionError(null)
    setActionSuccess(null)
  }

  // Action: Employee Submits Handover
  const handleSubmitForReview = async () => {
    if (!selectedHandover) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await submitHandover(selectedHandover.id, currentUser.employeeName)
      setSelectedHandover(updated)
      setActionSuccess('Handover submitted to engineering management for formal review.')
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Submission failed')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Action: Manager Starts Review
  const handleStartReview = async () => {
    if (!selectedHandover) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await startHandoverReview(selectedHandover.id, currentUser.managerName)
      setSelectedHandover(updated)
      setActionSuccess('Review started. Status updated to under_review.')
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Action failed')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Action: Manager Approves Handover
  const handleApprove = async () => {
    if (!selectedHandover) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await approveHandover(
        selectedHandover.id,
        currentUser.managerName,
        'All technical dependencies and credentials verified.'
      )
      setSelectedHandover(updated)
      setActionSuccess('Handover verified and signed off by management!')
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Approval failed')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Action: Manager Requests Changes
  const handleConfirmChangeRequest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedHandover || !changeRequestReason.trim()) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await requestHandoverChanges(
        selectedHandover.id,
        currentUser.managerName,
        changeRequestReason.trim()
      )
      setSelectedHandover(updated)
      setShowChangeRequestModal(false)
      setChangeRequestReason('')
      setActionSuccess('Feedback submitted. Handover returned to employee for revisions.')
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Failed to request changes')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Action: Complete Handover
  const handleComplete = async () => {
    if (!selectedHandover) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await completeHandover(selectedHandover.id, currentUser.managerName)
      setSelectedHandover(updated)
      setActionSuccess('Handover transition marked as fully completed.')
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Completion failed')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Action: Open Assignment Modal & Load Eligible Assignees
  const handleOpenAssignModal = async () => {
    if (!selectedHandover) return
    setSelectedAssigneeId(selectedHandover.assigned_to || '')
    setAssignNotes('')
    setShowAssignModal(true)
    setLoadingAssignees(true)
    try {
      const list = await fetchEligibleAssignees()
      setAssignees(list)
      if (list.length > 0 && !selectedHandover.assigned_to) {
        setSelectedAssigneeId(list[0].id)
      }
    } catch (err: any) {
      setActionError(err.message || 'Failed to load eligible assignees')
    } finally {
      setLoadingAssignees(false)
    }
  }

  // Action: Confirm Assignment
  const handleConfirmAssignment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedHandover || !selectedAssigneeId) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await assignHandover(selectedHandover.id, selectedAssigneeId, assignNotes.trim() || undefined)
      setSelectedHandover(updated)
      setShowAssignModal(false)
      setActionSuccess(`Handover successfully assigned to ${updated.assigned_to_name || 'selected employee'}!`)
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Assignment failed')
    } finally {
      setSubmittingAction(false)
    }
  }

  const openEmployeePanel = async () => {
    setShowEmployeePanel(true)
    setActionError(null)
    try { setEmployeeRows((await fetchEligibleAssignees()).filter((user) => user.role === 'employee')) }
    catch (err) { setActionError(err instanceof Error ? err.message : 'Could not load employees.') }
  }

  const handleCreateEmployee = async (event: React.FormEvent) => {
    event.preventDefault()
    setCreatingEmployee(true)
    setActionError(null)
    try {
      const created = await createOrganizationEmployee(employeeForm)
      setEmployeeRows((rows) => [created, ...rows])
      setEmployeeForm({ full_name: '', email: '', password: '' })
      setActionSuccess(`Employee ${created.full_name} added to your organization.`)
    } catch (err) { setActionError(err instanceof Error ? err.message : 'Could not add employee.') }
    finally { setCreatingEmployee(false) }
  }

  // Action: Save Edits
  const handleSaveEdits = async () => {
    if (!selectedHandover) return
    setSubmittingAction(true)
    setActionError(null)
    try {
      const updated = await updateHandover(selectedHandover.id, {
        important_notes: editNotes,
      })
      setSelectedHandover(updated)
      setIsEditing(false)
      setActionSuccess('Dossier notes updated.')
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Update failed')
    } finally {
      setSubmittingAction(false)
    }
  }

  // Action: Toggle Task from Pending to Completed
  const handleToggleTaskCompleted = async (taskText: string) => {
    if (!selectedHandover) return
    if (selectedHandover.status === 'verified' || selectedHandover.status === 'completed') return

    const newPending = selectedHandover.pending_tasks.filter((t) => t !== taskText)
    const newCompleted = [...selectedHandover.completed_tasks, taskText]

    try {
      const updated = await updateHandover(selectedHandover.id, {
        pending_tasks: newPending,
        completed_tasks: newCompleted,
      })
      setSelectedHandover(updated)
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Failed to toggle task')
    }
  }

  // Action: Add Task
  const handleAddTask = async (type: 'completed' | 'pending' | 'blocker') => {
    if (!selectedHandover) return
    try {
      let updatePayload = {}
      if (type === 'completed' && newCompletedTask.trim()) {
        updatePayload = { completed_tasks: [...selectedHandover.completed_tasks, newCompletedTask.trim()] }
        setNewCompletedTask('')
      } else if (type === 'pending' && newPendingTask.trim()) {
        updatePayload = { pending_tasks: [...selectedHandover.pending_tasks, newPendingTask.trim()] }
        setNewPendingTask('')
      } else if (type === 'blocker' && newBlocker.trim()) {
        updatePayload = { unresolved_blockers: [...selectedHandover.unresolved_blockers, newBlocker.trim()] }
        setNewBlocker('')
      }

      const updated = await updateHandover(selectedHandover.id, updatePayload)
      setSelectedHandover(updated)
      if (onRefreshHandovers) await onRefreshHandovers()
    } catch (err: any) {
      setActionError(err.message || 'Failed to add item')
    }
  }

  // Action: Open Markdown Export
  const handleExport = async (item: HandoverItem) => {
    try {
      const res = await exportHandoverMarkdown(item.id)
      setExportMarkdown(res.markdown_content)
      setShowExportModal(true)
    } catch (err: any) {
      alert(err.message || 'Export failed')
    }
  }

  return (
    <div className="section-container">
      {/* View Header with Persona Switcher */}
      <div className="section-header">
        <div>
          <h2>{managerMode ? 'Employee handovers' : 'Prepare your departure handover'}</h2>
          <p className="section-desc">
            {managerMode ? 'Review employee updates and important notes, then share handovers with the employees responsible for the work.' : 'Leaving the organization or moving on from your role? Record your responsibilities, completed and remaining work, key links, and important notes before your last day.'}
          </p>
        </div>

        <div className="handover-header-actions">
          {!managerMode && <button className="primary-btn" onClick={() => setShowCreateModal(true)}>
            <PlusCircle size={16} />
            <span>Create departure handover</span>
          </button>}
        </div>
      </div>

      {!managerMode && <div className="employee-departure-note"><FileText size={18} /><div><strong>Prepare before you leave</strong><p>Start a draft now, add accurate work details and attach relevant notes or runbooks. Submit it when ready so your manager can review and approve it. Do not include passwords, tokens, or other secrets.</p></div></div>}

      {managerMode && <section className="manager-role-groups card"><div className="manager-project-select"><label htmlFor="manager-project-select">Select project</label><select id="manager-project-select" value={activeProjectId || ''} onChange={(event) => { const id = event.target.value; onProjectChange?.(id, managerProjects.find((project) => project.id === id)?.name); setRoleFilter('all') }}><option value="">Choose a project…</option>{managerProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div><div className="card-header-clean"><div><h3>Role-based project segregation</h3><p>Select a project to group its employee handovers by recorded role. Open a handover to share it with an employee.</p></div><div className="manager-role-controls"><button type="button" className="secondary-btn" onClick={() => void openEmployeePanel()}><UsersRound size={15} /> Manage employees</button><button type="button" className={`secondary-btn ${autoRoleSegregation ? 'active' : ''}`} disabled={!activeProjectId} onClick={() => { setAutoRoleSegregation((value) => !value); setRoleFilter('all') }}>{autoRoleSegregation ? 'Automatic role grouping: On' : 'Automatic role grouping: Off'}</button>{autoRoleSegregation && <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} aria-label="Filter handovers by employee role"><option value="all">All roles ({scopedHandovers.length})</option>{roleGroups.map((role) => <option key={role} value={role}>{role} ({scopedHandovers.filter((item) => item.role.trim() === role).length})</option>)}</select>}</div></div>{autoRoleSegregation && <div className="manager-role-chips">{roleGroups.map((role) => <button key={role} className={roleFilter === role ? 'active' : ''} onClick={() => setRoleFilter(roleFilter === role ? 'all' : role)}><span>{role}</span><strong>{scopedHandovers.filter((item) => item.role.trim() === role).length}</strong></button>)}{!activeProjectId ? <p className="empty-subtext">Choose a project to see employee role groups.</p> : !roleGroups.length && <p className="empty-subtext">No employee role groups are recorded for this project yet.</p>}</div>}</section>}

      {/* Global Alerts */}
      {actionSuccess && (
        <div className="alert-banner alert-success">
          <CheckCircle size={16} />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="alert-banner alert-critical">
          <AlertTriangle size={16} />
          <span>{actionError}</span>
        </div>
      )}

      {/* Handover Filter Toolbar */}
      <div className="flex items-center gap-2 mb-4">
        <button
          className={`persona-btn ${filterTab === 'all' ? 'active' : ''}`}
          onClick={() => setFilterTab('all')}
        >
          <span>All Dossiers ({scopedHandovers.length})</span>
        </button>
        <button
          className={`persona-btn ${filterTab === 'assigned_to_me' ? 'active' : ''}`}
          onClick={() => setFilterTab('assigned_to_me')}
        >
          <UserCheck size={14} />
          <span>Assigned ({scopedHandovers.filter((h) => !!h.assigned_to).length})</span>
        </button>
        <button
          className={`persona-btn ${filterTab === 'unassigned' ? 'active' : ''}`}
          onClick={() => setFilterTab('unassigned')}
        >
          <Clock size={14} />
          <span>Unassigned ({scopedHandovers.filter((h) => !h.assigned_to).length})</span>
        </button>
      </div>

      {/* Handover Cards Grid */}
      <div className="cards-grid">
        {scopedHandovers.length === 0 && <section className="employee-departure-empty card"><FileText size={22} /><h3>{managerMode ? (activeProjectId ? 'No employee handovers for this project' : 'Select a project to review handovers') : 'No departure handover yet'}</h3><p>{managerMode ? 'Employee-submitted handovers for the selected project will appear here.' : 'Create a draft before your last day. Add completed work, remaining tasks, important notes, and any supporting files, then submit it for manager review.'}</p>{!managerMode && <button className="primary-btn" onClick={() => setShowCreateModal(true)}><PlusCircle size={15} /> Create your handover</button>}</section>}
        {scopedHandovers
          .filter((item) => {
            if (managerMode && autoRoleSegregation && roleFilter !== 'all' && item.role.trim() !== roleFilter) return false
            if (filterTab === 'assigned_to_me') return !!item.assigned_to
            if (filterTab === 'unassigned') return !item.assigned_to
            return true
          })
          .map((item) => (
          <div
            key={item.id}
            className={`card card-handover clickable-card ${selectedHandover?.id === item.id ? 'active-card' : ''}`}
            onClick={() => handleOpenDetail(item)}
          >
            <div className="card-top">
              <div>
                <span className="card-tag">{item.department}</span>
                <h3 className="card-title">{item.employee_name}</h3>
                <p className="card-sub">{item.role}</p>
              </div>
              <div className="flex-col items-end">
                {getStatusBadge(item.status)}
                <span className="readiness-meter-pill">
                  Readiness: <strong>{item.readiness_score}%</strong>
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 mt-2">
              {item.project_name && (
                <div className="project-badge-ribbon">
                  <Layers size={13} />
                  <span>{item.project_name}</span>
                </div>
              )}
              {item.assigned_to_name ? (
                <span className="badge badge-success flex items-center gap-1 text-xs">
                  <UserCheck size={12} />
                  <span>Assignee: {item.assigned_to_name}</span>
                </span>
              ) : (
                <span className="badge badge-warning flex items-center gap-1 text-xs">
                  <span>Unassigned</span>
                </span>
              )}
            </div>

            {/* Manager Feedback Banner if changes requested */}
            {item.status === 'changes_requested' && item.review_notes && (
              <div className="manager-feedback-card">
                <div className="feedback-head">
                  <AlertTriangle size={14} className="text-red-400" />
                  <strong>Changes Requested by {item.reviewed_by || 'Manager'}:</strong>
                </div>
                <p className="feedback-body">{item.review_notes}</p>
              </div>
            )}

            <div className="card-content-block">
              <h4>Key Tasks &amp; Responsibilities</h4>
              <ul className="bullet-list">
                {item.key_responsibilities.slice(0, 3).map((resp, i) => (
                  <li key={i}>{resp}</li>
                ))}
              </ul>
            </div>

            <div className="card-bottom-bar">
              <div className="meta-counts">
                <span>Completed: {item.completed_tasks?.length || 0}</span>
                <span>Pending: {item.pending_tasks?.length || 0}</span>
                {item.unresolved_blockers?.length > 0 && (
                  <span className="text-red-400">Blockers: {item.unresolved_blockers.length}</span>
                )}
                {(() => {
                  const itemDocs = documents.filter((d) => d.handover_id === item.id)
                  return itemDocs.length > 0 ? (
                    <span className="doc-count-badge flex items-center gap-1">
                      <FileText size={11} />
                      <span>{itemDocs.length} {itemDocs.length === 1 ? 'doc' : 'docs'}</span>
                    </span>
                  ) : (
                    <span className="doc-missing-badge flex items-center gap-1 text-amber-400">
                      <AlertTriangle size={11} />
                      <span>0 docs</span>
                    </span>
                  )
                })()}
              </div>
              <button
                className="text-link flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  handleOpenDetail(item)
                }}
              >
                <span>Inspect Dossier</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* DETAIL DRAWER / MODAL */}
      {selectedHandover && (
        <div className="modal-overlay" onClick={() => setSelectedHandover(null)}>
          <div className="modal-content modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="drawer-title-group">
                <div className="flex items-center gap-2">
                  <span className="card-tag">{selectedHandover.department}</span>
                  {getStatusBadge(selectedHandover.status)}
                  <span className="readiness-badge">
                    Readiness: <strong>{selectedHandover.readiness_score}%</strong>
                  </span>
                </div>
                <h3>{selectedHandover.employee_name} — Handover Dossier</h3>
                <p className="drawer-subtitle">
                  {selectedHandover.role} &bull; {selectedHandover.project_name || 'Primary Project'}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-muted">Assigned Engineer:</span>
                  {selectedHandover.assigned_to_name ? (
                    <span className="badge badge-success flex items-center gap-1 text-xs">
                      <UserCheck size={12} />
                      <span>{selectedHandover.assigned_to_name} ({selectedHandover.assigned_to_email || 'Assigned'})</span>
                    </span>
                  ) : (
                    <span className="badge badge-warning flex items-center gap-1 text-xs">
                      <Clock size={12} />
                      <span>Unassigned</span>
                    </span>
                  )}
                </div>
              </div>
              <button className="close-btn" onClick={() => setSelectedHandover(null)}>
                <X size={20} />
              </button>
            </div>

            <div className="drawer-body">
              {/* Reviewer Feedback Callout */}
              {selectedHandover.review_notes && (
                <div className={`review-feedback-banner ${selectedHandover.status}`}>
                  <div className="feedback-author">
                    <MessageSquare size={16} />
                    <span>
                      {selectedHandover.review_decision === 'approved' ? 'Manager Approval Note' : 'Manager Revision Request'} by{' '}
                      <strong>{selectedHandover.reviewed_by}</strong>:
                    </span>
                  </div>
                  <p className="feedback-text">{selectedHandover.review_notes}</p>
                </div>
              )}

              {/* Status Action Workflow Bar */}
              <div className="workflow-action-bar">
                <div className="action-bar-label">
                  <span>Current Workflow State:</span>
                  <span className="state-pill">{selectedHandover.status.toUpperCase()}</span>
                </div>

                <div className="action-button-group">
                  {/* EMPLOYEE ACTIONS */}
                  {activePersona === 'employee' && (
                    <>
                      {(selectedHandover.status === 'draft' || selectedHandover.status === 'changes_requested') && (
                        <button
                          className="primary-btn"
                          disabled={submittingAction}
                          onClick={handleSubmitForReview}
                        >
                          <Send size={15} />
                          <span>{selectedHandover.status === 'changes_requested' ? 'Resubmit Handover' : 'Submit for Manager Review'}</span>
                        </button>
                      )}
                      {selectedHandover.status === 'submitted' && (
                        <span className="status-note text-amber-400">
                          <Clock size={14} /> Awaiting manager review
                        </span>
                      )}
                    </>
                  )}

                  {/* MANAGER ACTIONS */}
                  {activePersona === 'manager' && (
                    <>
                      {selectedHandover.status === 'submitted' && (
                        <button
                          className="secondary-btn"
                          disabled={submittingAction}
                          onClick={handleStartReview}
                        >
                          <Clock size={15} />
                          <span>Start Review</span>
                        </button>
                      )}

                      {(selectedHandover.status === 'submitted' || selectedHandover.status === 'under_review') && (
                        <>
                          <button
                            className="danger-btn"
                            disabled={submittingAction}
                            onClick={() => setShowChangeRequestModal(true)}
                          >
                            <AlertTriangle size={15} />
                            <span>Request Changes</span>
                          </button>
                          <button
                            className="success-btn"
                            disabled={submittingAction}
                            onClick={handleApprove}
                          >
                            <ShieldCheck size={15} />
                            <span>Verify &amp; Approve</span>
                          </button>
                        </>
                      )}

                      {selectedHandover.status === 'verified' && (
                        <button
                          className="primary-btn"
                          disabled={submittingAction}
                          onClick={handleComplete}
                        >
                          <FileCheck2 size={15} />
                          <span>Complete &amp; Archive Handover</span>
                        </button>
                      )}

                      {/* Manager Assignment Action */}
                      <button
                        className="secondary-btn"
                        disabled={submittingAction}
                        onClick={handleOpenAssignModal}
                      >
                        <UserCheck size={15} />
                        <span>{managerMode ? (selectedHandover.assigned_to ? 'Reassign & share' : 'Share with employee') : (selectedHandover.assigned_to ? 'Reassign Handover' : 'Assign to New Joiner')}</span>
                      </button>
                    </>
                  )}

                  {/* EXPORT ACTION */}
                  <button
                    className="secondary-btn"
                    onClick={() => handleExport(selectedHandover)}
                  >
                    <Download size={15} />
                    <span>Export Markdown</span>
                  </button>
                </div>
              </div>

              {/* SECTION: Completed & Pending Tasks */}
              <div className="drawer-section">
                <h4>Completed Work &amp; Evidence ({selectedHandover.completed_tasks?.length || 0})</h4>
                <div className="task-list">
                  {selectedHandover.completed_tasks?.map((task, idx) => (
                    <div key={idx} className="task-item completed">
                      <CheckSquare size={16} className="text-emerald-400" />
                      <span>{task}</span>
                    </div>
                  ))}
                  {selectedHandover.completed_tasks?.length === 0 && (
                    <p className="empty-subtext">No completed tasks recorded yet.</p>
                  )}
                </div>

                {activePersona === 'employee' && selectedHandover.status !== 'verified' && selectedHandover.status !== 'completed' && (
                  <div className="quick-add-row">
                    <input
                      type="text"
                      placeholder="Add completed task or pull request evidence..."
                      value={newCompletedTask}
                      onChange={(e) => setNewCompletedTask(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddTask('completed')}
                    />
                    <button className="secondary-btn" onClick={() => handleAddTask('completed')}>
                      Add Task
                    </button>
                  </div>
                )}
              </div>

              <div className="drawer-section">
                <h4>Pending Work &amp; Incomplete Items ({selectedHandover.pending_tasks?.length || 0})</h4>
                <div className="task-list">
                  {selectedHandover.pending_tasks?.map((task, idx) => (
                    <div key={idx} className="task-item pending">
                      <button
                        className="check-toggle-btn"
                        title="Mark as completed"
                        onClick={() => handleToggleTaskCompleted(task)}
                      >
                        <Square size={16} />
                      </button>
                      <span>{task}</span>
                    </div>
                  ))}
                  {selectedHandover.pending_tasks?.length === 0 && (
                    <p className="empty-subtext text-emerald-400">Zero pending tasks remaining.</p>
                  )}
                </div>

                {activePersona === 'employee' && selectedHandover.status !== 'verified' && selectedHandover.status !== 'completed' && (
                  <div className="quick-add-row">
                    <input
                      type="text"
                      placeholder="Add pending handover task..."
                      value={newPendingTask}
                      onChange={(e) => setNewPendingTask(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddTask('pending')}
                    />
                    <button className="secondary-btn" onClick={() => handleAddTask('pending')}>
                      Add Pending
                    </button>
                  </div>
                )}
              </div>

              {/* SECTION: Critical Dependencies & Blockers */}
              <div className="drawer-columns-grid">
                <div className="drawer-section">
                  <h4>Critical External Dependencies</h4>
                  <ul className="bullet-list dep-list">
                    {selectedHandover.critical_dependencies?.map((dep, i) => (
                      <li key={i}>{dep}</li>
                    ))}
                  </ul>
                </div>

                <div className="drawer-section">
                  <h4>Unresolved Blockers &amp; Knowledge Gaps</h4>
                  <div className="task-list">
                    {selectedHandover.unresolved_blockers?.map((b, i) => (
                      <div key={i} className="task-item blocker">
                        <AlertTriangle size={15} className="text-red-400" />
                        <span>{b}</span>
                      </div>
                    ))}
                    {selectedHandover.unresolved_blockers?.length === 0 && (
                      <p className="empty-subtext text-emerald-400">No unresolved blockers.</p>
                    )}
                  </div>
                </div>
              </div>

              {/* SECTION: Repository & Technical Links */}
              <div className="drawer-section">
                <h4>Technical Links &amp; References</h4>
                <div className="links-group">
                  {selectedHandover.repository_links?.map((link, idx) => (
                    <a key={idx} href={link} target="_blank" rel="noreferrer" className="tech-link-pill">
                      <ExternalLink size={13} />
                      <span>{link}</span>
                    </a>
                  ))}
                  {selectedHandover.documentation_links?.map((link, idx) => (
                    <a key={idx} href={link} target="_blank" rel="noreferrer" className="tech-link-pill doc">
                      <FileText size={13} />
                      <span>{link}</span>
                    </a>
                  ))}
                  {selectedHandover.database_references?.map((ref, idx) => (
                    <span key={idx} className="tech-link-pill db">
                      <Layers size={13} />
                      <code>{ref}</code>
                    </span>
                  ))}
                </div>
              </div>

              {/* SECTION: Notes & Caveats */}
              <div className="drawer-section">
                <div className="flex justify-between items-center mb-2">
                  <h4>Important Notes &amp; Architectural Caveats</h4>
                  {!isEditing && selectedHandover.status !== 'verified' && selectedHandover.status !== 'completed' && (
                    <button className="text-link flex items-center gap-1" onClick={() => setIsEditing(true)}>
                      <Edit3 size={13} />
                      <span>Edit Notes</span>
                    </button>
                  )}
                </div>

                {isEditing ? (
                  <div className="edit-notes-box">
                    <textarea
                      rows={4}
                      value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)}
                    />
                    <div className="flex gap-2 justify-end mt-2">
                      <button className="secondary-btn" onClick={() => setIsEditing(false)}>
                        Cancel
                      </button>
                      <button className="primary-btn" onClick={handleSaveEdits}>
                        Save Changes
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="notes-box">{selectedHandover.important_notes || 'No additional notes provided.'}</p>
                )}
              </div>

              {/* SECTION: Attached Handover Documents (Module 1: Knowledge Integration Pipeline) */}
              <div className="drawer-section">
                <div className="flex justify-between items-center mb-2">
                  <div className="flex items-center gap-2">
                    <h4>Attached Handover Documentation &amp; Runbooks</h4>
                    <span className="badge-count">
                      {documents.filter((d) => d.handover_id === selectedHandover.id).length}
                    </span>
                  </div>
                  <button
                    className="text-link text-xs flex items-center gap-1"
                    onClick={loadDocuments}
                    title="Refresh Documents"
                  >
                    <RefreshCw size={12} />
                    <span>Sync</span>
                  </button>
                </div>

                {/* Manager Missing Documentation Warning */}
                {documents.filter((d) => d.handover_id === selectedHandover.id).length === 0 && activePersona === 'manager' && (
                  <div className="missing-doc-warning">
                    <AlertTriangle size={18} className="text-amber-400 flex-shrink-0" />
                    <div>
                      <strong>Missing Technical Documentation:</strong> This handover dossier has no uploaded architecture runbooks, system manuals, or READMEs. As a reviewing engineering manager, ensure technical knowledge is captured before final verification.
                    </div>
                  </div>
                )}

                {/* Document Upload Zone */}
                {selectedHandover.status !== 'completed' && (
                  <div className="doc-upload-box">
                    <label className="upload-dropzone">
                      <input
                        type="file"
                        accept=".pdf,.md,.markdown,.txt"
                        disabled={uploadingDoc}
                        onChange={handleFileUpload}
                        className="hidden-file-input"
                      />
                      <div className="dropzone-content">
                        <UploadCloud size={24} className="text-indigo-400" />
                        <div>
                          <span className="upload-link-text">
                            {uploadingDoc ? 'Uploading, parsing and chunking document...' : 'Click to attach architecture runbooks or system docs'}
                          </span>
                          <p className="upload-subtext">PDF, Markdown (.md), and TXT files supported (max 25 MB). Automatically chunked and preserved.</p>
                        </div>
                      </div>
                    </label>

                    {uploadingDoc && (
                      <div className="upload-progress-banner">
                        <span className="spinner" />
                        <span>Validating file structure, extracting plain text, and generating indexed chunks...</span>
                      </div>
                    )}

                    {uploadError && (
                      <div className="upload-error-banner flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <AlertTriangle size={15} className="text-red-400 flex-shrink-0" />
                          <span>{uploadError}</span>
                        </div>
                        <button className="text-link text-xs" onClick={() => setUploadError(null)}>
                          Dismiss
                        </button>
                      </div>
                    )}

                    {uploadSuccess && (
                      <div className="upload-success-banner flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CheckCircle size={15} className="text-emerald-400 flex-shrink-0" />
                          <span>{uploadSuccess}</span>
                        </div>
                        <button className="text-link text-xs" onClick={() => setUploadSuccess(null)}>
                          Dismiss
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Document List */}
                <div className="doc-list-grid">
                  {documents
                    .filter((d) => d.handover_id === selectedHandover.id)
                    .map((doc) => (
                      <div key={doc.id} className="doc-card-row">
                        <div className="doc-info-group">
                          <div
                            className={`doc-type-icon ${
                              doc.filename.endsWith('.pdf')
                                ? 'pdf'
                                : doc.filename.endsWith('.md')
                                ? 'md'
                                : 'txt'
                            }`}
                          >
                            {doc.filename.endsWith('.pdf') ? (
                              <FileText size={18} />
                            ) : doc.filename.endsWith('.md') ? (
                              <FileCode size={18} />
                            ) : (
                              <FileText size={18} />
                            )}
                          </div>
                          <div className="doc-meta-col">
                            <span className="doc-title">{doc.filename}</span>
                            <div className="doc-submeta">
                              <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                              <span>&bull;</span>
                              <span>{new Date(doc.uploaded_at).toLocaleDateString()}</span>
                              <span>&bull;</span>
                              <span className={`doc-status-tag ${doc.processing_status}`}>
                                {doc.processing_status === 'processed' && <CheckCircle size={11} />}
                                {doc.processing_status === 'processing' && <Clock size={11} />}
                                {doc.processing_status === 'failed' && <AlertTriangle size={11} />}
                                {doc.processing_status.toUpperCase()} ({doc.chunk_count}{' '}
                                {doc.chunk_count === 1 ? 'chunk' : 'chunks'})
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="doc-actions-group">
                          <button
                            className="secondary-btn btn-sm flex items-center gap-1"
                            onClick={() => handleInspectDoc(doc)}
                            title="Inspect Extracted Text & Chunks"
                          >
                            <Eye size={13} />
                            <span>Inspect</span>
                          </button>
                          {selectedHandover.status !== 'completed' && (
                            <button
                              className="delete-icon-btn"
                              onClick={() => handleDeleteDoc(doc.id)}
                              title="Delete Document"
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}

                  {documents.filter((d) => d.handover_id === selectedHandover.id).length === 0 && (
                    <p className="empty-subtext text-muted">
                      No documents attached to this handover. Upload technical specs or runbooks above.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Request Changes (Manager) */}
      {showChangeRequestModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3>Request Revisions on Handover</h3>
              <button className="close-btn" onClick={() => setShowChangeRequestModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleConfirmChangeRequest}>
              <div className="form-group">
                <label>Reviewer / Manager Name</label>
                <input type="text" value={currentUser.managerName} disabled />
              </div>
              <div className="form-group">
                <label>Reason for Requesting Changes (Mandatory) *</label>
                <textarea
                  rows={4}
                  required
                  placeholder="Explain exactly what documentation, evidence, or task resolution is required from the employee..."
                  value={changeRequestReason}
                  onChange={(e) => setChangeRequestReason(e.target.value)}
                />
              </div>
              <div className="modal-footer">
                <button type="button" className="secondary-btn" onClick={() => setShowChangeRequestModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="danger-btn" disabled={submittingAction}>
                  {submittingAction ? 'Submitting...' : 'Send Revision Request'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showEmployeePanel && managerMode && <div className="modal-overlay" onClick={() => setShowEmployeePanel(false)}><div className="modal-content manager-employee-modal" onClick={(event) => event.stopPropagation()}><div className="modal-header"><div><h3>Organization employees</h3><p className="modal-desc">Add an employee account to your organization so handovers can be shared with them.</p></div><button className="close-btn" onClick={() => setShowEmployeePanel(false)}><X size={20} /></button></div><div className="manager-employee-list">{employeeRows.map((employee) => <div key={employee.id}><UsersRound size={16} /><span><strong>{employee.full_name}</strong><small>{employee.email}</small></span></div>)}{!employeeRows.length && <p className="empty-subtext">No employee accounts are listed yet.</p>}</div><form className="manager-add-employee-form" onSubmit={(event) => void handleCreateEmployee(event)}><h4>Add employee</h4><label>Full name<input required maxLength={255} value={employeeForm.full_name} onChange={(event) => setEmployeeForm({ ...employeeForm, full_name: event.target.value })} /></label><label>Email address<input required type="email" value={employeeForm.email} onChange={(event) => setEmployeeForm({ ...employeeForm, email: event.target.value })} /></label><label>Temporary password<input required type="password" minLength={8} autoComplete="new-password" value={employeeForm.password} onChange={(event) => setEmployeeForm({ ...employeeForm, password: event.target.value })} /><small>At least 8 characters. Share it with the employee securely.</small></label><button className="primary-btn" type="submit" disabled={creatingEmployee}>{creatingEmployee ? 'Adding…' : 'Add employee'}</button></form></div></div>}

      {/* MODAL: Assign Handover to New Joiner (Manager) */}
      {showAssignModal && selectedHandover && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Assign Handover to New Joiner</h3>
              <button className="close-btn" onClick={() => setShowAssignModal(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleConfirmAssignment}>
              <div className="modal-body">
                <p className="modal-desc">
                  Assign <strong>{selectedHandover.employee_name}</strong>'s transition dossier to an incoming engineer within your organization.
                </p>

                <div className="form-group">
                  <label>Select Team Member (Same Organization) *</label>
                  {loadingAssignees ? (
                    <p className="text-sm text-muted">Loading organization members...</p>
                  ) : (
                    <select
                      className="form-input"
                      value={selectedAssigneeId}
                      onChange={(e) => setSelectedAssigneeId(e.target.value)}
                      required
                    >
                      <option value="">-- Choose an eligible employee --</option>
                      {assignees.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.full_name} ({a.email}) - {a.role}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="form-group">
                  <label>Assignment Notes / Onboarding Guidance (Optional)</label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Please review key responsibilities and complete the environment recreation checklist."
                    value={assignNotes}
                    onChange={(e) => setAssignNotes(e.target.value)}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-btn" onClick={() => setShowAssignModal(false)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="primary-btn"
                  disabled={submittingAction || !selectedAssigneeId}
                >
                  <CheckCircle size={15} />
                  <span>{submittingAction ? 'Assigning...' : 'Confirm Assignment'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: Markdown Export */}
      {showExportModal && selectedHandover && (
        <div className="modal-overlay" onClick={() => setShowExportModal(false)}>
          <div className="modal-content modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Handover Markdown Dossier ({selectedHandover.employee_name})</h3>
              <div className="flex gap-2 items-center">
                <a
                  href={getHandoverDownloadUrl(selectedHandover.id)}
                  download
                  className="primary-btn"
                >
                  <Download size={14} />
                  <span>Download .md</span>
                </a>
                <button className="close-btn" onClick={() => setShowExportModal(false)}>
                  &times;
                </button>
              </div>
            </div>
            <div className="markdown-preview-container">
              <pre>{exportMarkdown}</pre>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Create New Handover */}
      {showCreateModal && (
        <div className="modal-overlay">
          <div className="modal-content modal-lg">
            <div className="modal-header">
              <h3>{managerMode ? 'Create Handover Dossier' : 'Create your departure handover'}</h3>
              <button className="close-btn" onClick={() => setShowCreateModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateSubmit}>
              <div className="form-grid-2">
                <div className="form-group">
                  <label>Your name *</label>
                  <input
                    type="text"
                    required
                    readOnly={!managerMode}
                    value={form.employee_name}
                    onChange={(e) => setForm({ ...form, employee_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Your role / Job Title *</label>
                  <input
                    type="text"
                    required
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-grid-2">
                <div className="form-group">
                  <label>Department</label>
                  <input
                    type="text"
                    value={form.department}
                    onChange={(e) => setForm({ ...form, department: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Transition Type</label>
                  <select
                    value={form.transition_type}
                    onChange={(e) => setForm({ ...form, transition_type: e.target.value })}
                  >
                    <option value="resignation">Resignation</option>
                    <option value="retirement">Retirement</option>
                    <option value="internal_transition">Internal Role Transition</option>
                    <option value="project_transfer">Project Transfer</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Primary Project Name</label>
                <input
                  type="text"
                  value={form.project_name}
                  onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Key Responsibilities (one per line) *</label>
                <textarea
                  rows={3}
                  required
                  value={form.responsibilities}
                  onChange={(e) => setForm({ ...form, responsibilities: e.target.value })}
                />
              </div>

              <div className="form-grid-2">
                <div className="form-group">
                  <label>Completed Tasks &amp; Evidence (one per line)</label>
                  <textarea
                    rows={3}
                    value={form.completed_tasks}
                    onChange={(e) => setForm({ ...form, completed_tasks: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Pending / Incomplete Tasks (one per line)</label>
                  <textarea
                    rows={3}
                    value={form.pending_tasks}
                    onChange={(e) => setForm({ ...form, pending_tasks: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-grid-2">
                <div className="form-group">
                  <label>Critical External Dependencies</label>
                  <textarea
                    rows={2}
                    value={form.dependencies}
                    onChange={(e) => setForm({ ...form, dependencies: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Unresolved Blockers / Knowledge Gaps</label>
                  <textarea
                    rows={2}
                    value={form.blockers}
                    onChange={(e) => setForm({ ...form, blockers: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Repository &amp; Documentation Links (one per line)</label>
                <textarea
                  rows={2}
                  value={form.repository_links}
                  onChange={(e) => setForm({ ...form, repository_links: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Important Notes for Your Manager &amp; Successor</label>
                <textarea
                  rows={2}
                  placeholder="Record decisions, operational cautions, recurring issues, or details your successor should know. Never enter passwords or secret values."
                  value={form.important_notes}
                  onChange={(e) => setForm({ ...form, important_notes: e.target.value })}
                />
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-btn" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="primary-btn" disabled={submittingAction}>
                  {submittingAction ? 'Saving...' : 'Save Draft Handover'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: Document Content & Chunks Inspector (Module 1) */}
      {inspectingDoc && (
        <div className="modal-overlay" onClick={() => setInspectingDoc(null)}>
          <div className="modal-content modal-lg doc-inspector-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="drawer-title-group">
                <div className="flex items-center gap-2">
                  <span className={`doc-status-tag ${inspectingDoc.processing_status}`}>
                    {inspectingDoc.processing_status.toUpperCase()}
                  </span>
                  <span className="text-xs text-muted">
                    SHA-256: <code>{inspectingDoc.file_hash?.slice(0, 16)}...</code>
                  </span>
                </div>
                <h3>{inspectingDoc.filename}</h3>
                <p className="drawer-subtitle">
                  {(inspectingDoc.file_size / 1024).toFixed(1)} KB &bull; {inspectingChunks.length} Chunks Generated &bull; Attached to {selectedHandover?.employee_name}
                </p>
              </div>
              <button className="close-btn" onClick={() => setInspectingDoc(null)}>
                <X size={20} />
              </button>
            </div>

            <div className="modal-body">
              {/* Inspection Tabs */}
              <div className="doc-inspector-tabs">
                <button
                  className={`tab-btn ${docViewTab === 'text' ? 'active' : ''}`}
                  onClick={() => setDocViewTab('text')}
                >
                  <FileText size={15} />
                  <span>Extracted Plain Text</span>
                </button>
                <button
                  className={`tab-btn ${docViewTab === 'chunks' ? 'active' : ''}`}
                  onClick={() => setDocViewTab('chunks')}
                >
                  <Layers size={15} />
                  <span>Document Chunks ({inspectingChunks.length})</span>
                </button>
              </div>

              {loadingDocDetails ? (
                <div className="loading-banner my-4">
                  <span className="spinner" />
                  <span>Retrieving document content and chunks...</span>
                </div>
              ) : docViewTab === 'text' ? (
                <div className="extracted-text-viewer">
                  <div className="viewer-toolbar">
                    <span className="text-xs text-muted">
                      Extracted Text Content ({inspectingDoc.raw_text?.length || 0} characters)
                    </span>
                  </div>
                  <pre className="extracted-text-content">{inspectingDoc.raw_text || '(No text extracted)'}</pre>
                </div>
              ) : (
                <div className="chunks-list-viewer">
                  {inspectingChunks.map((chunk) => (
                    <div key={chunk.id} className="chunk-card">
                      <div className="chunk-card-header">
                        <span className="chunk-index-pill">Chunk #{chunk.chunk_index + 1}</span>
                        {chunk.page_number && (
                          <span className="chunk-page-pill">Page {chunk.page_number}</span>
                        )}
                        <span className="chunk-token-count">~{chunk.token_count || 0} tokens</span>
                      </div>
                      <p className="chunk-card-body">{chunk.chunk_text}</p>
                    </div>
                  ))}
                  {inspectingChunks.length === 0 && (
                    <p className="empty-subtext text-muted py-4">No chunks generated for this document.</p>
                  )}
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button className="secondary-btn" onClick={() => setInspectingDoc(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
