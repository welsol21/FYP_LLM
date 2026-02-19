import { useEffect, useMemo, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { RuntimeUiState, TranslationConfig, TranslationProviderConfig } from '../api/runtimeApi'
import { RuntimeStatusCard } from '../components/RuntimeStatusCard'

export function ConfigPage() {
  const api = useApi()
  const [uiState, setUiState] = useState<RuntimeUiState | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [saveMsg, setSaveMsg] = useState<string>('')
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

  function patchProvider(providerId: string, patch: Partial<TranslationProviderConfig>) {
    if (!translationConfig) return
    const nextProviders = translationConfig.providers.map((p) => (p.id === providerId ? { ...p, ...patch } : p))
    setTranslationConfig({ ...translationConfig, providers: nextProviders })
  }

  function patchProviderCred(providerId: string, key: string, value: string) {
    if (!translationConfig) return
    const nextProviders = translationConfig.providers.map((p) => {
      if (p.id !== providerId) return p
      return { ...p, credentials: { ...p.credentials, [key]: value } }
    })
    setTranslationConfig({ ...translationConfig, providers: nextProviders })
  }

  function addCustomProvider() {
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
    setTranslationConfig({
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

  function removeCustomProvider(providerId: string) {
    if (!translationConfig) return
    const next = translationConfig.providers.filter((p) => p.id !== providerId)
    const defaultProvider = translationConfig.default_provider === providerId ? 'm2m100' : translationConfig.default_provider
    setTranslationConfig({ ...translationConfig, providers: next, default_provider: defaultProvider })
  }

  async function saveConfig() {
    if (!translationConfig) return
    const saved = await api.saveTranslationConfig(translationConfig)
    setTranslationConfig(saved)
    setSaveMsg('Saved')
    setTimeout(() => setSaveMsg(''), 1200)
  }

  return (
    <section>
      <RuntimeStatusCard uiState={uiState} />
      <section className="card">
        <h2>Translation Providers</h2>
        {translationConfig ? (
          <>
            <label className="analyze-label">Default Provider</label>
            <select
              className="flat-select"
              value={translationConfig.default_provider}
              onChange={(e) => setTranslationConfig({ ...translationConfig, default_provider: e.target.value })}
            >
              {translationConfig.providers
                .filter((p) => p.enabled)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
            </select>

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

            <button type="button" onClick={saveConfig}>
              Save Translation Config
            </button>
            {saveMsg ? <p>{saveMsg}</p> : null}
          </>
        ) : (
          <p>Loading translation config...</p>
        )}
      </section>
    </section>
  )
}
