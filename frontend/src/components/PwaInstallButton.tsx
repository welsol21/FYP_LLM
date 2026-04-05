import { useEffect, useState } from 'react'
import { canInstallPwa, subscribePwaInstall, triggerPwaInstall } from '../lib/pwa'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'

export function PwaInstallButton() {
  const [available, setAvailable] = useState(canInstallPwa())

  useEffect(() => {
    return subscribePwaInstall(() => {
      setAvailable(canInstallPwa())
    })
  }, [])

  if (!available) return null

  return (
    <button
      type="button"
      className="top-link install-link"
      onClick={() => {
        void triggerPwaInstall().catch((error) => {
          recordRuntimeDiagnostic('ui.install', 'click_failed', error, 'error')
        })
      }}
      aria-label="Install app"
    >
      Install
    </button>
  )
}
