import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, AlertOctagon, Info, X } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  type: ToastType
  title: string
  message?: string
}

interface ToastContextType {
  toast: (options: { type?: ToastType; title: string; message?: string; duration?: number }) => void
  addToast: (options: { type?: ToastType; title: string; message?: string; duration?: number }) => void
  success: (title: string, message?: string) => void
  error: (title: string, message?: string) => void
  warning: (title: string, message?: string) => void
  info: (title: string, message?: string) => void
}

const ToastContext = createContext<ToastContextType | undefined>(undefined)

export const ToastProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback(
    ({
      type = 'info',
      title,
      message,
      duration = 4000,
    }: {
      type?: ToastType
      title: string
      message?: string
      duration?: number
    }) => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
      const newToast: ToastItem = { id, type, title, message }
      setToasts((prev) => [...prev, newToast])

      if (duration > 0) {
        setTimeout(() => {
          removeToast(id)
        }, duration)
      }
    },
    [removeToast]
  )

  const success = useCallback(
    (title: string, message?: string) => addToast({ type: 'success', title, message }),
    [addToast]
  )

  const error = useCallback(
    (title: string, message?: string) => addToast({ type: 'error', title, message }),
    [addToast]
  )

  const warning = useCallback(
    (title: string, message?: string) => addToast({ type: 'warning', title, message }),
    [addToast]
  )

  const info = useCallback(
    (title: string, message?: string) => addToast({ type: 'info', title, message }),
    [addToast]
  )

  return (
    <ToastContext.Provider value={{ toast: addToast, addToast, success, error, warning, info }}>
      {children}
      {/* Toast Notification Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto p-3.5 rounded-lg border shadow-xl flex items-start gap-3 transition-all transform animate-in slide-in-from-right-5 ${
              t.type === 'success'
                ? 'bg-slate-900 border-emerald-800/80 text-slate-100'
                : t.type === 'error'
                ? 'bg-slate-900 border-red-800/80 text-slate-100'
                : t.type === 'warning'
                ? 'bg-slate-900 border-amber-800/80 text-slate-100'
                : 'bg-slate-900 border-indigo-800/80 text-slate-100'
            }`}
          >
            <div className="shrink-0 mt-0.5">
              {t.type === 'success' && <CheckCircle2 size={16} className="text-emerald-400" />}
              {t.type === 'error' && <AlertOctagon size={16} className="text-red-400" />}
              {t.type === 'warning' && <AlertTriangle size={16} className="text-amber-400" />}
              {t.type === 'info' && <Info size={16} className="text-indigo-400" />}
            </div>

            <div className="flex-1 min-w-0">
              <h5 className="text-xs font-semibold leading-snug">{t.title}</h5>
              {t.message && <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">{t.message}</p>}
            </div>

            <button
              onClick={() => removeToast(t.id)}
              className="text-slate-500 hover:text-slate-300 p-0.5 shrink-0"
              aria-label="Close notification"
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextType {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}
