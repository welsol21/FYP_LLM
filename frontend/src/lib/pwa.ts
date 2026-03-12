type DeferredInstallPrompt = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

let deferredPrompt: DeferredInstallPrompt | null = null
const listeners = new Set<() => void>()

function notify(): void {
  for (const listener of listeners) listener()
}

export function initPwaSupport(): void {
  if (typeof window === 'undefined') return

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferredPrompt = event as DeferredInstallPrompt
    notify()
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null
    notify()
  })

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      void navigator.serviceWorker.register('/sw.js').catch(() => undefined)
    })
  }
}

export function canInstallPwa(): boolean {
  return deferredPrompt != null
}

export async function triggerPwaInstall(): Promise<boolean> {
  if (!deferredPrompt) return false
  const prompt = deferredPrompt
  await prompt.prompt()
  const choice = await prompt.userChoice
  deferredPrompt = null
  notify()
  return choice.outcome === 'accepted'
}

export function subscribePwaInstall(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
