import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertOctagon, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error in Synora component tree:', error, errorInfo)
    this.setState({ errorInfo })
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
    window.location.reload()
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="min-h-[350px] p-8 flex flex-col items-center justify-center text-center bg-slate-950/80 border border-red-900/50 rounded-xl m-6">
          <div className="w-12 h-12 rounded-full bg-red-950/80 border border-red-700/60 flex items-center justify-center text-red-400 mb-4">
            <AlertOctagon size={24} />
          </div>
          <h2 className="text-lg font-bold text-slate-100 mb-2">
            Application Rendering Interrupted
          </h2>
          <p className="text-xs text-slate-400 max-w-md mb-4 leading-relaxed">
            Synora encountered an unexpected UI component failure. The error has been isolated to prevent total session loss.
          </p>
          {this.state.error && (
            <pre className="text-xs font-mono bg-slate-900 p-3 rounded text-red-300 max-w-lg overflow-x-auto mb-5 border border-slate-800 text-left">
              <code>{this.state.error.message}</code>
            </pre>
          )}
          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md text-xs font-semibold shadow transition-colors"
          >
            <RotateCcw size={14} />
            <span>Reload Synora Workspace</span>
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
