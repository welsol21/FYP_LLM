import React from 'react'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'

type Props = {
  children: React.ReactNode
}

type State = {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error?.message || 'Unknown render error',
    }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    recordRuntimeDiagnostic('react', 'error_boundary', {
      message: error?.message || 'Unknown render error',
      stack: error?.stack || '',
      componentStack: info?.componentStack || '',
    }, 'error')
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="card">
          <h2>Rendering Error</h2>
          <p>{this.state.message}</p>
          <p>Open Config and inspect Runtime Diagnostics.</p>
        </section>
      )
    }
    return this.props.children
  }
}
