import { resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

type BootstrapStatus = 'idle' | 'loading' | 'ready' | 'error'
type BootstrapState = { status: BootstrapStatus; error: string }

let state: BootstrapState = { status: 'idle', error: '' }
let desktopPrewarmPromise: Promise<void> | null = null
const listeners = new Set<(s: BootstrapState) => void>()

function setState(next: Partial<BootstrapState>): void {
  state = { ...state, ...next }
  for (const fn of listeners) fn(state)
}

export function getDesktopBootstrapState(): BootstrapState {
  return state
}

export function subscribeDesktopBootstrap(fn: (s: BootstrapState) => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

export function ensureDesktopBootstrap(): Promise<void> {
  if (resolveClientMode() !== 'desktop') return Promise.resolve()
  if (!desktopPrewarmPromise) {
    setState({ status: 'loading', error: '' })
    desktopPrewarmPromise = (async () => {
      recordRuntimeDiagnostic('desktop.bootstrap', 'start')
      const { prewarmDesktopMediaRuntime } = await import('../runtime/desktopMediaFlow')
      await prewarmDesktopMediaRuntime((message, progress) => {
        recordRuntimeDiagnostic('desktop.bootstrap', 'progress', { message, progress })
      })
      recordRuntimeDiagnostic('desktop.bootstrap', 'ready')
      setState({ status: 'ready', error: '' })
    })().catch((error) => {
      desktopPrewarmPromise = null
      const message = error instanceof Error ? error.message : String(error)
      recordRuntimeDiagnostic('desktop.bootstrap', 'error', error, 'error')
      setState({ status: 'error', error: message })
      throw error
    })
  }
  return desktopPrewarmPromise
}
