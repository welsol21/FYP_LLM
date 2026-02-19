import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { MediaFileRow, SelectedProject } from '../api/runtimeApi'

export function FilesPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<MediaFileRow[]>([])
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const tapRef = useRef<{ rowId: string; ts: number } | null>(null)

  async function refreshFiles(projectId: string | null | undefined) {
    if (!projectId) {
      setRows([])
      return
    }
    const items = await api.listFiles(projectId)
    setRows(items)
  }

  useEffect(() => {
    let alive = true
    api.getSelectedProject().then((selected) => {
      if (!alive) return
      setSelectedProject(selected)
      if (!selected.project_id) return setRows([])
      api.listFiles(selected.project_id).then((items) => {
        if (alive) setRows(items)
      })
    })
    return () => {
      alive = false
    }
  }, [api])

  function openAnalyze(row: MediaFileRow) {
    navigate('/analyze', {
      state: {
        selectedMedia: {
          mediaFileId: row.id,
          fileName: row.name,
          mediaPath: row.path ?? `/uploads/${row.name}`,
          sizeBytes: row.size_bytes ?? 100 * 1024 * 1024,
          durationSec: row.duration_seconds ?? 600,
        },
      },
    })
  }

  function onRowTap(row: MediaFileRow) {
    const now = Date.now()
    const lastTap = tapRef.current
    if (lastTap && lastTap.rowId === row.id && now - lastTap.ts < 350) {
      openAnalyze(row)
      tapRef.current = null
      return
    }
    tapRef.current = { rowId: row.id, ts: now }
  }

  return (
    <section className="screen-block">
      <div className="page-head">
        <h2 className="page-title">{selectedProject.project_name ?? selectedProject.project_id ?? 'Project'}</h2>
        <button type="button" className="secondary-btn" onClick={() => inputRef.current?.click()}>
          New File
        </button>
      </div>

      <input
        ref={inputRef}
        aria-label="Media File"
        type="file"
        accept=".mp3,.wav,.m4a,.flac,.ogg,.mp4,.mkv,.mov,.avi,.webm,.pdf,.txt"
        style={{ display: 'none' }}
        onChange={async (e) => {
          const inputEl = e.currentTarget
          const file = e.target.files?.[0]
          if (!file || !selectedProject.project_id) return
          setUploading(true)
          setUploadError('')
          try {
            const uploaded = await api.uploadMedia(file)
            await api.registerMediaFile({
              projectId: selectedProject.project_id,
              name: uploaded.fileName,
              mediaPath: uploaded.mediaPath,
              sizeBytes: uploaded.sizeBytes,
              durationSec: 1,
            })
            await refreshFiles(selectedProject.project_id)
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err)
            setUploadError(msg)
          } finally {
            setUploading(false)
            inputEl.value = ''
          }
        }}
      />
      {uploading ? <p>Uploading...</p> : null}
      {uploadError ? <p style={{ color: '#ff6b6b' }}>{uploadError}</p> : null}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Settings</th>
            <th>Updated</th>
            <th>Analyzed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} onClick={() => onRowTap(row)} aria-label={`file-row-${row.id}`} style={{ cursor: 'pointer' }}>
              <td>{row.name}</td>
              <td>{row.settings}</td>
              <td>{new Date(row.updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</td>
              <td>{row.analyzed ? 'Yes' : 'No'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

