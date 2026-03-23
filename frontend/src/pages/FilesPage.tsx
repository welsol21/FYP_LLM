import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import { buildAnalysisFeatureBadges } from '../lib/analysisSettings'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'
import type { AnalysisHistoryRow, MediaFileRow, SelectedProject } from '../api/runtimeApi'

type FileAnalysisVersion = {
  analysis_id: string
  document_id: string
  updated_at: string
  settings: string
  file_name: string
}

export function FilesPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<MediaFileRow[]>([])
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisHistoryRow[]>([])
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [expandedVersionsByFileId, setExpandedVersionsByFileId] = useState<Record<string, boolean>>({})
  const [deletingByFileId, setDeletingByFileId] = useState<Record<string, boolean>>({})
  const inputRef = useRef<HTMLInputElement | null>(null)
  const tapRef = useRef<{ rowId: string; ts: number } | null>(null)

  async function refreshProjectData(projectId: string | null | undefined) {
    recordRuntimeDiagnostic('ui.files', 'refresh.start', { projectId })
    if (!projectId) {
      setRows([])
      setAnalysisHistory([])
      recordRuntimeDiagnostic('ui.files', 'refresh.empty')
      return
    }
    const [items, history] = await Promise.all([
      api.listFiles(projectId),
      api.listAnalysisHistory(projectId),
    ])
    setRows(items)
    setAnalysisHistory(history)
    recordRuntimeDiagnostic('ui.files', 'refresh.success', {
      projectId,
      files: items.length,
      analyses: history.length,
    })
  }

  useEffect(() => {
    let alive = true
    api.getSelectedProject().then((selected) => {
      if (!alive) return
      setSelectedProject(selected)
      if (!selected.project_id) {
        setRows([])
        setAnalysisHistory([])
        return
      }
      refreshProjectData(selected.project_id).then(() => {
        if (!alive) return
      })
    })
    return () => {
      alive = false
    }
  }, [api])

  const versionsByFileId = useMemo(() => {
    const out: Record<string, FileAnalysisVersion[]> = {}
    for (const fileRow of rows) {
      const fileId = String(fileRow.id || '').trim()
      const fileName = String(fileRow.name || '').trim().toLowerCase()
      const filePath = String(fileRow.path || '').trim()
      const versions = analysisHistory
        .filter((row) => {
          const rowFileId = String(row.media_file_id || '').trim()
          const rowFileName = String(row.file_name || '').trim().toLowerCase()
          const rowFilePath = String(row.file_path || '').trim()
          if (rowFileId && fileId && rowFileId === fileId) return true
          if (rowFilePath && filePath && rowFilePath === filePath) return true
          return rowFileName && fileName && rowFileName === fileName
        })
        .map((row) => ({
          analysis_id: String(row.analysis_id || ''),
          document_id: String(row.document_id || ''),
          updated_at: String(row.updated_at || row.created_at || ''),
          settings: String(row.settings || ''),
          file_name: String(row.file_name || fileRow.name || ''),
        }))
        .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      out[fileId] = versions
    }
    return out
  }, [rows, analysisHistory])

  function openAnalyze(row: MediaFileRow) {
    recordRuntimeDiagnostic('ui.files', 'open_analyze', { fileId: row.id, name: row.name, documentId: row.document_id || '' })
    navigate('/analyze', {
      state: {
        analyzeEntry: 'files',
        selectedMedia: {
          mediaFileId: row.id,
          documentId: row.document_id,
          fileName: row.name,
          mediaPath: row.path ?? `/uploads/${row.name}`,
          sizeBytes: row.size_bytes ?? 100 * 1024 * 1024,
          durationSec: row.duration_seconds ?? 600,
        },
      },
    })
  }

  function onRowTap(row: MediaFileRow) {
    recordRuntimeDiagnostic('ui.files', 'row.tap', { fileId: row.id, name: row.name })
    const now = Date.now()
    const lastTap = tapRef.current
    if (lastTap && lastTap.rowId === row.id && now - lastTap.ts < 350) {
      openAnalyze(row)
      tapRef.current = null
      return
    }
    tapRef.current = { rowId: row.id, ts: now }
  }

  async function deleteFile(fileId: string) {
    const id = String(fileId || '').trim()
    if (!id) return
    const shouldDelete = window.confirm('Delete this file and all related analyses/artifacts?')
    recordRuntimeDiagnostic('ui.files', 'delete.confirm', { fileId: id, confirmed: shouldDelete })
    if (!shouldDelete) return
    setDeletingByFileId((prev) => ({ ...prev, [id]: true }))
    try {
      const result = await api.deleteFile(id)
      if (result.status !== 'ok') return
      setExpandedVersionsByFileId((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
      await refreshProjectData(selectedProject.project_id)
    } finally {
      setDeletingByFileId((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    }
  }

  return (
    <section className="screen-block files-page">
      <div className="page-head">
        <h2 className="page-title">{selectedProject.project_name ?? selectedProject.project_id ?? 'Project'}</h2>
        <button
          type="button"
          className="secondary-btn"
          onClick={() => {
            recordRuntimeDiagnostic('ui.files', 'new_file.click', { projectId: selectedProject.project_id || '' })
            inputRef.current?.click()
          }}
        >
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
          recordRuntimeDiagnostic('ui.files', 'file_input.change', {
            count: e.target.files?.length || 0,
            projectId: selectedProject.project_id || '',
          })
          const inputEl = e.currentTarget
          const file = e.target.files?.[0]
          if (!file || !selectedProject.project_id) return
          recordRuntimeDiagnostic('ui.files', 'file_input.selected', {
            name: file.name,
            size: file.size,
            type: file.type,
            projectId: selectedProject.project_id,
          })
          setUploading(true)
          setUploadError('')
          try {
            recordRuntimeDiagnostic('ui.files', 'upload.start', { name: file.name, size: file.size })
            const uploaded = await api.uploadMedia(file)
            recordRuntimeDiagnostic('ui.files', 'upload.success', uploaded)
            recordRuntimeDiagnostic('ui.files', 'register.start', {
              projectId: selectedProject.project_id,
              fileName: uploaded.fileName,
              mediaPath: uploaded.mediaPath,
            })
            await api.registerMediaFile({
              projectId: selectedProject.project_id,
              name: uploaded.fileName,
              mediaPath: uploaded.mediaPath,
              sizeBytes: uploaded.sizeBytes,
              durationSec: 1,
            })
            recordRuntimeDiagnostic('ui.files', 'register.success', { fileName: uploaded.fileName })
            await refreshProjectData(selectedProject.project_id)
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err)
            recordRuntimeDiagnostic('ui.files', 'upload_or_register.error', msg, 'error')
            setUploadError(msg)
          } finally {
            setUploading(false)
            inputEl.value = ''
            recordRuntimeDiagnostic('ui.files', 'file_input.reset')
          }
        }}
      />
      {uploading ? <p>Uploading...</p> : null}
      {uploadError ? <p style={{ color: '#ff6b6b' }}>{uploadError}</p> : null}

      <div className="desktop-table">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Updated</th>
              <th>Analyzed</th>
              <th>Versions</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const versions = versionsByFileId[row.id] || []
              const expanded = Boolean(expandedVersionsByFileId[row.id])
              return (
                <Fragment key={row.id}>
                  <tr onClick={() => onRowTap(row)} aria-label={`file-row-${row.id}`} style={{ cursor: 'pointer' }}>
                    <td>{row.name}</td>
                    <td>{new Date(row.updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                    <td>{row.analyzed ? 'Yes' : 'No'}</td>
                    <td>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setExpandedVersionsByFileId((prev) => ({ ...prev, [row.id]: !expanded }))
                        }}
                        aria-label={`toggle-versions-${row.id}`}
                      >
                        {expanded ? `Hide versions (${versions.length})` : `Show versions (${versions.length})`}
                      </button>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          void deleteFile(row.id)
                        }}
                        disabled={Boolean(deletingByFileId[row.id])}
                        aria-label={`delete-file-${row.id}`}
                      >
                        {deletingByFileId[row.id] ? 'Deleting...' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                  {expanded ? (
                    <tr className="file-versions-row">
                      <td colSpan={5}>
                        {versions.length > 0 ? (
                          <div className="file-versions-list">
                            {versions.map((version) => (
                              <section key={`${row.id}-${version.analysis_id}`} className="file-version-item">
                                <div className="file-version-head">
                                  <strong>
                                    {new Date(version.updated_at).toLocaleString('en-US', {
                                      month: 'short',
                                      day: 'numeric',
                                      year: 'numeric',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    })}
                                  </strong>
                                  {version.document_id ? (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        navigate('/visualizer', {
                                          state: {
                                            documentId: version.document_id,
                                            documentMeta: {
                                              [version.document_id]: {
                                                project: selectedProject.project_name ?? selectedProject.project_id ?? '-',
                                                file: version.file_name || row.name,
                                              },
                                            },
                                          },
                                        })
                                      }
                                    >
                                      Open Visualizer
                                    </button>
                                  ) : null}
                                </div>
                                <div className="analysis-feature-badges">
                                  {buildAnalysisFeatureBadges(version.settings).map((badge) => (
                                    <span key={`${version.analysis_id}-${badge.key}`} className="badge analysis-feature-badge">
                                      {badge.label}: {badge.value}
                                    </span>
                                  ))}
                                </div>
                              </section>
                            ))}
                          </div>
                        ) : (
                          <span className="muted">No analysis versions yet.</span>
                        )}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mobile-records">
        {rows.map((row) => {
          const versions = versionsByFileId[row.id] || []
          const expanded = Boolean(expandedVersionsByFileId[row.id])
          return (
            <article
              key={`mobile-${row.id}`}
              className="mobile-record-card"
              onClick={() => onRowTap(row)}
              aria-label={`mobile-file-row-${row.id}`}
            >
              <div className="mobile-record-head">
                <h3 className="mobile-record-title">{row.name}</h3>
              </div>
              <div className="mobile-record-meta">
                <div className="mobile-record-field">
                  <span className="mobile-record-label">Updated</span>
                  <span>{new Date(row.updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                </div>
                <div className="mobile-record-field">
                  <span className="mobile-record-label">Analyzed</span>
                  <span>{row.analyzed ? 'Yes' : 'No'}</span>
                </div>
                <div className="mobile-record-field">
                  <span className="mobile-record-label">Versions</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setExpandedVersionsByFileId((prev) => ({ ...prev, [row.id]: !expanded }))
                    }}
                    aria-label={`mobile-toggle-versions-${row.id}`}
                  >
                    {expanded ? `Hide versions (${versions.length})` : `Show versions (${versions.length})`}
                  </button>
                </div>
              </div>
              <div className="mobile-record-actions">
                <button
                  type="button"
                  className="secondary-btn mobile-record-action-btn"
                  onClick={(e) => {
                    e.stopPropagation()
                    void deleteFile(row.id)
                  }}
                  disabled={Boolean(deletingByFileId[row.id])}
                  aria-label={`mobile-delete-file-${row.id}`}
                >
                  {deletingByFileId[row.id] ? 'Deleting...' : 'Delete'}
                </button>
              </div>
              {expanded ? (
                <div className="mobile-record-extra">
                  {versions.length > 0 ? (
                    <div className="file-versions-list">
                      {versions.map((version) => (
                        <section key={`mobile-${row.id}-${version.analysis_id}`} className="file-version-item">
                          <div className="file-version-head">
                            <strong>
                              {new Date(version.updated_at).toLocaleString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </strong>
                            {version.document_id ? (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigate('/visualizer', {
                                    state: {
                                      documentId: version.document_id,
                                      documentMeta: {
                                        [version.document_id]: {
                                          project: selectedProject.project_name ?? selectedProject.project_id ?? '-',
                                          file: version.file_name || row.name,
                                        },
                                      },
                                    },
                                  })
                                }}
                              >
                                Open Visualizer
                              </button>
                            ) : null}
                          </div>
                          <div className="analysis-feature-badges">
                            {buildAnalysisFeatureBadges(version.settings).map((badge) => (
                              <span key={`mobile-${version.analysis_id}-${badge.key}`} className="badge analysis-feature-badge">
                                {badge.label}: {badge.value}
                              </span>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  ) : (
                    <span className="muted">No analysis versions yet.</span>
                  )}
                </div>
              ) : null}
            </article>
          )
        })}
      </div>
    </section>
  )
}
