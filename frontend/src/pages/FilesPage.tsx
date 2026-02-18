import { useEffect, useState } from 'react'
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

  function onRowDoubleClick(row: MediaFileRow) {
    if (!row.analyzed || !row.document_id) return
    navigate('/visualizer', { state: { documentId: row.document_id } })
  }

  return (
    <section className="card">
      <h1>Files</h1>
      <p>Project: {selectedProject.project_name ?? selectedProject.project_id ?? 'not selected'}</p>
      {!selectedProject.project_id ? <p>Select project on Media tab first.</p> : null}
      {selectedProject.project_id ? (
        <section className="card compact-card" aria-label="files-upload-form">
          <h2>Add File To Project</h2>
          <label>
            Media File
            <input
              type="file"
              accept=".mp3,.wav,.m4a,.flac,.ogg,.mp4,.mkv,.mov,.avi,.webm,.pdf,.txt"
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
          </label>
          {uploading ? <p>Uploading...</p> : null}
          {uploadError ? <p style={{ color: '#ff6b6b' }}>{uploadError}</p> : null}
        </section>
      ) : null}
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
            <tr
              key={row.id}
              onDoubleClick={() => onRowDoubleClick(row)}
              aria-label={`file-row-${row.id}`}
              style={{ cursor: row.analyzed ? 'pointer' : 'default' }}
            >
              <td>{row.name}</td>
              <td>{row.settings}</td>
              <td>{row.updated}</td>
              <td>{row.analyzed ? 'yes' : 'no'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
