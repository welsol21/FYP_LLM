type RuntimeDiagnosticLevel = 'info' | 'warning' | 'error'

export type RuntimeDiagnosticEntry = {
  at: string
  session: string
  level: RuntimeDiagnosticLevel
  scope: string
  event: string
  details?: string
}

const RUNTIME_DIAG_KEY = 'ela_runtime_diagnostics_v1'
const MAX_RUNTIME_DIAGNOSTICS = 200
const sessionId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
const listeners = new Set<() => void>()

function notify(): void {
  for (const listener of listeners) listener()
}

function safeStringify(value: unknown): string {
  if (typeof value === 'string') return value
  if (value instanceof Error) return `${value.name}: ${value.message}`
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function getRuntimeDiagnostics(): RuntimeDiagnosticEntry[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = String(window.localStorage.getItem(RUNTIME_DIAG_KEY) || '')
    if (!raw) return []
    const parsed = JSON.parse(raw) as RuntimeDiagnosticEntry[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeRuntimeDiagnostics(entries: RuntimeDiagnosticEntry[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(RUNTIME_DIAG_KEY, JSON.stringify(entries.slice(-MAX_RUNTIME_DIAGNOSTICS)))
  } catch {
    // ignore logging failures
  }
}

export function recordRuntimeDiagnostic(
  scope: string,
  event: string,
  details?: unknown,
  level: RuntimeDiagnosticLevel = 'info',
): void {
  const entries = getRuntimeDiagnostics()
  entries.push({
    at: new Date().toISOString(),
    session: sessionId,
    level,
    scope: String(scope || 'runtime'),
    event: String(event || 'event'),
    details: details == null ? undefined : safeStringify(details),
  })
  writeRuntimeDiagnostics(entries)
  notify()
}

export function clearRuntimeDiagnostics(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(RUNTIME_DIAG_KEY)
  notify()
}

export function subscribeRuntimeDiagnostics(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

let initialized = false

export function initRuntimeDiagnostics(): void {
  if (initialized || typeof window === 'undefined') return
  initialized = true
  recordRuntimeDiagnostic('app', 'boot', {
    path: window.location.pathname,
    ua: navigator.userAgent,
    online: navigator.onLine,
  })
  window.addEventListener('pageshow', (event) => {
    recordRuntimeDiagnostic('window', 'pageshow', { persisted: Boolean((event as PageTransitionEvent).persisted) })
  })
  window.addEventListener('pagehide', (event) => {
    recordRuntimeDiagnostic('window', 'pagehide', { persisted: Boolean((event as PageTransitionEvent).persisted) })
  })
  window.addEventListener('beforeunload', () => {
    recordRuntimeDiagnostic('window', 'beforeunload')
  })
  document.addEventListener('visibilitychange', () => {
    recordRuntimeDiagnostic('document', 'visibilitychange', document.visibilityState)
  })
  window.addEventListener('online', () => {
    recordRuntimeDiagnostic('network', 'online')
  })
  window.addEventListener('offline', () => {
    recordRuntimeDiagnostic('network', 'offline', undefined, 'warning')
  })
  window.addEventListener('error', (event) => {
    recordRuntimeDiagnostic(
      'window',
      'error',
      {
        message: event.message,
        source: event.filename,
        line: event.lineno,
        column: event.colno,
      },
      'error',
    )
  })
  window.addEventListener('unhandledrejection', (event) => {
    recordRuntimeDiagnostic('window', 'unhandledrejection', event.reason, 'error')
  })
}
