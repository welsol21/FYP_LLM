import { useEffect, useMemo, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { RuntimeUiState, TranslationConfig, TranslationProviderConfig } from '../api/runtimeApi'
import { RuntimeStatusCard } from '../components/RuntimeStatusCard'
import { clearPwaDiagnostics, getPwaDiagnostics, subscribePwaDiagnostics } from '../lib/pwa'
import { clearRuntimeDiagnostics, getRuntimeDiagnostics, subscribeRuntimeDiagnostics } from '../lib/runtimeDiagnostics'

function downloadTextFile(fileName: string, text: string): void {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function copyText(text: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', 'true')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  document.execCommand('copy')
  area.remove()
}

type LogToast = { id: number; message: string; ok: boolean }
let toastSeq = 0

export function ConfigPage() {
  const api = useApi()
  const [uiState, setUiState] = useState<RuntimeUiState | null>(null)
  const [uiStateStatus, setUiStateStatus] = useState<'loading' | 'ok' | 'unavailable'>('loading')
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [providerErrors, setProviderErrors] = useState<Record<string, string>>({})
  const [newProviderId, setNewProviderId] = useState('')
  const [newProviderLabel, setNewProviderLabel] = useState('')
  const [newCredentialFields, setNewCredentialFields] = useState('')
  const [pwaDiagnostics, setPwaDiagnostics] = useState(getPwaDiagnostics())
  const [runtimeDiagnostics, setRuntimeDiagnostics] = useState(getRuntimeDiagnostics())
  const [toasts, setToasts] = useState<LogToast[]>([])
  const [activeBtn, setActiveBtn] = useState<string | null>(null)

  function showToast(message: string, ok: boolean) {
    const id = ++toastSeq
    setToasts((prev) => [...prev, { id, message, ok }])
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3500)
  }

  function pressBtn(key: string, action: () => void | Promise<void>) {
    setActiveBtn(key)
    window.setTimeout(() => setActiveBtn(null), 180)
    void Promise.resolve(action()).catch(() => undefined)
  }

  useEffect(() => {
    let cancelled = false
    api.getUiState()
      .then((value) => { if (!cancelled) { setUiState(value); setUiStateStatus('ok') } })
      .catch(() => { if (!cancelled) setUiStateStatus('unavailable') })
    api.getTranslationConfig()
      .then((value) => { if (!cancelled) setTranslationConfig(value) })
      .catch(() => { if (!cancelled) setTranslationConfig(null) })
    return () => { cancelled = true }
  }, [api])

  useEffect(() => subscribePwaDiagnostics(() => setPwaDiagnostics(getPwaDiagnostics())), [])
  useEffect(() => subscribeRuntimeDiagnostics(() => setRuntimeDiagnostics(getRuntimeDiagnostics())), [])

  const providerIds = useMemo(
    () => new Set((translationConfig?.providers || []).map((p) => p.id.toLowerCase())),
    [translationConfig],
  )
  const runtimeLogText = useMemo(
    () => runtimeDiagnostics
      .slice()
      .reverse()
      .map((entry) => `${entry.at} [${entry.session}] ${entry.level.toUpperCase()} ${entry.scope}.${entry.event}${entry.details ? ` :: ${entry.details}` : ''}`)
      .join('\n'),
    [runtimeDiagnostics],
  )
  const pwaLogText = useMemo(
    () => pwaDiagnostics
      .slice()
      .reverse()
      .map((entry) => `${entry.at} [${entry.session}] ${entry.event}${entry.details ? ` :: ${entry.details}` : ''}`)
      .join('\n'),
    [pwaDiagnostics],
  )

  function missingCredentialFields(provider: TranslationProviderConfig): string[] {
    return provider.credential_fields.filter((field) => !String(provider.credentials[field] || '').trim())
  }

  async function persistConfig(nextConfig: TranslationConfig) {
    const saved = await api.saveTranslationConfig(nextConfig)
    setTranslationConfig(saved)
  }

  async function patchProvider(providerId: string, patch: Partial<TranslationProviderConfig>) {
    if (!translationConfig) return
    const current = translationConfig.providers.find((p) => p.id === providerId)
    if (!current) return
    const draft = { ...current, ...patch }
    if (patch.enabled === true) {
      const missing = missingCredentialFields(draft)
      if (missing.length > 0) {
        setProviderErrors((prev) => ({ ...prev, [providerId]: `Missing credentials: ${missing.join(', ')}` }))
        return
      }
    }
    setProviderErrors((prev) => ({ ...prev, [providerId]: '' }))
    const nextProviders = translationConfig.providers.map((p) => (p.id === providerId ? { ...p, ...patch } : p))
    await persistConfig({ ...translationConfig, providers: nextProviders })
  }

  async function patchProviderCred(providerId: string, key: string, value: string) {
    if (!translationConfig) return
    const nextProviders = translationConfig.providers.map((p) => {
      if (p.id !== providerId) return p
      return { ...p, credentials: { ...p.credentials, [key]: value } }
    })
    setProviderErrors((prev) => ({ ...prev, [providerId]: '' }))
    await persistConfig({ ...translationConfig, providers: nextProviders })
  }

  async function addCustomProvider() {
    if (!translationConfig) return
    const id = newProviderId.trim().toLowerCase()
    const label = newProviderLabel.trim()
    if (!id || providerIds.has(id)) return
    const fields = newCredentialFields
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    const credentials: Record<string, string> = {}
    for (const field of fields) credentials[field] = ''
    await persistConfig({
      ...translationConfig,
      providers: [
        ...translationConfig.providers,
        { id, label: label || id, kind: 'custom', enabled: true, credential_fields: fields, credentials },
      ],
    })
    setNewProviderId('')
    setNewProviderLabel('')
    setNewCredentialFields('')
  }

  async function removeCustomProvider(providerId: string) {
    if (!translationConfig) return
    const next = translationConfig.providers.filter((p) => p.id !== providerId)
    const defaultProvider = translationConfig.default_provider === providerId ? 'm2m100' : translationConfig.default_provider
    await persistConfig({ ...translationConfig, providers: next, default_provider: defaultProvider })
  }

  return (
    <section>
      <RuntimeStatusCard uiState={uiState} status={uiStateStatus} />

      {/* ── Translation Providers ── */}
      <details className="config-group" open>
        <summary>Translation Providers</summary>
        <div className="config-group-body">
          {translationConfig ? (
            <>
              {/* Default provider */}
              <div>
                <label className="analyze-label">Default Provider</label>
                <div className="touch-options-grid">
                  {translationConfig.providers
                    .filter((p) => p.enabled)
                    .map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        className={`touch-option-btn${translationConfig.default_provider === p.id ? ' active' : ''}`}
                        onClick={() => persistConfig({ ...translationConfig, default_provider: p.id })}
                      >
                        {p.label}
                      </button>
                    ))}
                </div>
              </div>

              {/* Individual providers */}
              {translationConfig.providers.map((p) => (
                <details key={p.id} className="config-subgroup" open={p.enabled}>
                  <summary>
                    {p.label}
                    <span className="badge">{p.id}</span>
                    {p.enabled && <span className="badge" style={{ background: '#1a3a2a', color: '#5fca8a', borderColor: '#2a5a3a' }}>on</span>}
                  </summary>
                  <div className="config-subgroup-body">
                    <label className="touch-checkbox">
                      <input type="checkbox" checked={p.enabled} onChange={(e) => patchProvider(p.id, { enabled: e.target.checked })} />
                      Enabled
                    </label>
                    {providerErrors[p.id] ? <p className="config-error">{providerErrors[p.id]}</p> : null}
                    {p.credential_fields.map((field) => (
                      <div key={`${p.id}-${field}`}>
                        <label className="analyze-label">{field}</label>
                        <input
                          className="flat-input"
                          value={p.credentials[field] || ''}
                          onChange={(e) => patchProviderCred(p.id, field, e.target.value)}
                          placeholder={`${p.label} ${field}`}
                        />
                      </div>
                    ))}
                    {p.kind === 'custom' && (
                      <button type="button" onClick={() => removeCustomProvider(p.id)}>
                        Remove Provider
                      </button>
                    )}
                  </div>
                </details>
              ))}

              {/* Add custom provider */}
              <details className="config-subgroup">
                <summary>Add Custom Provider</summary>
                <div className="config-subgroup-body">
                  <input className="flat-input" placeholder="Provider ID (e.g. myapi)" value={newProviderId} onChange={(e) => setNewProviderId(e.target.value)} />
                  <input className="flat-input" placeholder="Label" value={newProviderLabel} onChange={(e) => setNewProviderLabel(e.target.value)} />
                  <input
                    className="flat-input"
                    placeholder="Credential fields (comma-separated)"
                    value={newCredentialFields}
                    onChange={(e) => setNewCredentialFields(e.target.value)}
                  />
                  <button type="button" onClick={addCustomProvider} disabled={!newProviderId.trim() || providerIds.has(newProviderId.trim().toLowerCase())}>
                    Add Provider
                  </button>
                </div>
              </details>
            </>
          ) : (
            <p>Loading translation config...</p>
          )}
        </div>
      </details>

      {/* ── Diagnostics ── */}
      <details className="config-group">
        <summary>Diagnostics</summary>
        <div className="config-group-body">
          {toasts.length > 0 && (
            <div className="log-toasts">
              {toasts.map((t) => (
                <div key={t.id} className={`log-toast ${t.ok ? 'log-toast-ok' : 'log-toast-err'}`}>
                  {t.message}
                </div>
              ))}
            </div>
          )}
          <div className="touch-options-grid">
            <button
              type="button"
              className={`touch-option-btn${activeBtn === 'export-runtime' ? ' active' : ''}`}
              onClick={() => pressBtn('export-runtime', () => {
                downloadTextFile('runtime_diagnostics.log', runtimeLogText || 'No runtime diagnostics.')
                showToast('Runtime logs saved → runtime_diagnostics.log', true)
              })}
            >
              Export Runtime Logs
            </button>
            <button
              type="button"
              className={`touch-option-btn${activeBtn === 'export-pwa' ? ' active' : ''}`}
              onClick={() => pressBtn('export-pwa', () => {
                downloadTextFile('pwa_diagnostics.log', pwaLogText || 'No PWA diagnostics.')
                showToast('PWA logs saved → pwa_diagnostics.log', true)
              })}
            >
              Export PWA Logs
            </button>
            <button
              type="button"
              className={`touch-option-btn${activeBtn === 'copy-runtime' ? ' active' : ''}`}
              onClick={() => pressBtn('copy-runtime', async () => {
                try {
                  await copyText(runtimeLogText || 'No runtime diagnostics.')
                  showToast('Runtime logs copied to clipboard', true)
                } catch {
                  showToast('Failed to copy to clipboard', false)
                }
              })}
            >
              Copy Runtime Logs
            </button>
            <button
              type="button"
              className={`touch-option-btn${activeBtn === 'clear-logs' ? ' active' : ''}`}
              onClick={() => pressBtn('clear-logs', () => {
                clearRuntimeDiagnostics()
                clearPwaDiagnostics()
                setRuntimeDiagnostics(getRuntimeDiagnostics())
                setPwaDiagnostics(getPwaDiagnostics())
                showToast('All logs cleared', true)
              })}
            >
              Clear Logs
            </button>
          </div>
          <div className="config-log-preview">
            <strong>Recent Runtime Logs</strong>
            <pre className="log-preview">
              {runtimeDiagnostics.length
                ? runtimeDiagnostics
                  .slice(-20)
                  .reverse()
                  .map((entry) => `${entry.at} [${entry.level}] ${entry.scope}.${entry.event}${entry.details ? ` :: ${entry.details}` : ''}`)
                  .join('\n')
                : 'No runtime diagnostics yet.'}
            </pre>
          </div>
        </div>
      </details>
    </section>
  )
}
