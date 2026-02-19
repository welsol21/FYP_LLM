import { useEffect, useMemo, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { RuntimeUiState, TranslationConfig, TranslationProviderConfig } from '../api/runtimeApi'
import { RuntimeStatusCard } from '../components/RuntimeStatusCard'

export function ConfigPage() {
  const api = useApi()
  const [uiState, setUiState] = useState<RuntimeUiState | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [providerErrors, setProviderErrors] = useState<Record<string, string>>({})
  const [newProviderId, setNewProviderId] = useState('')
  const [newProviderLabel, setNewProviderLabel] = useState('')
  const [newCredentialFields, setNewCredentialFields] = useState('')

  useEffect(() => {
    api.getUiState().then(setUiState)
    api.getTranslationConfig().then(setTranslationConfig)
  }, [api])

  const providerIds = useMemo(
    () => new Set((translationConfig?.providers || []).map((p) => p.id.toLowerCase())),
    [translationConfig],
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
        {
          id,
          label: label || id,
          kind: 'custom',
          enabled: true,
          credential_fields: fields,
          credentials,
        },
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
      <RuntimeStatusCard uiState={uiState} />
      <section className="card">
        <h2>Translation Providers</h2>
        {translationConfig ? (
          <>
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

            <div className="card compact-card">
              <h3>Add Custom Provider</h3>
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

            {translationConfig.providers.map((p) => (
              <div key={p.id} className="card compact-card">
                <div className="top-tabs" style={{ marginBottom: 8 }}>
                  <strong>{p.label}</strong>
                  <span className="badge">{p.id}</span>
                </div>
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
                {p.kind === 'custom' ? (
                  <button type="button" onClick={() => removeCustomProvider(p.id)}>
                    Remove Provider
                  </button>
                ) : null}
              </div>
            ))}
          </>
        ) : (
          <p>Loading translation config...</p>
        )}
      </section>
    </section>
  )
}
