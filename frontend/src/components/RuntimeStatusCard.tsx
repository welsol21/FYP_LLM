import type { RuntimeUiState } from '../api/runtimeApi'

type Props = {
  uiState: RuntimeUiState | null
  status: 'loading' | 'ok' | 'unavailable'
}

export function RuntimeStatusCard({ uiState, status }: Props) {
  if (status === 'loading') {
    return (
      <section className="card runtime-status-card runtime-status-loading">
        <h2>Connection Status</h2>
        <p className="runtime-status-msg">Connecting to server…</p>
      </section>
    )
  }

  if (status === 'unavailable' || !uiState) {
    return (
      <section className="card runtime-status-card runtime-status-offline">
        <h2>Connection Status</h2>
        <p className="runtime-status-msg">Server unavailable — running on local ML models</p>
      </section>
    )
  }

  const userFacingFeatures = Object.entries(uiState.features).filter(
    ([name]) => name !== 'phonetic' && name !== 'db_persistence',
  )

  return (
    <section className="card runtime-status-card runtime-status-online">
      <h2>Connection Status</h2>
      <div className="badge-row">
        {Object.values(uiState.badges).map((badge) => (
          <span key={badge} className="badge">
            {badge}
          </span>
        ))}
      </div>
      {userFacingFeatures.length > 0 ? (
        <ul>
          {userFacingFeatures.map(([name, cfg]) => (
            <li key={name}>
              <strong>{name}:</strong> {cfg.enabled ? 'enabled' : 'disabled'}
              {!cfg.enabled && cfg.reason_if_disabled ? ` — ${cfg.reason_if_disabled}` : ''}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
