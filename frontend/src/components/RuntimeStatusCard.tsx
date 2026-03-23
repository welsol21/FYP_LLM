import type { RuntimeUiState } from '../api/runtimeApi'

type Props = { uiState: RuntimeUiState | null }

export function RuntimeStatusCard({ uiState }: Props) {
  if (!uiState) return <section aria-label="runtime-status">Loading runtime state...</section>

  const userFacingFeatures = Object.entries(uiState.features).filter(
    ([name]) => name !== 'phonetic' && name !== 'db_persistence',
  )

  return (
    <section aria-label="runtime-status" className="card">
      <h2>Runtime Capabilities</h2>
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
