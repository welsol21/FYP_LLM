export type ClientMode = 'pwa' | 'desktop'

export type VoiceOption = {
  label: string
  value: string
}

function normalizedEnvMode(): string {
  return String(import.meta.env?.VITE_CLIENT_MODE || '')
    .trim()
    .toLowerCase()
}

export function resolveClientMode(): ClientMode {
  const envMode = normalizedEnvMode()
  if (envMode === 'pwa' || envMode === 'desktop') return envMode

  if (typeof window !== 'undefined' && '__TAURI__' in window) return 'desktop'

  const standalone = typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(display-mode: standalone)').matches
  const iosStandalone = typeof navigator !== 'undefined'
    && Boolean((navigator as Navigator & { standalone?: boolean }).standalone)
  const mobileUa = typeof navigator !== 'undefined'
    && /android|iphone|ipad|ipod|mobile/i.test(String(navigator.userAgent || ''))

  if (standalone || iosStandalone || mobileUa) return 'pwa'
  return 'desktop'
}

export function getVoiceOptionsForClientMode(mode: ClientMode, _online: boolean): VoiceOption[] {
  if (mode === 'pwa') {
    return [
      { label: 'Dmitry (Male)', value: 'backend_dmitry' },
      { label: 'Svetlana (Female)', value: 'backend_svetlana' },
    ]
  }
  return [
    { label: 'Male', value: 'client_male' },
    { label: 'Dmitry (Male)', value: 'client_dmitry' },
    { label: 'Svetlana (Female)', value: 'client_svetlana' },
  ]
}

export function getDefaultVoiceLabel(mode: ClientMode, online: boolean): string {
  return getVoiceOptionsForClientMode(mode, online)[0]?.label || 'Male'
}
