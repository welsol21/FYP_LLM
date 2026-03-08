import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type {
  BackendJobStatus,
  DocumentArtifact,
  MediaFileRow,
  MediaSubmissionPayload,
  ProjectRow,
  SelectedProject,
  TranslationConfig,
} from '../api/runtimeApi'
import { MediaSubmitForm } from '../components/MediaSubmitForm'

type AnalyzeRouteState = {
  analyzeEntry?: 'direct' | 'files'
  selectedMedia?: {
    mediaFileId?: string
    documentId?: string
    mediaPath?: string
    durationSec?: number
    sizeBytes?: number
    fileName?: string
  }
}

type AnalysisHistoryItem = {
  analysis_id: string
  file_id: string
  file_name: string
  document_id: string
  analyzed_at: string
  artifacts: DocumentArtifact[]
}

type AnalysisHistoryGroup = {
  time_key: string
  items: AnalysisHistoryItem[]
}

function parseTimestamp(value: string): number {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatHistoryTime(value: string): string {
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) return value || 'Unknown time'
  return new Date(parsed).toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function AnalyzePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [artifacts, setArtifacts] = useState<DocumentArtifact[]>([])
  const [historyGroups, setHistoryGroups] = useState<AnalysisHistoryGroup[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [historyReloadKey, setHistoryReloadKey] = useState(0)
  const [deletingByDocumentId, setDeletingByDocumentId] = useState<Record<string, boolean>>({})
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<BackendJobStatus | null>(null)
  const [liveProgress, setLiveProgress] = useState<number[]>([0, 0, 0, 0, 0])
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null)
  const [nowTs, setNowTs] = useState<number>(Date.now())
  const routeState = (location.state as AnalyzeRouteState | null | undefined) || null
  const selectedMediaFromRoute = routeState?.selectedMedia
  const analyzeEntry = routeState?.analyzeEntry || (selectedMediaFromRoute ? 'files' : 'direct')
  const showDirectSelector = analyzeEntry === 'direct'
  const [activeMedia, setActiveMedia] = useState<typeof selectedMediaFromRoute | null>(selectedMediaFromRoute ?? null)
  const [projects, setProjects] = useState<ProjectRow[]>([])
  const [directProjectId, setDirectProjectId] = useState<string>('')
  const [directFiles, setDirectFiles] = useState<MediaFileRow[]>([])
  const [directFileId, setDirectFileId] = useState<string>('')
  const pollFailuresRef = useRef<number>(0)
  const currentMediaFileId = String(activeMedia?.mediaFileId || '').trim()
  const currentMediaFileName = String(activeMedia?.fileName || '').trim().toLowerCase()
  const currentMediaPath = String(activeMedia?.mediaPath || '').trim()

  useEffect(() => {
    let stopped = false
    Promise.all([api.getSelectedProject(), api.getTranslationConfig(), api.listProjects()]).then(([selected, cfg, allProjects]) => {
      if (stopped) return
      const fallbackProject = allProjects[0]
      setSelectedProject(
        selected.project_id
          ? selected
          : {
              project_id: fallbackProject?.id || null,
              project_name: fallbackProject?.name,
            },
      )
      setTranslationConfig(cfg)
      setProjects(allProjects)
      // For direct Analyze entry, keep selector empty until user chooses project/file explicitly.
      setDirectProjectId((prev) => (analyzeEntry === 'direct' ? prev : (prev || selected.project_id || allProjects[0]?.id || '')))
    })
    return () => {
      stopped = true
    }
  }, [api, analyzeEntry])

  useEffect(() => {
    setActiveMedia(selectedMediaFromRoute ?? null)
  }, [selectedMediaFromRoute])

  useEffect(() => {
    if (!currentMediaFileId && !currentMediaFileName && !currentMediaPath) {
      setHistoryGroups([])
      setHistoryLoading(false)
      setHistoryError('')
      return
    }
    let stopped = false
    const loadHistory = async () => {
      setHistoryLoading(true)
      setHistoryError('')
      try {
        const historyRows = await api.listAnalysisHistory(selectedProject.project_id || undefined)
        const fileRows = historyRows.filter((row) => {
          const rowFileId = String(row.media_file_id || '').trim()
          const rowFileName = String(row.file_name || '').trim().toLowerCase()
          const rowFilePath = String(row.file_path || '').trim()
          const matchId = currentMediaFileId ? rowFileId === currentMediaFileId : true
          const matchName = currentMediaFileName ? rowFileName === currentMediaFileName : true
          const matchPath = currentMediaPath ? rowFilePath === currentMediaPath : true
          return matchId && matchName && matchPath
        })
        const resolved = await Promise.all(
          fileRows.map(async (row) => {
            const documentId = String(row.document_id || '')
            let docArtifacts: DocumentArtifact[] = []
            if (documentId) {
              try {
                docArtifacts = await api.listDocumentArtifacts(documentId)
              } catch {
                docArtifacts = []
              }
            }
            return {
              analysis_id: String(row.analysis_id || row.document_id),
              file_id: String(row.media_file_id || row.analysis_id || row.document_id),
              file_name: String(row.file_name || row.media_file_id || row.document_id || 'Unknown'),
              analyzed_at: String(row.updated_at || row.created_at || ''),
              documentId,
              artifacts: docArtifacts,
            }
          }),
        )
        resolved.sort((a, b) => parseTimestamp(b.analyzed_at) - parseTimestamp(a.analyzed_at))
        const grouped = new Map<string, AnalysisHistoryItem[]>()
        for (const item of resolved) {
          const timeKey = formatHistoryTime(item.analyzed_at)
          const bucket = grouped.get(timeKey) || []
          bucket.push({
            analysis_id: item.analysis_id,
            file_id: item.file_id,
            file_name: item.file_name,
            document_id: item.documentId,
            analyzed_at: item.analyzed_at,
            artifacts: item.artifacts,
          })
          grouped.set(timeKey, bucket)
        }
        if (!stopped) {
          setHistoryGroups(Array.from(grouped.entries()).map(([timeKey, items]) => ({ time_key: timeKey, items })))
        }
      } catch (err) {
        if (!stopped) {
          setHistoryGroups([])
          setHistoryError(err instanceof Error ? err.message : String(err))
        }
      } finally {
        if (!stopped) setHistoryLoading(false)
      }
    }
    loadHistory()
    return () => {
      stopped = true
    }
  }, [
    api,
    selectedProject.project_id,
    jobStatus?.status,
    historyReloadKey,
    currentMediaFileId,
    currentMediaFileName,
    currentMediaPath,
  ])

  useEffect(() => {
    if (showDirectSelector) {
      setDirectProjectId('')
      setDirectFileId('')
      setDirectFiles([])
    }
  }, [showDirectSelector])

  useEffect(() => {
    if (!directProjectId) {
      setDirectFiles([])
      setDirectFileId('')
      return
    }
    let stopped = false
    api.listFiles(directProjectId).then((rows) => {
      if (stopped) return
      setDirectFiles(rows)
      setDirectFileId((prev) => (prev && rows.some((row) => row.id === prev) ? prev : ''))
    })
    return () => {
      stopped = true
    }
  }, [api, directProjectId])

  useEffect(() => {
    if (!jobId) return
    const ticker = window.setInterval(() => setNowTs(Date.now()), 1000)
    return () => window.clearInterval(ticker)
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    let stopped = false
    const poll = async () => {
      try {
        const status = await api.getBackendJobStatus(jobId)
        if (stopped) return
        pollFailuresRef.current = 0
        setJobStatus(status)
        if (status.document_id) {
          setActiveMedia((prev) => (prev ? { ...prev, documentId: status.document_id } : prev))
        }
        if (Array.isArray(status.stage_progress) && status.stage_progress.length === 5) {
          setLiveProgress(status.stage_progress)
        }
        if (status.status === 'completed_local' || status.status === 'rejected' || status.status === 'error' || status.status === 'not_found') {
          setJobId(null)
        }
      } catch {
        if (stopped) return
        pollFailuresRef.current += 1
        if (pollFailuresRef.current >= 3) {
          setJobStatus((prev) => ({
            job_id: prev?.job_id || jobId,
            status: prev?.status || 'running_local',
            message: 'Temporary connection issue while polling status. Retrying...',
            stage_name: prev?.stage_name || 'running_local',
            stage_log: prev?.stage_log || 'Polling retry in progress...',
            stage_logs: prev?.stage_logs || ['Polling retry in progress...'],
            stage_progress: prev?.stage_progress || liveProgress,
            document_id: prev?.document_id,
          }))
        }
      }
    }
    poll()
    const timer = window.setInterval(poll, 800)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [api, jobId])

  const activeDocumentId = jobStatus?.document_id || submission?.result.document_id || activeMedia?.documentId
  const stageLogLines = (jobStatus?.stage_logs || []).slice(-10)

  async function deleteAnalysis(documentId: string) {
    const docId = String(documentId || '').trim()
    if (!docId) return
    const shouldDelete = window.confirm('Delete this analysis and all its artifacts?')
    if (!shouldDelete) return
    setDeletingByDocumentId((prev) => ({ ...prev, [docId]: true }))
    try {
      const result = await api.deleteAnalysis(docId)
      if (result.status !== 'ok') return
      if (activeDocumentId === docId) {
        setArtifacts([])
        setSubmission((prev) => {
          if (!prev || prev.result.document_id !== docId) return prev
          return { ...prev, result: { ...prev.result, document_id: undefined } }
        })
        setJobStatus((prev) => {
          if (!prev || prev.document_id !== docId) return prev
          return { ...prev, document_id: undefined }
        })
        setActiveMedia((prev) => {
          if (!prev || prev.documentId !== docId) return prev
          return { ...prev, documentId: undefined }
        })
      }
      if (directProjectId) {
        const files = await api.listFiles(directProjectId)
        setDirectFiles(files)
        setDirectFileId((prev) => (prev && files.some((row) => row.id === prev) ? prev : ''))
      }
      setHistoryReloadKey((prev) => prev + 1)
    } finally {
      setDeletingByDocumentId((prev) => {
        const next = { ...prev }
        delete next[docId]
        return next
      })
    }
  }

  useEffect(() => {
    if (!activeDocumentId) {
      setArtifacts([])
      return
    }
    let stopped = false
    const fetchArtifacts = async () => {
      try {
        const rows = await api.listDocumentArtifacts(activeDocumentId)
        if (!stopped) setArtifacts(rows)
      } catch {
        if (!stopped) setArtifacts([])
      }
    }
    fetchArtifacts()
    if (jobId) {
      const timer = window.setInterval(fetchArtifacts, 1200)
      return () => {
        stopped = true
        window.clearInterval(timer)
      }
    }
    return () => {
      stopped = true
    }
  }, [api, activeDocumentId, jobId, jobStatus?.status])

  const stageProgress = useMemo(() => {
    if (jobId) return liveProgress
    if (!submission) return [0, 0, 0, 0, 0]
    if (submission.result.route === 'reject') return [100, 0, 0, 0, 0]
    if (submission.result.route === 'local') return [100, 100, 100, 100, 100]
    return [0, 0, 0, 0, 0]
  }, [submission, jobId, liveProgress])

  const activeStageIndex = useMemo(() => {
    if (!jobId) return null
    for (let i = stageProgress.length - 1; i >= 0; i -= 1) {
      const value = Number(stageProgress[i] ?? 0)
      if (value > 0 && value < 100) return i
    }
    return null
  }, [jobId, stageProgress])
  const elapsedSec = useMemo(() => {
    if (!analysisStartedAt) return 0
    return Math.max(0, Math.floor((nowTs - analysisStartedAt) / 1000))
  }, [analysisStartedAt, nowTs])
  const estimatedSec = useMemo(() => {
    const progressValues = stageProgress.map((value) => {
      const n = Number(value)
      if (!Number.isFinite(n)) return 0
      return Math.max(0, Math.min(100, n))
    })
    const progressFraction = progressValues.reduce((acc, value) => acc + value, 0) / (progressValues.length * 100)
    if (elapsedSec > 0 && progressFraction >= 0.03) {
      return Math.max(elapsedSec + 1, Math.round(elapsedSec / Math.max(progressFraction, 0.03)))
    }
    const src = Number(activeMedia?.durationSec ?? 0)
    if (src > 0) return Math.max(20, Math.round(src * 1.8))
    return 60
  }, [elapsedSec, stageProgress, activeMedia?.durationSec])
  const stageTitle = useMemo(() => {
    const value = String(jobStatus?.stage_name || '').trim().toLowerCase()
    if (!value) return ''
    if (value === 'translating_text') return 'linguistic parsing'
    return value.replace(/_/g, ' ')
  }, [jobStatus?.stage_name])

  return (
    <section className="screen-block analyze-stack">
      {showDirectSelector ? (
        <section className="card compact-card" aria-label="analyze-direct-select">
          <p className="stage-log-title">Select project and file</p>
          <div className="analyze-grid">
            <label className="analyze-label" htmlFor="analyze-project-select">Project</label>
            <select
              id="analyze-project-select"
              value={directProjectId}
              onChange={async (e) => {
                const projectId = e.target.value
                setDirectProjectId(projectId)
                setDirectFileId('')
                const selected = await api.setSelectedProject(projectId)
                setSelectedProject(selected)
              }}
            >
              <option value="">Select project...</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
            <label className="analyze-label" htmlFor="analyze-file-select">File</label>
            <select
              id="analyze-file-select"
              value={directFileId}
              onChange={(e) => setDirectFileId(e.target.value)}
              disabled={!directProjectId}
            >
              <option value="">Select file...</option>
              {directFiles.map((file) => (
                <option key={file.id} value={file.id}>{file.name}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => {
              const row = directFiles.find((file) => file.id === directFileId)
              if (!row) return
              setActiveMedia({
                mediaFileId: row.id,
                documentId: row.document_id,
                fileName: row.name,
                mediaPath: row.path ?? `/uploads/${row.name}`,
                sizeBytes: row.size_bytes ?? 100 * 1024 * 1024,
                durationSec: row.duration_seconds ?? 600,
              })
            }}
            disabled={!directFileId}
          >
            Use selected file
          </button>
        </section>
      ) : null}
      <MediaSubmitForm
        onSubmitted={(payload) => {
          setSubmission(payload)
          setJobStatus(null)
          setAnalysisStartedAt(Date.now())
          setNowTs(Date.now())
          if (payload.result.route === 'local' && payload.result.status === 'accepted_local' && payload.result.job_id) {
            setJobId(payload.result.job_id)
            setLiveProgress([2, 0, 0, 0, 0])
          } else {
            setJobId(null)
            setLiveProgress(payload.result.route === 'local' ? [100, 100, 100, 100, 100] : [100, 0, 0, 0, 0])
          }
        }}
        onSubmittingChange={() => {}}
        projectId={selectedProject.project_id ?? null}
        projectLabel={activeMedia ? (selectedProject.project_name ?? selectedProject.project_id ?? 'Project') : '-'}
        stageProgress={stageProgress}
        activeStageIndex={activeStageIndex}
        initialMedia={activeMedia ?? undefined}
        translatorOptions={translationConfig?.providers || []}
        defaultTranslator={translationConfig?.default_provider || 'm2m100'}
      />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <p>{jobStatus?.message || submission.ui_feedback.message}</p>
          <p className="stage-log-title">Elapsed: {elapsedSec}s / Estimated: {estimatedSec}s</p>
          {stageTitle ? (
            <p className="stage-log-title">Stage: {stageTitle}</p>
          ) : null}
          {stageLogLines.length > 0 ? (
            <pre className="stage-log-box">{stageLogLines.join('\n')}</pre>
          ) : null}
        </section>
      ) : null}
      {activeDocumentId ? (
        <section className="card compact-card" aria-label="analyze-open-visualizer">
          <button type="button" onClick={() => navigate('/visualizer', { state: { documentId: activeDocumentId } })}>
            Open Visualizer
          </button>
          <button
            type="button"
            className="secondary-btn"
            onClick={() => {
              void deleteAnalysis(activeDocumentId)
            }}
            disabled={Boolean(deletingByDocumentId[activeDocumentId])}
            aria-label="delete-active-analysis"
          >
            {deletingByDocumentId[activeDocumentId] ? 'Deleting...' : 'Delete analysis artifacts'}
          </button>
          <p className="stage-log-title">Available artifacts</p>
          <div className="artifact-actions">
            {artifacts.length > 0 ? (
              artifacts.map((artifact) => (
                <a key={artifact.name} className="top-link" href={artifact.download_url} target="_blank" rel="noreferrer">
                  Download {artifact.name}
                </a>
              ))
            ) : (
              <span className="muted">Artifacts are not ready yet.</span>
            )}
          </div>
        </section>
      ) : null}
      <section className="card compact-card" aria-label="analyze-history">
        <p className="stage-log-title">Analysis history</p>
        {historyLoading ? (
          <p className="muted">Loading history...</p>
        ) : historyError ? (
          <p className="muted">Failed to load history: {historyError}</p>
        ) : historyGroups.length > 0 ? (
          <div className="analysis-history">
            {historyGroups.map((group) => (
              <section key={group.time_key} className="analysis-history-group">
                <p className="analysis-history-time">{group.time_key}</p>
                {group.items.map((item) => {
                  const isDeleting = Boolean(deletingByDocumentId[item.document_id])
                  return (
                  <article key={`${item.analysis_id}-${item.document_id}`} className="analysis-history-item">
                    <div className="analysis-history-head">
                      <strong>{item.file_name}</strong>
                      <div className="actions-row">
                        {item.document_id ? (
                          <button
                            type="button"
                            onClick={() => navigate('/visualizer', { state: { documentId: item.document_id } })}
                            aria-label={`history-open-${item.file_name}`}
                          >
                            Open Visualizer
                          </button>
                        ) : null}
                        {item.document_id ? (
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => {
                              void deleteAnalysis(item.document_id)
                            }}
                            aria-label={`history-delete-${item.document_id}`}
                            disabled={isDeleting}
                          >
                            {isDeleting ? 'Deleting...' : 'Delete'}
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <div className="artifact-actions">
                      {item.artifacts.length > 0 ? (
                        item.artifacts.map((artifact) => (
                          <a key={`${item.file_id}-${artifact.name}`} className="top-link" href={artifact.download_url} target="_blank" rel="noreferrer">
                            Download {artifact.name}
                          </a>
                        ))
                      ) : (
                        <span className="muted">Artifacts are not ready yet.</span>
                      )}
                    </div>
                  </article>
                )})}
              </section>
            ))}
          </div>
        ) : (
          <p className="muted">No analyzed files yet.</p>
        )}
      </section>
    </section>
  )
}
