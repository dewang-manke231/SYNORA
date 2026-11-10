import React from 'react'
import { ShieldAlert, BookOpen, UserCheck, Cpu, Terminal, Activity, Compass, User as UserIcon, LogOut, LogIn, FolderKanban } from 'lucide-react'
import type { HealthStatus, UserProfile } from '../types'

interface NavbarProps {
  activeTab: string
  setActiveTab: (tab: string) => void
  health: HealthStatus | null
  healthLoading: boolean
  criticalGapsCount?: number
  currentUser: UserProfile | null
  onOpenAuth: () => void
  onLogout: () => void
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  health,
  healthLoading,
  criticalGapsCount = 0,
  currentUser,
  onOpenAuth,
  onLogout,
}) => {
  const managerMode = currentUser?.role === 'manager' || currentUser?.role === 'admin'
  const tabs = [
    { id: 'dashboard', label: managerMode ? 'Manager Overview' : 'Overview', icon: Activity },
    { id: 'projects', label: 'Projects', icon: FolderKanban },
    { id: 'handovers', label: 'Employee Handovers', icon: UserCheck },
    ...(!managerMode ? [
    { id: 'radar', label: 'Loss Radar', icon: Compass, badgeCount: criticalGapsCount },
    { id: 'sentinel', label: 'Synora Sentinel', icon: ShieldAlert },
    { id: 'knowledge', label: 'Knowledge Graph', icon: BookOpen },
    { id: 'recreator', label: 'Env Recreator', icon: Terminal },
    ] : []),
  ]

  const getRoleBadgeClass = (role: string) => {
    switch (role.toLowerCase()) {
      case 'manager':
        return 'role-badge manager'
      case 'admin':
        return 'role-badge admin'
      case 'employee':
      default:
        return 'role-badge employee'
    }
  }

  return (
    <header className="header">
      <div className="header-brand">
        <div className="logo-icon">
          <Cpu className="w-6 h-6" />
        </div>
        <div>
          <h1 className="brand-title">SYNORA</h1>
          <p className="brand-subtitle">Knowledge Continuity & Project Protection</p>
        </div>
      </div>

      <nav className="header-nav">
        {tabs.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`nav-btn ${isActive ? 'active' : ''}`}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
              {tab.badgeCount !== undefined && tab.badgeCount > 0 && (
                <span className="nav-alert-count">
                  {tab.badgeCount}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      <div className="header-status flex items-center gap-3">
        {currentUser ? (
          <div className="header-account">
            <div className="header-account-avatar">
              {currentUser.full_name.charAt(0)}
            </div>
            <div className="header-account-info">
              <span className="header-account-name">
                {currentUser.full_name}
              </span>
              <span className="header-account-org">
                {currentUser.organization_name || 'Acme Technologies'}
              </span>
            </div>
            <span
              className={getRoleBadgeClass(currentUser.role)}
            >
              {currentUser.role}
            </span>
            <button
              onClick={onOpenAuth}
              title="Switch user account"
              className="header-account-control"
            >
              <UserIcon size={13} />
            </button>
            <button
              onClick={onLogout}
              title="Sign Out"
              className="header-account-control signout"
            >
              <LogOut size={13} />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="header-signin-button"
          >
            <LogIn size={13} />
            <span>Sign In</span>
          </button>
        )}

        <div
          className={`status-pill ${health ? 'online' : healthLoading ? 'loading' : 'offline'}`}
          title={
            health
              ? `Database: ${health.database_type?.toUpperCase()} (${health.database_target}) | Latency: ${health.latency_ms}ms | Tables: ${health.tables_count} | pgvector: ${health.pgvector_installed ? 'ACTIVE' : 'N/A'}`
              : undefined
          }
        >
          <span className="dot" />
          <span>
            {healthLoading
              ? 'Connecting...'
              : health
              ? `${health.database_type === 'postgresql' ? 'Supabase PG' : 'SQLite'} • v${health.version}`
              : 'Backend Offline'}
          </span>
        </div>
      </div>
    </header>
  )
}
