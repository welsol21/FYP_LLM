import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { MediaFileRow } from '../api/runtimeApi'

export function FilesPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<MediaFileRow[]>([])

  useEffect(() => {
    let alive = true
    api.listFiles().then((items) => {
      if (alive) setRows(items)
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
