import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'

type VocabRow = {
  id: string
  project: string
  file: string
  items: number
  created: string
}

function pseudoCount(seed: string): number {
  let acc = 0
  for (let i = 0; i < seed.length; i += 1) acc = (acc * 31 + seed.charCodeAt(i)) >>> 0
  return 30 + (acc % 40)
}

export function VocabularyPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<VocabRow[]>([])
  const [checked, setChecked] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let alive = true
    ;(async () => {
      const projects = await api.listProjects()
      const grouped = await Promise.all(
        projects.map(async (p) => {
          const files = await api.listFiles(p.id)
          return files
            .filter((f) => f.analyzed)
            .map((f) => ({
            id: `${p.id}:${f.id}`,
            project: p.name,
            file: f.name,
            items: pseudoCount(f.id),
            created: new Date(f.updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
            }))
        }),
      )
      if (alive) setRows(grouped.flat())
    })()
    return () => {
      alive = false
    }
  }, [api])

  const selectedCount = useMemo(() => Object.values(checked).filter(Boolean).length, [checked])

  return (
    <section className="screen-block">
      <div className="page-head">
        <h2 className="page-title">Vocabulary</h2>
        <div className="actions-row">
          <button type="button" className="secondary-btn" onClick={() => navigate('/visualizer')}>
            Visualizer
          </button>
          <button type="button" className="secondary-btn" onClick={() => window.alert(`Export JSON (${selectedCount})`)}>
            Export JSON
          </button>
          <button type="button" className="secondary-btn" onClick={() => window.alert(`Export CSV (${selectedCount})`)}>
            Export CSV
          </button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th style={{ width: 36 }} />
            <th>Project</th>
            <th>File</th>
            <th>Items</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <input
                  type="checkbox"
                  checked={!!checked[row.id]}
                  onChange={(e) => setChecked((prev) => ({ ...prev, [row.id]: e.target.checked }))}
                />
              </td>
              <td>{row.project}</td>
              <td>{row.file}</td>
              <td>{row.items}</td>
              <td>{row.created}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
