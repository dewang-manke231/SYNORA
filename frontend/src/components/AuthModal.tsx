import React, { useState } from 'react'
import { Shield, LogIn, UserPlus, X, AlertCircle, CheckCircle2, Building2 } from 'lucide-react'
import { loginUser, registerUser } from '../services/api'
import type { UserProfile } from '../types'

interface AuthModalProps {
  isOpen: boolean
  onClose: () => void
  onAuthSuccess: (user: UserProfile) => void
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, onAuthSuccess }) => {
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [orgName, setOrgName] = useState('Acme Financial Technologies')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)
    setLoading(true)

    try {
      if (tab === 'login') {
        const res = await loginUser({ email: email.trim(), password })
        setSuccessMsg(`Welcome back, ${res.user.full_name}!`)
        setTimeout(() => {
          onAuthSuccess(res.user)
          onClose()
        }, 400)
      } else {
        const res = await registerUser({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          role: 'employee',
          organization_name: orgName.trim(),
        })
        setSuccessMsg(`Account created for ${res.user.full_name}!`)
        setTimeout(() => {
          onAuthSuccess(res.user)
          onClose()
        }, 400)
      }
    } catch (err: any) {
      setError(err?.message || 'Authentication failed. Please verify credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-modal-backdrop fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="auth-modal-panel relative w-full max-w-lg bg-[#111827] border border-gray-800 rounded-xl shadow-2xl p-6 text-gray-100 overflow-hidden">
        {/* Header */}
        <div className="auth-modal-header flex items-center justify-between pb-4 border-b border-gray-800">
          <div className="flex items-center space-x-3">
            <div className="auth-modal-icon p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h2 className="auth-modal-title text-lg font-bold text-white tracking-wide">
                {tab === 'login' ? 'Authentication Required' : 'Register New User'}
              </h2>
              <p className="auth-modal-subtitle text-xs text-gray-400">
                Server-side role-based authorization & data isolation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Toggle */}
        <div className="auth-modal-tabs flex rounded-lg bg-gray-900/80 p-1 my-4 border border-gray-800">
          <button
            type="button"
            onClick={() => { setTab('login'); setError(null); }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all flex items-center justify-center gap-1.5 ${
              tab === 'login' ? 'bg-emerald-600 text-white shadow-sm' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Sign In</span>
          </button>
          <button
            type="button"
            onClick={() => { setTab('register'); setError(null); }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all flex items-center justify-center gap-1.5 ${
              tab === 'register' ? 'bg-emerald-600 text-white shadow-sm' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Create Account</span>
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="auth-modal-error mb-4 p-3 rounded-lg bg-red-950/40 border border-red-500/30 text-red-300 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Success Alert */}
        {successMsg && (
          <div className="auth-modal-success mb-4 p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Auth Form */}
        <form onSubmit={handleSubmit} className="auth-modal-form space-y-3.5">
          {tab === 'register' && (
            <>
              <div>
                <label className="auth-modal-label block text-xs font-medium text-gray-300 mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Marcus Vance"
                  className="auth-modal-input w-full px-3 py-2 rounded-lg bg-gray-900 border border-gray-750 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                  <label className="auth-modal-label block text-xs font-medium text-gray-300 mb-1 flex items-center gap-1">
                    <Building2 className="w-3 h-3 text-gray-400" />
                    <span>Organization</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    placeholder="e.g. Acme Fintech"
                    className="auth-modal-input w-full px-3 py-2 rounded-lg bg-gray-900 border border-gray-750 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                  />
              </div>
            </>
          )}

          <div>
            <label className="auth-modal-label block text-xs font-medium text-gray-300 mb-1">Corporate Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. marcus.vance@acme.corp"
              className="auth-modal-input w-full px-3 py-2 rounded-lg bg-gray-900 border border-gray-750 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            />
          </div>

          <div>
            <label className="auth-modal-label block text-xs font-medium text-gray-300 mb-1">
              Password {tab === 'register' && <span className="text-gray-500">(minimum 8 characters)</span>}
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="auth-modal-input w-full px-3 py-2 rounded-lg bg-gray-900 border border-gray-750 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            />
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={loading}
              className="auth-modal-submit w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-800 disabled:text-gray-500 text-white text-xs font-semibold tracking-wide transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-950/50"
            >
              {loading ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  <span>Verifying Credentials...</span>
                </>
              ) : tab === 'login' ? (
                <>
                  <LogIn className="w-3.5 h-3.5" />
                  <span>Authenticate & Issue Token</span>
                </>
              ) : (
                <>
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>Register & Initialize Organization</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Security Footer Notice */}
        <div className="auth-modal-footer mt-4 pt-3 border-t border-gray-800 text-[10px] text-gray-500 text-center flex items-center justify-center gap-1.5">
          <Shield className="w-3 h-3 text-emerald-500" />
          <span>Enforces Argon2/bcrypt-12 hashing & JWT authorization &bull; Cross-organization isolation</span>
        </div>
      </div>
    </div>
  )
}

