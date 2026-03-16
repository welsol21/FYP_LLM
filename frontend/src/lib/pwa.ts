import { recordRuntimeDiagnostic } from './runtimeDiagnostics'
import { isTauriRuntime } from './clientMode'

type DeferredInstallPrompt = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

let deferredPrompt: DeferredInstallPrompt | null = null
const listeners = new Set<() => void>()
const diagnosticListeners = new Set<() => void>()
const DIAG_KEY = 'ela_pwa_diagnostics_v1'
const MAX_DIAGNOSTICS = 60
const sessionId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

function notify(): void {
  for (const listener of listeners) listener()
}

function notifyDiagnostics(): void {
  for (const listener of diagnosticListeners) listener()
}

type PwaDiagnosticEntry = {
  at: string
  session: string
  event: string
  details?: string
}

function readDiagnostics(): PwaDiagnosticEntry[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = String(window.localStorage.getItem(DIAG_KEY) || '')
    if (!raw) return []
    const parsed = JSON.parse(raw) as PwaDiagnosticEntry[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeDiagnostics(entries: PwaDiagnosticEntry[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(DIAG_KEY, JSON.stringify(entries.slice(-MAX_DIAGNOSTICS)))
  } catch {
    // ignore
  }
}

function diagDetails(extra?: string): string {
  const bits = [
    `path=${typeof window !== 'undefined' ? window.location.pathname : '-'}`,
    `vis=${typeof document !== 'undefined' ? document.visibilityState : '-'}`,
    `online=${typeof navigator !== 'undefined' ? navigator.onLine : false}`,
    `ctrl=${typeof navigator !== 'undefined' && 'serviceWorker' in navigator ? Boolean(navigator.serviceWorker.controller) : false}`,
  ]
  if (extra) bits.push(extra)
  return bits.join(' ')
}

function recordDiagnostic(event: string, details?: string): void {
  recordRuntimeDiagnostic('pwa', event, details)
  const entries = readDiagnostics()
  entries.push({
    at: new Date().toISOString(),
    session: sessionId,
    event,
    details: details || diagDetails(),
  })
  writeDiagnostics(entries)
  notifyDiagnostics()
}

export function initPwaSupport(): void {
  if (typeof window === 'undefined') return
  recordDiagnostic('boot', diagDetails())

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferredPrompt = event as DeferredInstallPrompt
    recordDiagnostic('beforeinstallprompt')
    notify()
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null
    recordDiagnostic('appinstalled')
    notify()
  })

  window.addEventListener('pageshow', (event) => {
    recordDiagnostic('pageshow', diagDetails(`persisted=${Boolean((event as PageTransitionEvent).persisted)}`))
  })
  window.addEventListener('pagehide', (event) => {
    recordDiagnostic('pagehide', diagDetails(`persisted=${Boolean((event as PageTransitionEvent).persisted)}`))
  })
  window.addEventListener('beforeunload', () => {
    recordDiagnostic('beforeunload')
  })
  window.addEventListener('online', () => {
    recordDiagnostic('online')
  })
  window.addEventListener('offline', () => {
    recordDiagnostic('offline')
  })
  window.addEventListener('error', (event) => {
    recordDiagnostic('error', diagDetails(String(event.message || 'unknown')))
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? event.reason.message : String(event.reason || 'unknown')
    recordDiagnostic('unhandledrejection', diagDetails(reason))
  })
  document.addEventListener('visibilitychange', () => {
    recordDiagnostic('visibilitychange')
  })

  if (!isTauriRuntime() && 'serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      recordDiagnostic('sw.controllerchange')
    })
    window.addEventListener('load', () => {
      void navigator.serviceWorker.register('/sw.js')
        .then((registration) => {
          recordDiagnostic('sw.registered', diagDetails(`scope=${registration.scope}`))
          registration.addEventListener('updatefound', () => {
            recordDiagnostic('sw.updatefound')
          })
        })
        .catch((error) => {
          recordDiagnostic('sw.register_failed', diagDetails(error instanceof Error ? error.message : String(error)))
        })
    })
  } else if (isTauriRuntime()) {
    recordDiagnostic('sw.skipped', diagDetails('tauri_runtime=true'))
  }
}

export function canInstallPwa(): boolean {
  return deferredPrompt != null
}

export async function triggerPwaInstall(): Promise<boolean> {
  if (!deferredPrompt) return false
  const prompt = deferredPrompt
  try {
    recordDiagnostic('install.click')
    await prompt.prompt()
    recordDiagnostic('install.prompt.open')
    const choice = await prompt.userChoice
    recordDiagnostic(`install.choice.${choice.outcome}`, choice.platform)
    deferredPrompt = null
    notify()
    return choice.outcome === 'accepted'
  } catch (error) {
    recordDiagnostic('install.error', error instanceof Error ? error.message : String(error))
    throw error
  }
}

export function subscribePwaInstall(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getPwaDiagnostics(): PwaDiagnosticEntry[] {
  return readDiagnostics()
}

export function clearPwaDiagnostics(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(DIAG_KEY)
  notifyDiagnostics()
}

export function subscribePwaDiagnostics(listener: () => void): () => void {
  diagnosticListeners.add(listener)
  return () => {
    diagnosticListeners.delete(listener)
  }
}
