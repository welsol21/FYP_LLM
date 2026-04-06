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
    const [projects, selected, allFiles, allAnalyses] = await Promise.all([
      api.listProjects(),
      api.getSelectedProject(),
      api.listFiles(),
      api.listAnalysisHistory(),
    ])
    setRows(projects)
    setSelectedId(selected.project_id ?? null)
    const statsMap: Record<string, ProjectStat> = {}
    const projectIds = new Set(projects.map((project) => project.id))
    const projectIdByName = new Map(
      projects.map((project) => [String(project.name || '').trim().toLowerCase(), project.id] as const),
    )
    const singletonProjectId = projects.length === 1 ? projects[0].id : ''
    const resolveProjectId = (rawProjectId: string, rawProjectName: string): string => {
      const byId = String(rawProjectId || '').trim()
      if (byId && projectIds.has(byId)) return byId
      const byName = projectIdByName.get(String(rawProjectName || '').trim().toLowerCase())
      if (byName) return byName
      return singletonProjectId
    }
    const fileProjectByKey = new Map<string, string>()
    for (const file of allFiles) {
      const projectId = resolveProjectId(
        String((file.project_id || (file as { projectId?: string }).projectId || '')).trim(),
        '',
      )
      if (!projectId) continue
      const fileId = String(file.id || '').trim()
      const filePath = String((file.path || (file as { file_path?: string }).file_path || '')).trim()
      const fileName = String(file.name || '').trim().toLowerCase()
      if (fileId) fileProjectByKey.set(`id:${fileId}`, projectId)
      if (filePath) fileProjectByKey.set(`path:${filePath}`, projectId)
      if (fileName) fileProjectByKey.set(`name:${fileName}`, projectId)
    }
    const analyzedByProject = new Map<string, Set<string>>()
    for (const row of allAnalyses) {
      let projectId = resolveProjectId(
        String((row.project_id || (row as { projectId?: string }).projectId || '')).trim(),
        String((row.project_name || (row as { projectName?: string }).projectName || '')).trim(),
      )
      if (!projectId) {
        const fileId = String(row.media_file_id || '').trim()
        const filePath = String(row.file_path || '').trim()
        const fileName = String(row.file_name || '').trim().toLowerCase()
        projectId = fileProjectByKey.get(`id:${fileId}`)
          || fileProjectByKey.get(`path:${filePath}`)
          || fileProjectByKey.get(`name:${fileName}`)
          || ''
      }
      if (!projectId) continue
      const key = String(row.media_file_id || row.file_path || row.file_name || row.document_id || row.analysis_id || '').trim()
      if (!key) continue
      if (!analyzedByProject.has(projectId)) analyzedByProject.set(projectId, new Set())
      analyzedByProject.get(projectId)?.add(key)
    }
    for (const p of projects) {
      const pFiles = allFiles.filter((f) => {
        const projectId = resolveProjectId(
          String((f.project_id || (f as { projectId?: string }).projectId || '')).trim(),
          '',
        )
        return projectId === p.id
      })
      const total = pFiles.length
      const analyzedFromFiles = pFiles.filter((f) => Boolean(f.analyzed)).length
      const analyzedFromHistory = analyzedByProject.get(p.id)?.size || 0
      const analyzed = Math.max(analyzedFromFiles, analyzedFromHistory)
      statsMap[p.id] = { analyzed, total: total > 0 ? total : analyzedFromHistory }
    }
    setStats(statsMap)
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
    <section className="screen-block projects-page">
      <div className="page-head">
        <h2 className="page-title">Projects</h2>
        <button type="button" className="secondary-btn" onClick={onNewProject} disabled={creatingProject}>
          {creatingProject ? 'Creating...' : 'New Project'}
        </button>
      </div>
      <div className="desktop-table">
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
      </div>

      <div className="mobile-records">
        {rows.map((row) => {
          const stat = stats[row.id] ?? { analyzed: 0, total: 0 }
          return (
            <article
              key={`mobile-${row.id}`}
              className={`mobile-record-card${selectedId === row.id ? ' is-selected' : ''}`}
              onClick={() => onRowTap(row)}
              aria-label={`mobile-project-row-${row.id}`}
            >
              <div className="mobile-record-head">
                <h3 className="mobile-record-title">{row.name}</h3>
              </div>
              <div className="mobile-record-meta">
                <div className="mobile-record-field">
                  <span className="mobile-record-label">Created</span>
                  <span>{new Date(row.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                </div>
                <div className="mobile-record-field">
                  <span className="mobile-record-label">Updated</span>
                  <span>{new Date(row.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                </div>
                <div className="mobile-record-field">
                  <span className="mobile-record-label">Analyzed</span>
                  <span>{`${stat.analyzed}/${stat.total}`}</span>
                </div>
                {typeof api.deleteProject === 'function' ? (
                  <div className="mobile-record-field mobile-record-field-delete">
                    <button
                      type="button"
                      className="secondary-btn mobile-project-delete-btn"
                      onClick={(e) => {
                        e.stopPropagation()
                        void onDeleteProject(row)
                      }}
                      disabled={Boolean(deletingByProjectId[row.id])}
                      aria-label={`mobile-delete-project-${row.id}`}
                    >
                      <span className="mobile-project-delete-btn-text">
                        {deletingByProjectId[row.id] ? 'Deleting...' : 'Delete'}
                      </span>
                    </button>
                  </div>
                ) : null}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
