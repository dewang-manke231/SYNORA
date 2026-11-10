import React, { useState } from 'react'
import { ArrowRight, BriefcaseBusiness, Check, CheckCircle2, Cpu, Loader2, Sparkles, UsersRound } from 'lucide-react'
import { demoLoginUser, loginUser, setAuthToken } from '../services/api'
import { TubesBackground } from './TubesBackground'
import type { UserProfile } from '../types'

interface WelcomeLoginProps {
  onAuthenticated: (user: UserProfile) => void
}

type LoginRole = 'manager' | 'employee'

export const WelcomeLogin: React.FC<WelcomeLoginProps> = ({ onAuthenticated }) => {
  const [loadingRole, setLoadingRole] = useState<LoginRole | null>(null)
  const [errors, setErrors] = useState<Partial<Record<LoginRole, string>>>({})
  const [showEmployeeSignIn, setShowEmployeeSignIn] = useState(false)
  const [employeeCredentials, setEmployeeCredentials] = useState({ email: '', password: '' })
  const [employeeSignInError, setEmployeeSignInError] = useState('')
  const [employeeSigningIn, setEmployeeSigningIn] = useState(false)

  const signIn = async (requestedRole: LoginRole) => {
    setErrors(previous => ({ ...previous, [requestedRole]: undefined }))
    setLoadingRole(requestedRole)
    try {
      const session = await demoLoginUser(requestedRole)
      const roleMatches = requestedRole === 'manager'
        ? session.user.role === 'manager' || session.user.role === 'admin'
        : session.user.role === 'employee'
      if (!roleMatches) {
        setAuthToken(null)
        throw new Error(`This account has ${session.user.role} access. Please use the matching login option.`)
      }
      onAuthenticated(session.user)
    } catch (error: any) {
      setErrors(previous => ({ ...previous, [requestedRole]: error?.message || 'Sign in failed. Check your email and password.' }))
    } finally {
      setLoadingRole(null)
    }
  }

  const signInExistingEmployee = async (event: React.FormEvent) => {
    event.preventDefault()
    setEmployeeSigningIn(true)
    setEmployeeSignInError('')
    try {
      const session = await loginUser(employeeCredentials)
      if (session.user.role !== 'employee') {
        setAuthToken(null)
        throw new Error('This sign-in is for employee accounts. Use the Manager Login option for manager accounts.')
      }
      onAuthenticated(session.user)
    } catch (error) { setEmployeeSignInError(error instanceof Error ? error.message : 'Sign in failed.') }
    finally { setEmployeeSigningIn(false) }
  }

  return <main className="welcome-login-page">
    <TubesBackground />
    <div className="welcome-login-grain" aria-hidden="true" />
    <div className="welcome-login-content">
      <header className="welcome-brand">
        <span className="welcome-brand-icon"><Cpu size={25} aria-hidden="true" /></span>
        <span><strong>SYNORA</strong><small>Knowledge continuity, made clear.</small></span>
      </header>

      <section className="welcome-intro" aria-labelledby="welcome-title">
        <span className="welcome-eyebrow"><CheckCircle2 size={14} /> YOUR PROJECT CONTINUITY WORKSPACE</span>
        <h1 id="welcome-title">Welcome back.<br /><span>Your team’s <em className="welcome-title-accent">knowledge</em> starts here.</span></h1>
        <p>Sign in to explore projects, preserve critical knowledge and keep work moving across every handoff.</p>
      </section>

      <section className="login-role-grid" aria-label="Choose your workspace login">
        <LoginCard
          role="manager"
          title="Manager Login"
          description="Oversee team continuity and project health."
          features={[
            'See organization projects and team progress',
            'Verify extracted knowledge and handover submissions',
            'Use Sentinel to spot missing files and incomplete work',
            'Review Radar alerts, guidance and recommended actions',
            'Manage role-based employee handovers',
            'Review key notes and handover reports',
          ]}
          icon={<BriefcaseBusiness size={22} aria-hidden="true" />}
          loading={loadingRole === 'manager'}
          disabled={loadingRole !== null}
          error={errors.manager}
          onSubmit={() => void signIn('manager')}
        />
        <LoginCard
          role="employee"
          title="Employee Login"
          description="Upload project work and preserve the details your team needs."
          features={[
            'Upload project ZIPs and supporting documents',
            'Track completed and pending work with Radar',
            'Record important notes, links and repositories',
            'Create handovers for manager review',
            'Use project knowledge and environment checklists',
            'Share progress and project updates',
          ]}
          icon={<UsersRound size={22} aria-hidden="true" />}
          loading={loadingRole === 'employee'}
          disabled={loadingRole !== null}
          error={errors.employee}
          onSubmit={() => void signIn('employee')}
        />
      </section>

      <section className="welcome-shared-tools" aria-label="Shared tools for managers and employees">
        <div className="welcome-shared-heading"><Sparkles size={17} /><strong>Shared in both workspaces</strong></div>
        <div className="welcome-shared-list"><span>NOVA AI guidance</span><span>Project knowledge search</span><span>Missing-information discovery</span><span>Next-step planning</span></div>
      </section>

      <section className="welcome-joiner-flow" aria-label="New joiner project continuity workflow">
        <div className="welcome-joiner-title"><span>NEW JOINER PATH</span><small>From project access to continuity checks</small></div>
        <div className="welcome-joiner-steps">{['Get project', 'Verify sources', 'Extract files & knowledge', 'Review extracted info', 'Build memory graph', 'Recreate environment', 'Complete setup checks', 'Review alerts'].map((step, index) => <span key={step}><b>{index + 1}</b>{step}</span>)}</div>
      </section>

      <footer className="welcome-login-footer"><span>Secure sign-in with your Synora account</span><span>Access is determined by your account permissions.</span></footer>
      <section className="welcome-employee-signin"><button type="button" onClick={() => setShowEmployeeSignIn((shown) => !shown)}>{showEmployeeSignIn ? 'Hide employee account sign-in' : 'Already added as an employee? Sign in with your account'}</button>{showEmployeeSignIn && <form onSubmit={(event) => void signInExistingEmployee(event)}><input required type="email" autoComplete="username" placeholder="Employee email" value={employeeCredentials.email} onChange={(event) => setEmployeeCredentials({ ...employeeCredentials, email: event.target.value })} /><input required type="password" autoComplete="current-password" placeholder="Password" value={employeeCredentials.password} onChange={(event) => setEmployeeCredentials({ ...employeeCredentials, password: event.target.value })} />{employeeSignInError && <p role="alert">{employeeSignInError}</p>}<button type="submit" disabled={employeeSigningIn}>{employeeSigningIn ? 'Signing in…' : 'Sign in as employee'}</button></form>}</section>
    </div>
  </main>
}

interface LoginCardProps {
  role: LoginRole
  title: string
  description: string
  features: string[]
  icon: React.ReactNode
  loading: boolean
  disabled: boolean
  error?: string
  onSubmit: () => void
}

const LoginCard: React.FC<LoginCardProps> = ({ role, title, description, features, icon, loading, disabled, error, onSubmit }) => (
  <article className={`login-role-card ${role}`}>
    <div className="login-role-heading">
      <span className="login-role-icon">{icon}</span>
      <div><h2>{title}</h2><p>{description}</p></div>
    </div>
    <ul className="login-role-features">{features.map(feature => <li key={feature}><Check size={14} aria-hidden="true" />{feature}</li>)}</ul>
    <div className="welcome-login-form">
      <p className="welcome-demo-note">Prototype demo access · No email or password required</p>
      {error && <p className="welcome-login-error" role="alert">{error}</p>}
      <button type="button" className="welcome-login-submit" disabled={disabled} onClick={onSubmit}>
        {loading ? <><Loader2 className="spin" size={16} /> Opening demo workspace…</> : <>Continue as {role === 'manager' ? 'Manager' : 'Employee'} <ArrowRight size={16} /></>}
      </button>
    </div>
  </article>
)
