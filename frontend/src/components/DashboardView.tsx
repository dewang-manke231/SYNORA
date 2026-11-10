import React from 'react'
import type { HandoverItem, RiskAlert, KnowledgeNode } from '../types'
import { fetchProjects } from '../services/api'
import {
  ShieldAlert,
  BookOpen,
  UserCheck,
  AlertTriangle,
  ArrowUpRight,
  Compass,
  FolderKanban,
  CheckCircle2,
  CircleDashed,
  FileText,
  ListTodo,
} from 'lucide-react'

interface DashboardViewProps {
  handovers: HandoverItem[]
  risks: RiskAlert[]
  nodes: KnowledgeNode[]
  radarGaps: import('../types').KnowledgeGapItem[]
  setActiveTab: (tab: string) => void
  managerMode?: boolean
  managerName?: string
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  handovers,
  risks,
  nodes,
  radarGaps,
  setActiveTab,
  managerMode = false,
  managerName = 'Manager',
}) => {
  const [projectCount, setProjectCount] = React.useState<number | null>(null)
  React.useEffect(() => {
    if (!managerMode) return
    fetchProjects().then((projects) => setProjectCount(projects.length)).catch(() => setProjectCount(null))
  }, [managerMode])
  const criticalRisks = risks.filter((r) => r.risk_level === 'critical')
  const inProgressHandovers = handovers.filter((h) => h.status !== 'completed')
  const completedTasks = handovers.flatMap((h) => h.completed_tasks || []).length
  const remainingTasks = handovers.flatMap((h) => h.pending_tasks || []).length
  const totalTasks = completedTasks + remainingTasks
  const completion = totalTasks ? Math.round((completedTasks / totalTasks) * 100) : null
  const priorityItems = [
    ...risks.filter((r) => !r.is_resolved).map((r) => ({ id: `s-${r.id}`, title: r.description, project: r.project_name, priority: r.risk_level, action: r.recommended_action, source: 'Sentinel' })),
    ...radarGaps.filter((gap) => !gap.is_resolved).map((gap) => ({ id: `r-${gap.id}`, title: gap.description, project: gap.module_name, priority: gap.severity, action: gap.recommended_remediation || 'Review this knowledge gap', source: 'Radar' })),
  ].sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority))
  const completedWork = handovers.flatMap((h) => (h.completed_tasks || []).map((task) => ({ id: `${h.id}-${task}`, task, project: h.project_name || h.employee_name })))
  const remainingWork = handovers.flatMap((h) => (h.pending_tasks || []).map((task) => ({ id: `${h.id}-${task}`, task, project: h.project_name || h.employee_name })))

  if (managerMode) return <div className="section-container manager-dashboard">
    <section className="manager-welcome card"><span className="hero-badge">MANAGER WORKSPACE</span><h2>Team projects and handovers</h2><p>Welcome, {managerName}. Review employee updates, keep important project notes together, and share each handover with the right role.</p><div className="manager-dashboard-actions"><button className="primary-btn" onClick={() => setActiveTab('projects')}><FolderKanban size={16} /> Manage projects</button><button className="secondary-btn" onClick={() => setActiveTab('handovers')}><UserCheck size={16} /> Employee handovers</button></div></section>
    <div className="manager-summary-grid"><button className="manager-summary-card" onClick={() => setActiveTab('projects')}><FolderKanban size={18} /><span>Projects</span><strong>{projectCount ?? '—'}</strong></button><button className="manager-summary-card" onClick={() => setActiveTab('handovers')}><UserCheck size={18} /><span>Employee handovers</span><strong>{handovers.length}</strong></button><button className="manager-summary-card" onClick={() => setActiveTab('handovers')}><CircleDashed size={18} /><span>Pending review / work</span><strong>{handovers.filter((h) => h.status !== 'completed').length + remainingTasks}</strong></button></div>
    <section className="manager-notes-panel card"><div className="card-header-clean"><div className="col-title-group"><FileText size={18} /><h3>Important employee notes</h3></div><button className="text-link" onClick={() => setActiveTab('handovers')}>Open handover engine →</button></div>{handovers.filter((h) => h.important_notes?.trim()).slice(0, 6).map((h) => <article className="manager-note-row" key={h.id}><div><strong>{h.project_name || 'Project'} · {h.employee_name}</strong><small>{h.role} · {h.status.replace('_', ' ')}</small></div><p>{h.important_notes}</p></article>)}{!handovers.some((h) => h.important_notes?.trim()) && <p className="empty-subtext">Important notes from employee handovers will appear here.</p>}</section>
  </div>

  return (
    <div className="section-container">
      {/* Hero Banner */}
      <div className="hero-banner">
        <div className="hero-content">
          <span className="hero-badge">Enterprise Knowledge Continuity Platform</span>
          <h2 className="hero-title">Where Organizational Knowledge Becomes Lasting Team Intelligence</h2>
          <p className="hero-desc">
            Synora prevents costly organizational memory loss caused by employee turnover, resignations, and team transitions.
            Convert scattered pull requests, Jira tickets, and tribal knowledge into verified handovers and proactive continuity alerts.
          </p>
          <div className="hero-actions">
            <button className="primary-btn" onClick={() => setActiveTab('handovers')}>
              <UserCheck size={16} />
              <span>Manage Handover Dossiers</span>
            </button>
            <button className="secondary-btn" onClick={() => setActiveTab('projects')}>
              <FolderKanban size={16} />
              <span>Open Projects</span>
            </button>
            <button className="secondary-btn" onClick={() => setActiveTab('sentinel')}>
              <ShieldAlert size={16} />
              <span>Review Sentinel Risks</span>
            </button>
          </div>
        </div>
      </div>

      <section className="dashboard-workspace" aria-label="Project completion and work status">
        <div className="dashboard-progress-panel card">
          <div className="card-header-clean"><div className="col-title-group"><CheckCircle2 className="text-indigo" size={18} /><h3>Recorded Work Completion</h3></div><button className="text-link" onClick={() => setActiveTab('handovers')}>Open handovers →</button></div>
          <div className="dashboard-progress-content">
            <div className="completion-ring" style={{ '--completion': `${completion ?? 0}%` } as React.CSSProperties} aria-label={completion == null ? 'Completion not available' : `${completion}% recorded work complete`}>
              <div><strong>{completion == null ? '—' : `${completion}%`}</strong><span>{completion == null ? 'No task data' : 'complete'}</span></div>
            </div>
            <div className="dashboard-progress-stats"><div><strong>{completedTasks}</strong><span>Recorded done</span></div><div><strong>{remainingTasks}</strong><span>Recorded remaining</span></div><p>Calculated from completed and pending tasks in handover records. No project-wide estimate is inferred when tasks are not recorded.</p></div>
          </div>
        </div>
        <div className="dashboard-work-columns">
          <WorkList title="Work done" icon={<CheckCircle2 size={17} />} items={completedWork} empty="No completed work recorded yet." />
          <WorkList title="Remaining work" icon={<CircleDashed size={17} />} items={remainingWork} empty="No pending work recorded." />
        </div>
        <section className="dashboard-priority-panel card">
          <div className="card-header-clean"><div className="col-title-group"><ListTodo className="text-amber" size={18} /><h3>Priority Work</h3></div><span className="dashboard-count-pill">{priorityItems.length} active findings</span></div>
          {priorityItems.length ? <div className="dashboard-priority-list">{priorityItems.slice(0, 8).map((item) => <article key={item.id} className="dashboard-priority-item"><span className={`badge badge-${item.priority}`}>{item.priority}</span><div><strong>{item.title}</strong><small>{item.source} · {item.project}</small><p>{item.action}</p></div></article>)}</div> : <p className="empty-subtext">No active Radar or Sentinel findings.</p>}
          <button className="text-link" onClick={() => setActiveTab('radar')}>Review Radar and Sentinel →</button>
        </section>
      </section>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card" onClick={() => setActiveTab('handovers')}>
          <div className="stat-header">
            <span className="stat-label">Active Handovers</span>
            <div className="stat-icon-wrapper bg-indigo">
              <UserCheck size={20} />
            </div>
          </div>
          <div className="stat-value">{handovers.length}</div>
          <div className="stat-footer">
            <span className="stat-sub">{inProgressHandovers.length} currently in progress</span>
            <ArrowUpRight size={14} />
          </div>
        </div>

        <div className="stat-card" onClick={() => setActiveTab('sentinel')}>
          <div className="stat-header">
            <span className="stat-label">Sentinel Risk Alerts</span>
            <div className="stat-icon-wrapper bg-red">
              <ShieldAlert size={20} />
            </div>
          </div>
          <div className="stat-value">{risks.length}</div>
          <div className="stat-footer">
            <span className="stat-sub text-red">{criticalRisks.length} critical SPOF flags</span>
            <ArrowUpRight size={14} />
          </div>
        </div>

        <div className="stat-card" onClick={() => setActiveTab('knowledge')}>
          <div className="stat-header">
            <span className="stat-label">Knowledge Nodes</span>
            <div className="stat-icon-wrapper bg-emerald">
              <BookOpen size={20} />
            </div>
          </div>
          <div className="stat-value">{nodes.length}</div>
          <div className="stat-footer">
            <span className="stat-sub">Mapped architecture & modules</span>
            <ArrowUpRight size={14} />
          </div>
        </div>

        <div className="stat-card" onClick={() => setActiveTab('radar')}>
          <div className="stat-header">
            <span className="stat-label">Coverage & Radar</span>
            <div className="stat-icon-wrapper bg-cyan">
              <Compass size={20} />
            </div>
          </div>
          <div className="stat-value">Radar Active</div>
          <div className="stat-footer">
            <span className="stat-sub">Audit coverage & bus factor</span>
            <ArrowUpRight size={14} />
          </div>
        </div>
      </div>

      {/* Two Column Section */}
      <div className="dashboard-columns">
        {/* Left Column: Sentinel Highlights */}
        <div className="dashboard-col card">
          <div className="card-header-clean">
            <div className="col-title-group">
              <AlertTriangle className="text-amber" size={18} />
              <h3>High Priority Sentinel Alerts</h3>
            </div>
            <button className="text-link" onClick={() => setActiveTab('sentinel')}>
              View all ({risks.length}) &rarr;
            </button>
          </div>
          <div className="quick-list">
            {risks.slice(0, 2).map((r) => (
              <div key={r.id} className="quick-item">
                <div className="quick-item-top">
                  <span className="quick-title">{r.project_name}</span>
                  <span className={`badge badge-${r.risk_level}`}>{r.risk_level.toUpperCase()}</span>
                </div>
                <p className="quick-desc">{r.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Active Handover Queue */}
        <div className="dashboard-col card">
          <div className="card-header-clean">
            <div className="col-title-group">
              <UserCheck className="text-indigo" size={18} />
              <h3>Recent Handover Dossiers</h3>
            </div>
            <button className="text-link" onClick={() => setActiveTab('handovers')}>
              View all ({handovers.length}) &rarr;
            </button>
          </div>
          <div className="quick-list">
            {handovers.slice(0, 2).map((h) => (
              <div key={h.id} className="quick-item">
                <div className="quick-item-top">
                  <div>
                    <span className="quick-title">{h.employee_name}</span>
                    <span className="quick-sub"> &bull; {h.role}</span>
                  </div>
                  <span className="badge badge-neutral">{h.status.replace('_', ' ')}</span>
                </div>
                <p className="quick-desc">
                  {h.key_responsibilities.length} responsibilities &bull; {h.critical_dependencies.length} dependencies
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function priorityRank(priority: string) { return ({ critical: 0, high: 1, medium: 2, low: 3 } as Record<string, number>)[priority.toLowerCase()] ?? 4 }

function WorkList({ title, icon, items, empty }: { title: string; icon: React.ReactNode; items: Array<{ id: string; task: string; project: string }>; empty: string }) {
  return <section className="dashboard-work-list card"><div className="card-header-clean"><div className="col-title-group">{icon}<h3>{title}</h3></div><span className="dashboard-count-pill">{items.length}</span></div>{items.length ? <ul>{items.slice(0, 8).map((item) => <li key={item.id}><strong>{item.task}</strong><small>{item.project}</small></li>)}</ul> : <p className="empty-subtext">{empty}</p>}</section>
}
