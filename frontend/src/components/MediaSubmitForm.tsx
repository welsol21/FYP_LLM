import { useState } from 'react'
import { useApi } from '../api/apiContext'
import type { MediaSubmissionPayload } from '../api/runtimeApi'

type Props = {
  onSubmitted: (payload: MediaSubmissionPayload) => void
}

export function MediaSubmitForm({ onSubmitted }: Props) {
  const api = useApi()
  const [mediaPath, setMediaPath] = useState('/tmp/demo.mp4')
  const [durationSec, setDurationSec] = useState(600)
  const [sizeBytes, setSizeBytes] = useState(100 * 1024 * 1024)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = await api.submitMedia({ mediaPath, durationSec, sizeBytes })
      onSubmitted(payload)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card" aria-label="media-submit-form">
      <h2>Analyze Media</h2>
      <label>
        Media Path
        <input value={mediaPath} onChange={(e) => setMediaPath(e.target.value)} />
      </label>
      <label>
        Duration (sec)
        <input
          type="number"
          value={durationSec}
          onChange={(e) => setDurationSec(Number(e.target.value))}
          min={1}
        />
      </label>
      <label>
        Size (bytes)
        <input
          type="number"
          value={sizeBytes}
          onChange={(e) => setSizeBytes(Number(e.target.value))}
          min={1}
        />
      </label>
      <button type="submit" disabled={submitting}>
        {submitting ? 'Submitting...' : 'Start'}
      </button>
    </form>
  )
}
