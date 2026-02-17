import type { RuntimeUiState } from '../api/runtimeApi'

type Props = { uiState: RuntimeUiState | null }

export function RuntimeStatusCard({ uiState }: Props) {
  if (!uiState) return <section aria-label="runtime-status">Loading runtime state...</section>

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
      <ul>
        {Object.entries(uiState.features).map(([name, cfg]) => (
          <li key={name}>
            <strong>{name}:</strong> {cfg.enabled ? 'enabled' : 'disabled'}
            {!cfg.enabled && cfg.reason_if_disabled ? ` — ${cfg.reason_if_disabled}` : ''}
          </li>
        ))}
      </ul>
    </section>
  )
}
