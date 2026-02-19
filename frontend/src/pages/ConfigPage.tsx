import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { RuntimeUiState } from '../api/runtimeApi'
import { RuntimeStatusCard } from '../components/RuntimeStatusCard'

export function ConfigPage() {
  const api = useApi()
  const [uiState, setUiState] = useState<RuntimeUiState | null>(null)

  useEffect(() => {
    api.getUiState().then(setUiState)
  }, [api])

  return (
    <section>
      <RuntimeStatusCard uiState={uiState} />
      <section className="card">
        <h2>Legacy Screens (Stubs)</h2>
        <p>
          `New Project`, `New File`, `Analyze List` are added as navigation stubs and will be wired next.
        </p>
        <p>
          <Link to="/new-project">Open New Project Stub</Link>
        </p>
        <p>
          <Link to="/new-file">Open New File Stub</Link>
        </p>
        <p>
          <Link to="/analyze-list">Open Analyze List Stub</Link>
        </p>
      </section>
    </section>
  )
}
