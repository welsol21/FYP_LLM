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
  const [deletingByProjectId, setDeletingByProjectId] = useState<Record<string, boolean>>({})
  const [creatingProject, setCreatingProject] = useState(false)
  const creatingProjectRef = useRef(false)
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
    if (creatingProjectRef.current) return
    creatingProjectRef.current = true
    setCreatingProject(true)
    try {
      const entered = window.prompt('Enter project name:')
      const name = String(entered || '').trim()
      if (!name) return
      try {
        const created = await api.createProject(name)
        await api.setSelectedProject(created.id)
        await refresh()
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        window.alert(message || 'Unable to create project.')
      }
    } finally {
      creatingProjectRef.current = false
      setCreatingProject(false)
    }
  }

  async function openFiles(row: ProjectRow) {
    await api.setSelectedProject(row.id)
    setSelectedId(row.id)
    navigate('/files')
  }

  async function onDeleteProject(row: ProjectRow) {
    const id = String(row.id || '').trim()
    if (!id) return
    if (typeof api.deleteProject !== 'function') return
    const shouldDelete = window.confirm(`Delete project "${row.name}" and all related files/analyses/artifacts?`)
    if (!shouldDelete) return
    setDeletingByProjectId((prev) => ({ ...prev, [id]: true }))
    try {
      await api.deleteProject(id)
      await refresh()
    } finally {
      setDeletingByProjectId((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    }
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
        <button type="button" className="secondary-btn" onClick={onNewProject} disabled={creatingProject}>
          {creatingProject ? 'Creating...' : 'New Project'}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Created</th>
            <th>Updated</th>
            <th>Analyzed</th>
            <th>Actions</th>
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
                <td>
                  {typeof api.deleteProject === 'function' ? (
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={(e) => {
                        e.stopPropagation()
                        void onDeleteProject(row)
                      }}
                      disabled={Boolean(deletingByProjectId[row.id])}
                      aria-label={`delete-project-${row.id}`}
                    >
                      {deletingByProjectId[row.id] ? 'Deleting...' : 'Delete'}
                    </button>
                  ) : null}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
