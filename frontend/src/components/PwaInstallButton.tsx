import { useEffect, useState } from 'react'
import { canInstallPwa, shouldShowInstallControl, subscribePwaInstall, triggerPwaInstall } from '../lib/pwa'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'

export function PwaInstallButton() {
  const [available, setAvailable] = useState(canInstallPwa())
  const [visible, setVisible] = useState(shouldShowInstallControl())

  useEffect(() => {
    return subscribePwaInstall(() => {
      setAvailable(canInstallPwa())
      setVisible(shouldShowInstallControl())
    })
  }, [])

  if (!visible) return null

  return (
    <button
      type="button"
      className="top-link install-link"
      onClick={() => {
        if (!available) {
          window.alert('Install prompt is unavailable. Use browser menu: "Install app" / "Add to Home Screen".')
          recordRuntimeDiagnostic('ui.install', 'manual_hint_shown')
          return
        }
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
