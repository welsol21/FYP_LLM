import { useState } from 'react'
import { useApi } from '../api/apiContext'
import type { MediaSubmissionPayload } from '../api/runtimeApi'

type Props = {
  onSubmitted: (payload: MediaSubmissionPayload) => void
  projectId: string | null
}

export function MediaSubmitForm({ onSubmitted, projectId }: Props) {
  const api = useApi()
  const [mediaPath, setMediaPath] = useState('/tmp/demo.mp4')
  const [durationSec, setDurationSec] = useState(600)
  const [sizeBytes, setSizeBytes] = useState(100 * 1024 * 1024)
  const [selectedFileName, setSelectedFileName] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [uploading, setUploading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = await api.submitMedia({ mediaPath, durationSec, sizeBytes, projectId: projectId ?? undefined })
      onSubmitted(payload)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card" aria-label="media-submit-form">
      <h2>Analyze Media</h2>
      <p>Project: {projectId ?? 'not selected'}</p>
      <label>
        Media File
        <input
          type="file"
          accept=".mp3,.wav,.m4a,.flac,.ogg,.mp4,.mkv,.mov,.avi,.webm,.pdf,.txt"
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (!file) return
            setUploading(true)
            setUploadError('')
            try {
              const uploaded = await api.uploadMedia(file)
              setSelectedFileName(uploaded.fileName)
              setMediaPath(uploaded.mediaPath)
              setSizeBytes(uploaded.sizeBytes)
            } catch (err) {
              const msg = err instanceof Error ? err.message : String(err)
              setUploadError(msg)
            } finally {
              setUploading(false)
            }
          }}
        />
      </label>
      {selectedFileName ? <p>Selected: {selectedFileName}</p> : null}
      {uploading ? <p>Uploading...</p> : null}
      {uploadError ? <p style={{ color: '#ff6b6b' }}>{uploadError}</p> : null}
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
      <button type="submit" disabled={submitting || uploading || !mediaPath || !projectId}>
        {submitting ? 'Submitting...' : 'Start'}
      </button>
    </form>
  )
}
