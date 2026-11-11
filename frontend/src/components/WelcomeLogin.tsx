import React, { useEffect, useState } from 'react'
import { ArrowRight, BriefcaseBusiness, Check, CheckCircle2, Copy, Cpu, Loader2, Sparkles, UsersRound } from 'lucide-react'
import { fetchPublicDemoCredentials, loginUser, setAuthToken } from '../services/api'
import { TubesBackground } from './TubesBackground'
import type { UserProfile } from '../types'

interface WelcomeLoginProps {
  onAuthenticated: (user: UserProfile) => void
}

type LoginRole = 'manager' | 'employee'
type DemoCredentials = { email: string; password: string }

export const WelcomeLogin: React.FC<WelcomeLoginProps> = ({ onAuthenticated }) => {
  const [loadingRole, setLoadingRole] = useState<LoginRole | null>(null)
  const [errors, setErrors] = useState<Partial<Record<LoginRole, string>>>({})
  const [showEmployeeSignIn, setShowEmployeeSignIn] = useState(false)
  const [employeeCredentials, setEmployeeCredentials] = useState({ email: '', password: '' })
  const [employeeSignInError, setEmployeeSignInError] = useState('')
  const [employeeSigningIn, setEmployeeSigningIn] = useState(false)
  const [demoCredentials, setDemoCredentials] = useState<Partial<Record<LoginRole, DemoCredentials>>>({})
  const [credentialsError, setCredentialsError] = useState('')
  const [copied, setCopied] = useState('')

  useEffect(() => {
    let active = true
    fetchPublicDemoCredentials().then((credentials) => {
      if (active) setDemoCredentials(credentials)
    }).catch((error: unknown) => {
      if (active) setCredentialsError(error instanceof Error ? error.message : 'Demo credentials are unavailable.')
    })
    return () => { active = false }
  }, [])

  const signIn = async (requestedRole: LoginRole) => {
    setErrors(previous => ({ ...previous, [requestedRole]: undefined }))
    setLoadingRole(requestedRole)
    try {
      const credentials = demoCredentials[requestedRole]
      if (!credentials) throw new Error(credentialsError || 'Demo credentials are not available yet. Please retry shortly.')
      const session = await loginUser(credentials)
      const roleMatches = requestedRole === 'manager'
        ? session.user.role === 'manager'
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
          title="Manager Demo"
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
          credentials={demoCredentials.manager}
          credentialsError={credentialsError}
          copied={copied}
          onCopy={(kind, value) => void copyCredential('manager', kind, value)}
          onSubmit={() => void signIn('manager')}
        />
        <LoginCard
          role="employee"
          title="Employee Demo"
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
          credentials={demoCredentials.employee}
          credentialsError={credentialsError}
          copied={copied}
          onCopy={(kind, value) => void copyCredential('employee', kind, value)}
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

  async function copyCredential(role: LoginRole, kind: 'Email' | 'Password' | 'All', value: string) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value)
      } else {
        const field = document.createElement('textarea')
        field.value = value
        field.style.position = 'fixed'
        field.style.opacity = '0'
        document.body.appendChild(field)
        field.select()
        const copiedToClipboard = document.execCommand('copy')
        field.remove()
        if (!copiedToClipboard) throw new Error('Copy unavailable')
      }
      setCopied(`${role}-${kind}`)
      window.setTimeout(() => setCopied(''), 1800)
    } catch {
      setErrors(previous => ({ ...previous, [role]: 'Clipboard access is unavailable in this browser.' }))
    }
  }
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
  credentials?: DemoCredentials
  credentialsError: string
  copied: string
  onCopy: (kind: 'Email' | 'Password' | 'All', value: string) => void
  onSubmit: () => void
}

const LoginCard: React.FC<LoginCardProps> = ({ role, title, description, features, icon, loading, disabled, error, credentials, credentialsError, copied, onCopy, onSubmit }) => (
  <article className={`login-role-card ${role}`}>
    <div className="login-role-heading">
      <span className="login-role-icon">{icon}</span>
      <div><h2>{title}</h2><p>{description}</p></div>
    </div>
    <ul className="login-role-features">{features.map(feature => <li key={feature}><Check size={14} aria-hidden="true" />{feature}</li>)}</ul>
    <div className="welcome-login-form">
      <p className="welcome-demo-note">Public Hackathon Demo Account · Fictional sample data</p>
      {credentials ? <div className="welcome-demo-credentials">
        <div><span>Email</span><code>{credentials.email}</code><button type="button" onClick={() => onCopy('Email', credentials.email)} aria-label="Copy demo email"><Copy size={14} />{copied === `${role}-Email` ? 'Copied' : 'Copy email'}</button></div>
        <div><span>Password</span><code>{credentials.password}</code><button type="button" onClick={() => onCopy('Password', credentials.password)} aria-label="Copy demo password"><Copy size={14} />{copied === `${role}-Password` ? 'Copied' : 'Copy password'}</button></div>
        <button type="button" className="welcome-copy-all" onClick={() => onCopy('All', `Email: ${credentials.email}\nPassword: ${credentials.password}`)}><Copy size={14} />{copied === `${role}-All` ? 'Copied all credentials' : 'Copy all credentials'}</button>
      </div> : <p className="welcome-login-error" role="status">{credentialsError || 'Loading public demo credentials…'}</p>}
      {error && <p className="welcome-login-error" role="alert">{error}</p>}
      <button type="button" className="welcome-login-submit" disabled={disabled || !credentials} onClick={onSubmit}>
        {loading ? <><Loader2 className="spin" size={16} /> Signing in…</> : <>Continue as {role === 'manager' ? 'Manager' : 'Employee'} <ArrowRight size={16} /></>}
      </button>
    </div>
  </article>
)
