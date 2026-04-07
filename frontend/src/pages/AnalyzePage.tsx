import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import { buildAnalysisFeatureBadges, buildExportFileName } from '../lib/analysisSettings'
import { recordRuntimeDiagnostic } from '../lib/runtimeDiagnostics'
import type {
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
  settings: string
  artifacts: DocumentArtifact[]
}

type AnalysisHistoryGroup = {
  time_key: string
  items: AnalysisHistoryItem[]
}

const FALLBACK_TRANSLATION_CONFIG: TranslationConfig = {
  default_provider: 'm2m100',
  providers: [
    { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
    { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: false, credential_fields: ['api_key'], credentials: { api_key: '' } },
    { id: 'deepl', label: 'DeepL', kind: 'builtin', enabled: false, credential_fields: ['auth_key'], credentials: { auth_key: '' } },
    {
      id: 'lara',
      label: 'Lara',
      kind: 'builtin',
      enabled: false,
      credential_fields: ['api_id', 'api_secret'],
      credentials: { api_id: '', api_secret: '' },
    },
    { id: 'original', label: 'Original only (no translation)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
  ],
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

async function sleepMs(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function withRetry<T>(fn: () => Promise<T>, attempts: number, baseDelayMs: number): Promise<T> {
  let lastErr: unknown = null
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await fn()
    } catch (err) {
      lastErr = err
      if (i < attempts - 1) {
        await sleepMs(baseDelayMs * (i + 1))
      }
    }
  }
  throw lastErr
}

export function AnalyzePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const api = useApi()
  const [selectedProject, setSelectedProject] = useState<SelectedProject>({ project_id: null })
  const [submission, setSubmission] = useState<MediaSubmissionPayload | null>(null)
  const [translationConfig, setTranslationConfig] = useState<TranslationConfig | null>(null)
  const [historyGroups, setHistoryGroups] = useState<AnalysisHistoryGroup[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [historyReloadKey, setHistoryReloadKey] = useState(0)
  const [deletingByDocumentId, setDeletingByDocumentId] = useState<Record<string, boolean>>({})
  const [isSubmittingPipeline, setIsSubmittingPipeline] = useState(false)
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
  const currentMediaFileId = String(activeMedia?.mediaFileId || '').trim()
  const currentMediaFileName = String(activeMedia?.fileName || '').trim().toLowerCase()
  const currentMediaPath = String(activeMedia?.mediaPath || '').trim()

  useEffect(() => {
    let stopped = false
    void Promise.allSettled([api.getSelectedProject(), api.listProjects()])
      .then((results) => {
        if (stopped) return
        const selectedResult = results[0]
        const projectsResult = results[1]
        const selected = selectedResult.status === 'fulfilled'
          ? selectedResult.value
          : { project_id: null, project_name: undefined }
        const allProjects = projectsResult.status === 'fulfilled' ? projectsResult.value : []
        const fallbackProject = allProjects[0]
        setSelectedProject(
          selected.project_id
            ? selected
            : {
                project_id: fallbackProject?.id || null,
                project_name: fallbackProject?.name,
              },
        )
        setProjects(allProjects)
        // For direct Analyze entry, keep selector empty until user chooses project/file explicitly.
        setDirectProjectId((prev) => (analyzeEntry === 'direct' ? prev : (prev || selected.project_id || allProjects[0]?.id || '')))
      })
    const loadTranslationConfig = async (): Promise<void> => {
      try {
        const cfg = await withRetry(() => api.getTranslationConfig(), 4, 250)
        if (stopped) return
        setTranslationConfig(cfg || FALLBACK_TRANSLATION_CONFIG)
        recordRuntimeDiagnostic('ui.analyze', 'translation_config.loaded', {
          providers: (cfg?.providers || []).map((provider) => ({
            id: provider.id,
            enabled: provider.enabled,
          })),
          defaultProvider: cfg?.default_provider || 'm2m100',
        })
      } catch (err) {
        recordRuntimeDiagnostic('ui.analyze', 'translation_config.load_error', err, 'error')
        if (stopped) return
        // Keep "Loading…" instead of an incorrect fallback, then do one delayed retry.
        setTranslationConfig(null)
        window.setTimeout(async () => {
          if (stopped) return
          try {
            const retryCfg = await withRetry(() => api.getTranslationConfig(), 3, 400)
            if (stopped) return
            setTranslationConfig(retryCfg || FALLBACK_TRANSLATION_CONFIG)
            recordRuntimeDiagnostic('ui.analyze', 'translation_config.retry_loaded', {
              providers: (retryCfg?.providers || []).map((provider) => ({
                id: provider.id,
                enabled: provider.enabled,
              })),
              defaultProvider: retryCfg?.default_provider || 'm2m100',
            })
          } catch (retryErr) {
            recordRuntimeDiagnostic('ui.analyze', 'translation_config.retry_failed', retryErr, 'error')
            if (!stopped) setTranslationConfig(FALLBACK_TRANSLATION_CONFIG)
          }
        }, 900)
      }
    }
    void loadTranslationConfig()
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
          const sameId = Boolean(currentMediaFileId && rowFileId && rowFileId === currentMediaFileId)
          const samePath = Boolean(currentMediaPath && rowFilePath && rowFilePath === currentMediaPath)
          const sameName = Boolean(currentMediaFileName && rowFileName && rowFileName === currentMediaFileName)
          // Files are often re-registered and receive a new media_file_id.
          // History linkage must still work by stable path/name when id changed.
          return sameId || samePath || sameName
        })
        recordRuntimeDiagnostic('ui.analyze', 'history.filter', {
          projectId: selectedProject.project_id || null,
          currentMediaFileId,
          currentMediaPath,
          currentMediaFileName,
          totalRows: historyRows.length,
          matchedRows: fileRows.length,
          sample: fileRows.slice(0, 3).map((row) => ({
            documentId: row.document_id,
            mediaFileId: row.media_file_id || null,
            fileName: row.file_name,
            filePath: row.file_path || null,
          })),
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
              settings: String(row.settings || ''),
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
            settings: item.settings,
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

  const activeDocumentId = submission?.result.document_id || activeMedia?.documentId
  const stageLogLines = (submission?.result.stage_logs || []).slice(-10)

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
        setSubmission((prev) => {
          if (!prev || prev.result.document_id !== docId) return prev
          return { ...prev, result: { ...prev.result, document_id: undefined } }
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

  const stageProgress = useMemo(() => {
    if (Array.isArray(submission?.result.stage_progress) && submission.result.stage_progress.length >= 5) {
      return submission.result.stage_progress
    }
    return [0, 0, 0, 0, 0]
  }, [submission])

  useEffect(() => {
    const shouldTick =
      Boolean(submission) &&
      typeof submission?.result.processing_duration_ms !== 'number' &&
      (isSubmittingPipeline || stageProgress.some((value) => Number(value) > 0 && Number(value) < 100))
    if (!shouldTick) return
    const ticker = window.setInterval(() => setNowTs(Date.now()), 1000)
    return () => window.clearInterval(ticker)
  }, [submission, isSubmittingPipeline, stageProgress])

  const stageTitle = useMemo(() => {
    const value = String(submission?.result.stage_name || '').trim().toLowerCase()
    if (!value) return ''
    if (value === 'translating_text') return 'linguistic parsing'
    return value.replace(/_/g, ' ')
  }, [submission?.result.stage_name])
  const elapsedSec = useMemo(() => {
    if (typeof submission?.result.processing_duration_ms === 'number') {
      return Math.max(0, Math.round(submission.result.processing_duration_ms / 1000))
    }
    if (!analysisStartedAt) return 0
    return Math.max(0, Math.floor((nowTs - analysisStartedAt) / 1000))
  }, [submission?.result.processing_duration_ms, analysisStartedAt, nowTs])
  const estimatedSec = useMemo(() => {
    const progressValues = stageProgress.map((value) => {
      const n = Number(value)
      if (!Number.isFinite(n)) return 0
      return Math.max(0, Math.min(100, n))
    })
    const progressFraction = progressValues.reduce((acc, value) => acc + value, 0) / (progressValues.length * 100)
    const sourceDuration =
      Number(activeMedia?.durationSec ?? selectedMediaFromRoute?.durationSec ?? 0)
    if (elapsedSec > 0 && progressFraction >= 0.03) {
      return Math.max(elapsedSec + 1, Math.round(elapsedSec / Math.max(progressFraction, 0.03)))
    }
    if (sourceDuration > 0) return Math.max(20, Math.round(sourceDuration * 1.8))
    return 60
  }, [elapsedSec, stageProgress, activeMedia?.durationSec, selectedMediaFromRoute?.durationSec])

  return (
    <section className="screen-block analyze-stack">
      {showDirectSelector ? (
        <section className="card compact-card" aria-label="analyze-direct-select">
          <p className="stage-log-title">Select project and file</p>
          <div className="analyze-grid">
            <label className="analyze-label">Project</label>
            <div className="touch-options-grid">
              {projects.length > 0 ? (
                projects.map((project) => (
                  <button
                    key={project.id}
                    type="button"
                    className={`touch-option-btn${directProjectId === project.id ? ' active' : ''}`}
                    onClick={async () => {
                      const projectId = project.id
                      setDirectProjectId(projectId)
                      setDirectFileId('')
                      const selected = await api.setSelectedProject(projectId)
                      setSelectedProject(selected)
                    }}
                  >
                    {project.name}
                  </button>
                ))
              ) : (
                <span className="muted">No projects available.</span>
              )}
            </div>
            <label className="analyze-label">File</label>
            <div className="touch-options-grid">
              {!directProjectId ? (
                <span className="muted">Select project first.</span>
              ) : directFiles.length > 0 ? (
                directFiles.map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    className={`touch-option-btn${directFileId === file.id ? ' active' : ''}`}
                    onClick={() => setDirectFileId(file.id)}
                  >
                    {file.name}
                  </button>
                ))
              ) : (
                <span className="muted">No files in this project.</span>
              )}
            </div>
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
          if (payload.result.status === 'cancelled') {
            // Return to initial state — clear submission card, reset timer
            setSubmission(null)
            setIsSubmittingPipeline(false)
            setAnalysisStartedAt(null)
            return
          }
          setSubmission(payload)
          setIsSubmittingPipeline(false)
          if (!analysisStartedAt) {
            setAnalysisStartedAt(Date.now())
            setNowTs(Date.now())
          }
          if (payload.result.document_id) {
            setActiveMedia((prev) => (prev ? { ...prev, documentId: payload.result.document_id } : prev))
          } else {
            setActiveMedia((prev) => (prev ? { ...prev, documentId: undefined } : prev))
          }
          setHistoryReloadKey((prev) => prev + 1)
        }}
        onProgress={(payload) => {
          setSubmission((prev) => {
            const prevResult = prev?.result
            const logs = payload.stage_logs || prevResult?.stage_logs || []
            return {
              result: {
                route: prevResult?.route || 'local',
                message: payload.message || prevResult?.message || 'Processing...',
                status: prevResult?.status || 'running_local',
                stage_name: payload.stage_name || prevResult?.stage_name || '',
                stage_log: logs.slice(-10).join('\n'),
                stage_logs: logs,
                stage_progress: payload.stage_progress || prevResult?.stage_progress || [0, 0, 0, 0, 0],
                processing_duration_ms: prevResult?.processing_duration_ms,
                document_id: prevResult?.document_id,
                job_id: prevResult?.job_id,
              },
              ui_feedback: {
                severity: prev?.ui_feedback?.severity || 'info',
                title: prev?.ui_feedback?.title || 'Local processing',
                message: payload.message || prev?.ui_feedback?.message || 'Processing...',
              },
            }
          })
        }}
        onSubmittingChange={(value) => {
          setIsSubmittingPipeline(value)
          if (value) {
            setAnalysisStartedAt(Date.now())
            setNowTs(Date.now())
            setSubmission({
              result: {
                route: 'local',
                status: 'running_local',
                message: 'Starting pipeline...',
                stage_name: 'loading_file',
                stage_log: '',
                stage_logs: [],
                stage_progress: [0, 0, 0, 0, 0],
              },
              ui_feedback: {
                severity: 'info',
                title: 'Local processing',
                message: 'Starting pipeline...',
              },
            })
          }
        }}
        projectId={selectedProject.project_id ?? null}
        projectLabel={activeMedia ? (selectedProject.project_name ?? selectedProject.project_id ?? 'Project') : ''}
        stageProgress={stageProgress}
        activeStageIndex={null}
        isAnalyzing={isSubmittingPipeline}
        initialMedia={activeMedia ?? undefined}
        translatorOptions={translationConfig?.providers || []}
        defaultTranslator={translationConfig?.default_provider || 'm2m100'}
      />
      {submission ? (
        <section className={`card feedback ${submission.ui_feedback.severity}`} aria-label="submission-feedback">
          <p>{submission.ui_feedback.message}</p>
          <p className="stage-log-title">Elapsed: {elapsedSec >= 100 ? `${Math.floor(elapsedSec / 60)}m ${elapsedSec % 60}s` : `${elapsedSec}s`} / Estimated: {estimatedSec >= 100 ? `${Math.floor(estimatedSec / 60)}m ${estimatedSec % 60}s` : `${estimatedSec}s`}</p>
          {typeof submission.result.processing_duration_ms === 'number' ? (
            <p className="stage-log-title">
              Total duration: {Math.max(0, Math.round(submission.result.processing_duration_ms / 1000))}s
            </p>
          ) : null}
          {stageTitle ? (
            <p className="stage-log-title">Stage: {stageTitle}</p>
          ) : null}
          {stageLogLines.length > 0 ? (
            <pre className="stage-log-box">{stageLogLines.join('\n')}</pre>
          ) : null}
        </section>
      ) : null}
      {activeMedia?.mediaPath && activeMedia?.fileName ? (
        <section className="card compact-card" aria-label="source-file-download">
          <p className="stage-log-title">Source file</p>
          <div className="artifact-actions">
            <a
              className="top-link"
              href="#"
              download={activeMedia.fileName}
              onClick={async (e) => {
                e.preventDefault()
                const blob = await api.getSourceFileBlob(activeMedia.mediaPath!)
                if (!blob) return
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = activeMedia.fileName!
                document.body.appendChild(a)
                a.click()
                document.body.removeChild(a)
                setTimeout(() => URL.revokeObjectURL(url), 10000)
              }}
            >
              Download {activeMedia.fileName}
            </a>
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
                  const featureBadges = buildAnalysisFeatureBadges(item.settings)
                  return (
                  <article key={`${item.analysis_id}-${item.document_id}`} className="analysis-history-item">
                    <div className="analysis-history-head">
                      <strong>{item.file_name}</strong>
                      <div className="actions-row">
                        {item.document_id ? (
                          <button
                            type="button"
                            onClick={() =>
                              navigate('/visualizer', {
                                state: {
                                  documentId: item.document_id,
                                  documentMeta: {
                                    [item.document_id]: {
                                      project: selectedProject.project_name ?? selectedProject.project_id ?? '-',
                                      file: item.file_name,
                                    },
                                  },
                                },
                              })
                            }
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
                    {featureBadges.length > 0 ? (
                      <div className="analysis-feature-badges">
                        {featureBadges.map((badge) => (
                          <span key={`${item.analysis_id}-${badge.key}`} className="badge analysis-feature-badge">
                            {badge.label}: {badge.value}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <div className="artifact-actions">
                      {item.artifacts.length > 0 ? (
                        item.artifacts.map((artifact) => (
                          <a
                            key={`${item.file_id}-${artifact.name}`}
                            className="top-link"
                            href={artifact.download_url}
                            download={buildExportFileName(item.file_name, item.settings, artifact.name)}
                            onClick={(e) => {
                              e.preventDefault()
                              const a = document.createElement('a')
                              a.href = artifact.download_url
                              a.download = buildExportFileName(item.file_name, item.settings, artifact.name)
                              document.body.appendChild(a)
                              a.click()
                              document.body.removeChild(a)
                            }}
                          >
                            Download {buildExportFileName(item.file_name, item.settings, artifact.name)}
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
