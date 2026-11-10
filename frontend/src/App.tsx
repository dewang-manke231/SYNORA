import { useEffect, useState, useCallback } from 'react'
import { Navbar } from './components/Navbar'
import { DashboardView } from './components/DashboardView'
import { HandoverView } from './components/HandoverView'
import { SentinelView } from './components/SentinelView'
import { KnowledgeView } from './components/KnowledgeView'
import { RadarView } from './components/RadarView'
import { RecreatorView } from './components/RecreatorView'
import { ProjectsView } from './components/ProjectsView'
import { ChatAssistant } from './components/ChatAssistant'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider, useToast } from './components/Toast'
import { AuthModal } from './components/AuthModal'
import { WelcomeLogin } from './components/WelcomeLogin'
import {
  fetchHealth,
  fetchHandovers,
  createHandover,
  fetchRisks,
  fetchKnowledgeNodes,
  fetchRadarRisks,
  fetchCurrentUser,
  logoutUser,
  getAuthToken,
  fetchProjects,
} from './services/api'
import type { HealthStatus, HandoverItem, HandoverCreatePayload, RiskAlert, KnowledgeNode, KnowledgeGapItem, UserProfile, ChatAgentType } from './types'
import './App.css'

function AppContent() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [lastModuleTab, setLastModuleTab] = useState('dashboard')
  const [activeProjectId, setActiveProjectId] = useState('')
  const [activeProjectName, setActiveProjectName] = useState('')
  const [chatAgentHint, setChatAgentHint] = useState<ChatAgentType>('auto')
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [handovers, setHandovers] = useState<HandoverItem[]>([])
  const [risks, setRisks] = useState<RiskAlert[]>([])
  const [nodes, setNodes] = useState<KnowledgeNode[]>([])
  const [radarGaps, setRadarGaps] = useState<KnowledgeGapItem[]>([])
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [authChecking, setAuthChecking] = useState(true)
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { addToast } = useToast()

  useEffect(() => {
    if (activeTab !== 'chat') setLastModuleTab(activeTab)
  }, [activeTab])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const managerMode = currentUser?.role === 'manager' || currentUser?.role === 'admin'
      const [handoversData, risksData, nodesData, radarData] = managerMode
        ? [await fetchHandovers(), [] as RiskAlert[], [] as KnowledgeNode[], [] as KnowledgeGapItem[]]
        : await Promise.all([
          fetchHandovers(), fetchRisks(), fetchKnowledgeNodes(),
          fetchRadarRisks({ is_resolved: false }).catch(() => []),
        ])
      setHandovers(handoversData)
      setRisks(risksData)
      setNodes(nodesData)
      setRadarGaps(radarData)
    } catch (err) {
      console.error('Failed to load full platform data', err)
      setError('Connected in standalone mode or waiting for backend service.')
    } finally {
      setLoading(false)
    }
  }, [currentUser])

  // Check auth session
  useEffect(() => {
    async function checkAuth() {
      const token = getAuthToken()
      if (!token) {
        setAuthChecking(false)
        return
      }
      try {
        const user = await fetchCurrentUser()
        setCurrentUser(user)
        setActiveTab('dashboard')
      } catch {
        logoutUser()
        setCurrentUser(null)
      } finally {
        setAuthChecking(false)
      }
    }
    checkAuth()
  }, [])

  // Listen to global auth events
  useEffect(() => {
    const handleUnauthorized = () => {
      addToast({
        type: 'warning',
        title: 'Authentication Required',
        message: 'Your session has expired or requires manager authorization. Please sign in.',
      })
      setIsAuthModalOpen(true)
    }

    const handleLoggedOut = () => {
      setCurrentUser(null)
      setActiveProjectId('')
      setActiveProjectName('')
      addToast({
        type: 'info',
        title: 'Signed Out',
        message: 'You have been logged out.',
      })
    }

    window.addEventListener('synora-unauthorized', handleUnauthorized)
    window.addEventListener('synora-logged-out', handleLoggedOut)

    return () => {
      window.removeEventListener('synora-unauthorized', handleUnauthorized)
      window.removeEventListener('synora-logged-out', handleLoggedOut)
    }
  }, [addToast])

  useEffect(() => {
    if (!currentUser) {
      setHealthLoading(false)
      setLoading(false)
      return
    }
    async function loadHealth() {
      setHealthLoading(true)
      try {
        const healthData = await fetchHealth()
        setHealth(healthData)
      } catch (err) {
        console.warn('Backend not yet reachable on /api/v1/health', err)
        setHealth(null)
      } finally {
        setHealthLoading(false)
      }
    }

    loadHealth()
    loadData()

    const interval = setInterval(async () => {
      try {
        const healthData = await fetchHealth()
        setHealth(healthData)
      } catch {
        setHealth(null)
      }
    }, 60000)

    return () => clearInterval(interval)
  }, [loadData, currentUser])

  const criticalRadarCount = radarGaps.filter(
    (g) => g.severity.toLowerCase() === 'critical' && !g.is_resolved
  ).length

  const handleSelectProject = useCallback((id: string, name?: string) => {
    setActiveProjectId(id)
    if (currentUser) {
      const key = `synora_active_project_${currentUser.id}`
      if (id) localStorage.setItem(key, id)
      else localStorage.removeItem(key)
    }
    if (!id) {
      setActiveProjectName('')
    } else if (name) {
      setActiveProjectName(name)
    } else {
      setActiveProjectName('')
    }
  }, [currentUser])

  useEffect(() => {
    if (!currentUser) return
    const storedId = localStorage.getItem(`synora_active_project_${currentUser.id}`)
    // Restore the user's last project immediately; the server response below
    // still validates that the project remains accessible to this account.
    if (storedId) setActiveProjectId(storedId)
    // Warm the shared project-list request after authentication so Projects and
    // Knowledge can reuse it instead of starting another serial request.
    fetchProjects().then(projects => {
      if (!storedId) return
      const project = projects.find(item => item.id === storedId)
      if (project) {
        setActiveProjectId(project.id)
        setActiveProjectName(project.name)
      } else {
        localStorage.removeItem(`synora_active_project_${currentUser.id}`)
        setActiveProjectId((activeId) => activeId === storedId ? '' : activeId)
        setActiveProjectName('')
      }
    }).catch(() => {
      if (!storedId) return
      localStorage.removeItem(`synora_active_project_${currentUser.id}`)
      setActiveProjectId((activeId) => activeId === storedId ? '' : activeId)
      setActiveProjectName('')
    })
  }, [currentUser])

  useEffect(() => {
    if ((currentUser?.role === 'manager' || currentUser?.role === 'admin') && !['dashboard', 'projects', 'handovers'].includes(activeTab)) {
      setActiveTab('dashboard')
    }
  }, [currentUser, activeTab])

  const handleCreateHandover = async (payload: HandoverCreatePayload) => {
    try {
      const newItem = await createHandover(payload)
      setHandovers([newItem, ...handovers])
      addToast({
        type: 'success',
        title: 'Handover Created',
        message: `Dossier '${newItem.employee_name}' created in Draft status.`,
      })
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Creation Failed',
        message: err?.message || 'Failed to create handover.',
      })
      throw err
    }
  }

  const handleRefreshHandovers = async () => {
    try {
      const data = await fetchHandovers()
      setHandovers(data)
    } catch (err) {
      console.error('Failed to refresh handovers', err)
    }
  }

  const handleAuthenticated = (user: UserProfile) => {
    setCurrentUser(user)
    setActiveTab('dashboard')
    setIsAuthModalOpen(false)
    setActiveProjectId('')
    setActiveProjectName('')
  }

  if (authChecking) {
    return <main className="auth-check-screen" aria-live="polite"><span className="spinner" /> Preparing your Synora sign-in…</main>
  }

  if (!currentUser) {
    return <WelcomeLogin onAuthenticated={handleAuthenticated} />
  }

  return (
    <div className="app-layout">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        health={health}
        healthLoading={healthLoading}
        criticalGapsCount={criticalRadarCount}
        currentUser={currentUser}
        onOpenAuth={() => setIsAuthModalOpen(true)}
        onLogout={() => {
          logoutUser()
          setCurrentUser(null)
        }}
      />

      <main className="main-content">
        {loading && (
          <div className="loading-banner">
            <span className="spinner" />
            <span>Loading Synora Platform Intelligence...</span>
          </div>
        )}

        {error && !loading && handovers.length === 0 && (
          <div className="error-banner">
            <p>{error}</p>
          </div>
        )}

        {activeTab === 'dashboard' && (
          <DashboardView
            handovers={handovers}
            risks={risks}
            nodes={nodes}
            radarGaps={radarGaps}
            setActiveTab={setActiveTab}
            managerMode={currentUser.role === 'manager' || currentUser.role === 'admin'}
            managerName={currentUser.full_name}
          />
        )}

        {activeTab === 'projects' && (
          <ProjectsView
            userId={currentUser?.id || 'guest'}
            managerMode={currentUser.role === 'manager' || currentUser.role === 'admin'}
            activeProjectId={activeProjectId}
            onSelectProject={handleSelectProject}
            onOpenModule={(tab, projectId, projectName) => {
              setActiveProjectId(projectId)
              setActiveProjectName(projectName || '')
              if (currentUser && projectId) localStorage.setItem(`synora_active_project_${currentUser.id}`, projectId)
              setActiveTab(tab)
            }}
          />
        )}

        {activeTab === 'handovers' && (
          <HandoverView
            handovers={currentUser.role === 'manager' || currentUser.role === 'admin' ? handovers : (activeProjectId ? handovers.filter((item) => item.project_id === activeProjectId) : handovers)}
            onCreateHandover={handleCreateHandover}
            onRefreshHandovers={handleRefreshHandovers}
            activeProjectId={activeProjectId}
            activeProjectName={activeProjectName}
            managerMode={currentUser.role === 'manager' || currentUser.role === 'admin'}
            currentUserName={currentUser.full_name}
            currentUserId={currentUser.id}
            onProjectChange={handleSelectProject}
          />
        )}

        {activeTab === 'radar' && <RadarView projectId={activeProjectId} />}

        {activeTab === 'sentinel' && <SentinelView risks={risks} projectId={activeProjectId} />}

        {activeTab === 'knowledge' && (
          <KnowledgeView
            nodes={nodes}
            projectId={activeProjectId}
            onRefreshNodes={async () => {
              try {
                const refreshed = await fetchKnowledgeNodes()
                setNodes(refreshed)
              } catch (err) {
                console.error('Failed to refresh knowledge nodes', err)
              }
            }}
          />
        )}

        {activeTab === 'recreator' && <RecreatorView projectId={activeProjectId} onAskAssistant={(id, name) => {
          if (id) handleSelectProject(id, name)
          setChatAgentHint('onboarding_navigator')
          setActiveTab('chat')
        }} />}
      </main>

      <footer className="footer">
        <div className="footer-inner">
          <p>&copy; {new Date().getFullYear()} Synora Intelligence. All rights reserved.</p>
          <p className="footer-meta">
            FastAPI Backend + React Vite TypeScript Frontend &bull; Knowledge Continuity &bull; RBAC Protected
          </p>
        </div>
      </footer>

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onAuthSuccess={(user) => {
          handleAuthenticated(user)
          addToast({
            type: 'success',
            title: 'Authenticated',
            message: `Signed in as ${user.full_name} (${user.role.toUpperCase()})`,
          })
        }}
      />

      {currentUser && <ChatAssistant
        userId={currentUser.id}
        projectId={activeProjectId}
        projectName={activeProjectName}
        handovers={handovers}
        currentPage={activeTab === 'chat' ? lastModuleTab : activeTab}
        forceOpen={activeTab === 'chat'}
        agentHint={chatAgentHint}
        onClose={() => setActiveTab(lastModuleTab)}
        onNavigate={(tab) => setActiveTab(tab)}
      />}
    </div>
  )
}

export function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </ErrorBoundary>
  )
}

export default App
