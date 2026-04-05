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

// In-memory buffer — mutations are instant; localStorage flush is debounced.
// Previously every recordRuntimeDiagnostic() did a synchronous read+parse+
// stringify+write of the full 200-entry blob on the main thread, causing
// 50-100ms freezes per event in WebKitGTK / slower localStorage environments.
let memDiagnostics: RuntimeDiagnosticEntry[] | null = null
let flushTimer: ReturnType<typeof setTimeout> | null = null

function getMemDiagnostics(): RuntimeDiagnosticEntry[] {
  if (memDiagnostics !== null) return memDiagnostics
  if (typeof window === 'undefined') {
    memDiagnostics = []
    return memDiagnostics
  }
  try {
    const raw = String(window.localStorage.getItem(RUNTIME_DIAG_KEY) || '')
    const parsed = raw ? (JSON.parse(raw) as RuntimeDiagnosticEntry[]) : []
    memDiagnostics = Array.isArray(parsed) ? parsed : []
  } catch {
    memDiagnostics = []
  }
  return memDiagnostics
}

function scheduleFlush(): void {
  if (flushTimer !== null) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    if (typeof window === 'undefined' || memDiagnostics === null) return
    try {
      window.localStorage.setItem(
        RUNTIME_DIAG_KEY,
        JSON.stringify(memDiagnostics.slice(-MAX_RUNTIME_DIAGNOSTICS)),
      )
    } catch {
      // ignore
    }
  }, 800)
}

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
  return getMemDiagnostics()
}

function writeRuntimeDiagnostics(_entries: RuntimeDiagnosticEntry[]): void {
  // no-op: writes are now handled by scheduleFlush()
}

export function recordRuntimeDiagnostic(
  scope: string,
  event: string,
  details?: unknown,
  level: RuntimeDiagnosticLevel = 'info',
): void {
  const entries = getMemDiagnostics()
  entries.push({
    at: new Date().toISOString(),
    session: sessionId,
    level,
    scope: String(scope || 'runtime'),
    event: String(event || 'event'),
    details: details == null ? undefined : safeStringify(details),
  })
  if (entries.length > MAX_RUNTIME_DIAGNOSTICS * 2) {
    memDiagnostics = entries.slice(-MAX_RUNTIME_DIAGNOSTICS)
  }
  scheduleFlush()
  notify()
}

export function clearRuntimeDiagnostics(): void {
  if (typeof window === 'undefined') return
  memDiagnostics = []
  if (flushTimer !== null) { clearTimeout(flushTimer); flushTimer = null }
  window.localStorage.removeItem(RUNTIME_DIAG_KEY)
  notify()
}

function flushNow(): void {
  if (flushTimer !== null) { clearTimeout(flushTimer); flushTimer = null }
  if (typeof window === 'undefined' || memDiagnostics === null) return
  try {
    window.localStorage.setItem(
      RUNTIME_DIAG_KEY,
      JSON.stringify(memDiagnostics.slice(-MAX_RUNTIME_DIAGNOSTICS)),
    )
  } catch {
    // ignore
  }
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
    flushNow()
  })
  window.addEventListener('beforeunload', () => {
    recordRuntimeDiagnostic('window', 'beforeunload')
    flushNow()
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
