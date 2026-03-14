import { resolveClientMode } from './clientMode'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

let desktopPrewarmPromise: Promise<void> | null = null

export function ensureDesktopBootstrap(): Promise<void> {
  if (resolveClientMode() !== 'desktop') return Promise.resolve()
  if (!desktopPrewarmPromise) {
    desktopPrewarmPromise = (async () => {
      recordRuntimeDiagnostic('desktop.bootstrap', 'start')
      const { prewarmDesktopMediaRuntime } = await import('../runtime/desktopMediaFlow')
      await prewarmDesktopMediaRuntime((message, progress) => {
        recordRuntimeDiagnostic('desktop.bootstrap', 'progress', { message, progress })
      })
      recordRuntimeDiagnostic('desktop.bootstrap', 'ready')
    })().catch((error) => {
      desktopPrewarmPromise = null
      recordRuntimeDiagnostic('desktop.bootstrap', 'error', error, 'error')
      throw error
    })
  }
  return desktopPrewarmPromise
}
