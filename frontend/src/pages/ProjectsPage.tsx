import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { ProjectRow } from '../api/runtimeApi'

type ProjectStat = { analyzed: number; total: number }

export function ProjectsPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<ProjectRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [stats, setStats] = useState<Record<string, ProjectStat>>({})
  const tapRef = useRef<{ rowId: string; ts: number } | null>(null)

  async function refresh() {
    const [projects, selected] = await Promise.all([api.listProjects(), api.getSelectedProject()])
    setRows(projects)
    setSelectedId(selected.project_id ?? null)
    const pairs = await Promise.all(
      projects.map(async (p) => {
        const files = await api.listFiles(p.id)
        return [p.id, { analyzed: files.filter((f) => f.analyzed).length, total: files.length }] as const
      }),
    )
    setStats(Object.fromEntries(pairs))
  }

  useEffect(() => {
    refresh()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function onNewProject() {
    const created = await api.createProject(`New Project ${rows.length + 1}`)
    await api.setSelectedProject(created.id)
    await refresh()
  }

  async function openFiles(row: ProjectRow) {
    await api.setSelectedProject(row.id)
    setSelectedId(row.id)
    navigate('/files')
  }

  function onRowTap(row: ProjectRow) {
    const now = Date.now()
    const last = tapRef.current
    if (last && last.rowId === row.id && now - last.ts < 350) {
      openFiles(row)
      tapRef.current = null
      return
    }
    tapRef.current = { rowId: row.id, ts: now }
  }

  return (
    <section className="screen-block">
      <div className="page-head">
        <h2 className="page-title">Projects</h2>
        <button type="button" className="secondary-btn" onClick={onNewProject}>
          New Project
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Created</th>
            <th>Updated</th>
            <th>Analyzed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const stat = stats[row.id] ?? { analyzed: 0, total: 0 }
            return (
              <tr
                key={row.id}
                onClick={() => onRowTap(row)}
                aria-label={`project-row-${row.id}`}
                style={{ cursor: 'pointer', outline: selectedId === row.id ? '1px solid #f3d13b' : 'none' }}
              >
                <td>{row.name}</td>
                <td>{new Date(row.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                <td>{new Date(row.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                <td>{`${stat.analyzed}/${stat.total}`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

