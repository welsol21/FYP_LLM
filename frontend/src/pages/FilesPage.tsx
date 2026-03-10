import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import { buildAnalysisFeatureBadges } from '../lib/analysisSettings'
import type { AnalysisHistoryRow, MediaFileRow, SelectedProject } from '../api/runtimeApi'

type FileAnalysisVersion = {
  analysis_id: string
  document_id: string
  updated_at: string
  settings: string
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
  const inputRef = useRef<HTMLInputElement | null>(null)
  const tapRef = useRef<{ rowId: string; ts: number } | null>(null)

  async function refreshProjectData(projectId: string | null | undefined) {
    if (!projectId) {
      setRows([])
      setAnalysisHistory([])
      return
    }
    const [items, history] = await Promise.all([
      api.listFiles(projectId),
      api.listAnalysisHistory(projectId),
    ])
    setRows(items)
    setAnalysisHistory(history)
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
        }))
        .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      out[fileId] = versions
    }
    return out
  }, [rows, analysisHistory])

  function openAnalyze(row: MediaFileRow) {
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
            await refreshProjectData(selectedProject.project_id)
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
            <th>Updated</th>
            <th>Analyzed</th>
            <th>Versions</th>
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
                </tr>
                {expanded ? (
                  <tr className="file-versions-row">
                    <td colSpan={4}>
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
                                    onClick={() => navigate('/visualizer', { state: { documentId: version.document_id } })}
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
    </section>
  )
}
