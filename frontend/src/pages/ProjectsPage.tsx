import { FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { ProjectRow } from '../api/runtimeApi'

export function ProjectsPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<ProjectRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  async function refresh() {
    const [projects, selected] = await Promise.all([api.listProjects(), api.getSelectedProject()])
    setRows(projects)
    setSelectedId(selected.project_id ?? null)
  }

  useEffect(() => {
    refresh()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Project name is required.')
      return
    }
    const created = await api.createProject(trimmed)
    await api.setSelectedProject(created.id)
    setName('')
    setError('')
    await refresh()
  }

  async function onSelect(row: ProjectRow) {
    await api.setSelectedProject(row.id)
    setSelectedId(row.id)
    navigate('/files')
  }

  return (
    <section className="card">
      <h1>Projects</h1>
      <form onSubmit={onCreate} aria-label="project-create-form">
        <label>
          New Project
          <input
            aria-label="new-project-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name"
          />
        </label>
        <button type="submit">Create</button>
        {error ? <p style={{ color: '#ff6b6b' }}>{error}</p> : null}
      </form>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Created</th>
            <th>Updated</th>
            <th>Selected</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              onDoubleClick={() => onSelect(row)}
              aria-label={`project-row-${row.id}`}
              style={{ cursor: 'pointer' }}
            >
              <td>{row.name}</td>
              <td>{row.created_at}</td>
              <td>{row.updated_at}</td>
              <td>{selectedId === row.id ? 'yes' : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Double-click project row to open Files.</p>
    </section>
  )
}
