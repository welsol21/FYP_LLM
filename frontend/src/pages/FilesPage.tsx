import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { MediaFileRow, SelectedProject } from '../api/runtimeApi'

export function FilesPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<MediaFileRow[]>([])
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })

  useEffect(() => {
    let alive = true
    api.getSelectedProject().then((selected) => {
      if (!alive) return
      setSelectedProject(selected)
      if (!selected.project_id) {
        setRows([])
        return
      }
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
