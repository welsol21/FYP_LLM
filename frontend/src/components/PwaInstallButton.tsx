import { useEffect, useState } from 'react'
import { canInstallPwa, subscribePwaInstall, triggerPwaInstall } from '../lib/pwa'

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
        void triggerPwaInstall()
      }}
      aria-label="Install app"
    >
      Install
    </button>
  )
}
