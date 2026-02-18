import samplePayload from './frontend_contract_sample.json'
import type {
  BackendJob,
  BackendJobStatus,
  BackendResumePayload,
  BackendSyncPayload,
  MediaFileRow,
  MediaSubmissionPayload,
  ProjectRow,
  RuntimeApi,
  RuntimeUiState,
  SelectedProject,
  VisualizerNode,
  VisualizerPayload,
} from './runtimeApi'

function parsePath(path: string): Array<string | number> {
  const out: Array<string | number> = []
  const normalized = path.replace(/\[(\d+)\]/g, '.$1')
  for (const part of normalized.split('.').filter(Boolean)) {
    if (/^\d+$/.test(part)) out.push(Number(part))
    else out.push(part)
  }
  return out
}

function getByPath(root: unknown, path: string): unknown {
  const tokens = parsePath(path)
  let cur: unknown = root
  for (const token of tokens) {
    if (cur == null) return undefined
    if (typeof token === 'number') {
      if (!Array.isArray(cur)) return undefined
      cur = cur[token]
    } else {
      if (typeof cur !== 'object') return undefined
      cur = (cur as Record<string, unknown>)[token]
    }
  }
  return cur
}

function setByPath(root: unknown, path: string, value: unknown): boolean {
  const tokens = parsePath(path)
  if (tokens.length === 0 || root == null || typeof root !== 'object') return false
  let cur: unknown = root
  for (let i = 0; i < tokens.length - 1; i += 1) {
    const token = tokens[i]
    const nextToken = tokens[i + 1]
    if (typeof token === 'number') {
      if (!Array.isArray(cur)) return false
      if (cur[token] == null) {
        cur[token] = typeof nextToken === 'number' ? [] : {}
      }
      cur = cur[token]
    } else {
      if (typeof cur !== 'object' || cur == null) return false
      const dict = cur as Record<string, unknown>
      if (dict[token] == null) {
        dict[token] = typeof nextToken === 'number' ? [] : {}
      }
      cur = dict[token]
    }
  }

  const last = tokens[tokens.length - 1]
  if (typeof last === 'number') {
    if (!Array.isArray(cur)) return false
    cur[last] = value
    return true
  }
  if (typeof cur !== 'object' || cur == null) return false
  ;(cur as Record<string, unknown>)[last] = value
  return true
}

function coerceInputValue(raw: string, existing: unknown): unknown {
  if (raw === '__NULL__') return null
  if (Array.isArray(existing)) {
    const trimmed = raw.trim()
    if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (Array.isArray(parsed)) return parsed
      } catch {
        // fallback below
      }
    }
    return raw
      .split('\n')
      .map((v) => v.trim())
      .filter(Boolean)
  }
  if (typeof existing === 'number') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : existing
  }
  if (typeof existing === 'boolean') {
    return raw.trim().toLowerCase() === 'true'
  }
  if (existing && typeof existing === 'object') {
    try {
      return JSON.parse(raw)
    } catch {
      return existing
    }
  }
  return raw
}

export class MockRuntimeApi implements RuntimeApi {
  private projects: ProjectRow[] = [
    {
      id: 'proj-1',
      name: 'Demo Project',
      created_at: '2026-02-17T00:00:00Z',
      updated_at: '2026-02-18T00:00:00Z',
    },
  ]
  private selectedProjectId: string | null = 'proj-1'
  private jobs: BackendJob[] = []
  private jobPollCount: Record<string, number> = {}
  private jobFileId: Record<string, string> = {}
  private jobDocumentId: Record<string, string> = {}
  private fileProjectId: Record<string, string> = {
    'file-1': 'proj-1',
    'file-2': 'proj-1',
  }
  private payloadByDocument: Record<string, VisualizerPayload> = {
    'doc-1': JSON.parse(JSON.stringify(samplePayload)) as VisualizerPayload,
  }
  private files: MediaFileRow[] = [
    {
      id: 'file-1',
      name: 'sample.mp4',
      settings: 'GPT / Bilingual',
      updated: 'Feb 17, 2026',
      analyzed: true,
      document_id: 'doc-1',
    },
    {
      id: 'file-2',
      name: 'draft.mp3',
      settings: 'HF / EN only',
      updated: 'Feb 18, 2026',
      analyzed: false,
    },
  ]

  async getUiState(): Promise<RuntimeUiState> {
    return {
      runtime_mode: 'online',
      deployment_mode: 'local',
      badges: {
        mode: 'Mode: online',
        deployment: 'Deployment: local',
        backend_jobs: 'Backend jobs: on',
        phonetic: 'Phonetic: on',
      },
      features: {
        phonetic: { enabled: true, reason_if_disabled: '' },
        db_persistence: { enabled: true, reason_if_disabled: '' },
        backend_jobs: { enabled: true, reason_if_disabled: '' },
      },
    }
  }

  async listProjects(): Promise<ProjectRow[]> {
    return this.projects
  }

  async createProject(name: string): Promise<ProjectRow> {
    const now = new Date().toISOString()
    const row: ProjectRow = {
      id: `proj-${this.projects.length + 1}`,
      name: name.trim() || `Project ${this.projects.length + 1}`,
      created_at: now,
      updated_at: now,
    }
    this.projects.unshift(row)
    return row
  }

  async getSelectedProject(): Promise<SelectedProject> {
    if (!this.selectedProjectId) return { project_id: null }
    const row = this.projects.find((p) => p.id === this.selectedProjectId)
    return { project_id: this.selectedProjectId, project_name: row?.name }
  }

  async setSelectedProject(projectId: string): Promise<SelectedProject> {
    const row = this.projects.find((p) => p.id === projectId)
    if (!row) return { project_id: null }
    this.selectedProjectId = projectId
    return { project_id: projectId, project_name: row.name }
  }

  async uploadMedia(file: File): Promise<{ fileName: string; mediaPath: string; sizeBytes: number }> {
    return {
      fileName: file.name,
      mediaPath: `/uploads/${file.name}`,
      sizeBytes: file.size,
    }
  }

  async submitMedia(input: {
    mediaPath: string
    durationSec: number
    sizeBytes: number
    projectId?: string
  }): Promise<MediaSubmissionPayload> {
    if (!input.projectId) {
      return {
        result: { route: 'reject', message: 'Select project first.' },
        ui_feedback: {
          severity: 'error',
          title: 'Project is required',
          message: 'Create/select a project before starting pipeline.',
        },
      }
    }
    const mediaName = input.mediaPath.split('/').pop() || input.mediaPath
    if (input.durationSec <= 900 && input.sizeBytes <= 250 * 1024 * 1024) {
      const fileId = `file-${this.files.length + 1}`
      const docId = `doc-${Object.keys(this.payloadByDocument).length + 1}`
      this.fileProjectId[fileId] = input.projectId
      this.payloadByDocument[docId] = JSON.parse(JSON.stringify(samplePayload)) as VisualizerPayload
      this.files.unshift({
        id: fileId,
        name: mediaName,
        settings: 'HF / Local',
        updated: 'Feb 18, 2026',
        analyzed: true,
        document_id: docId,
      })
      return {
        result: { route: 'local', message: 'File accepted for local processing.' },
        ui_feedback: {
          severity: 'info',
          title: 'Local processing started',
          message: 'File accepted for local processing.',
        },
      }
    }
    if (input.sizeBytes <= 2048 * 1024 * 1024) {
      const fileId = `file-${this.files.length + 1}`
      this.fileProjectId[fileId] = input.projectId
      const job: BackendJob = {
        id: `job-${this.jobs.length + 1}`,
        status: 'queued',
        media_path: input.mediaPath,
        duration_seconds: input.durationSec,
        size_bytes: input.sizeBytes,
      }
      this.jobPollCount[job.id] = 0
      this.jobFileId[job.id] = fileId
      this.jobs.unshift(job)
      this.files.unshift({
        id: fileId,
        name: mediaName,
        settings: 'HF / Backend',
        updated: 'Feb 18, 2026',
        analyzed: false,
      })
      return {
        result: { route: 'backend', message: 'Queued for backend processing.', job_id: job.id },
        ui_feedback: {
          severity: 'warning',
          title: 'Queued for backend processing',
          message: `Queued for backend processing. Job ID: ${job.id}`,
        },
      }
    }
    return {
      result: { route: 'reject', message: 'File exceeds backend size limit.' },
      ui_feedback: {
        severity: 'error',
        title: 'File rejected by media policy',
        message: 'File exceeds backend size limit.',
      },
    }
  }

  async listBackendJobs(): Promise<BackendJob[]> {
    return this.jobs
  }

  async getBackendJobStatus(jobId: string): Promise<BackendJobStatus> {
    const job = this.jobs.find((j) => j.id === jobId)
    if (!job) return { job_id: jobId, status: 'not_found' }
    const polls = (this.jobPollCount[jobId] || 0) + 1
    this.jobPollCount[jobId] = polls
    if (job.status === 'queued' && polls >= 1) job.status = 'processing'
    if (job.status === 'processing' && polls >= 2) job.status = 'completed'
    return { job_id: job.id, status: job.status }
  }

  async retryBackendJob(jobId: string): Promise<BackendSyncPayload> {
    const job = this.jobs.find((j) => j.id === jobId)
    if (!job) return { job_id: jobId, status: 'not_found', message: 'Job not found.' }
    if (!['failed', 'error', 'canceled'].includes(job.status)) {
      return { job_id: job.id, status: job.status, message: `Job is not retryable from status '${job.status}'.` }
    }
    job.status = 'queued'
    this.jobPollCount[job.id] = 0
    return { job_id: job.id, status: 'queued', message: 'Job moved to queued.' }
  }

  async resumeBackendJobs(): Promise<BackendResumePayload> {
    const jobs = this.jobs
      .filter((j) => ['queued', 'processing'].includes(j.status))
      .map((j) => ({ job_id: j.id, status: j.status }))
    return { resumed_count: jobs.length, jobs }
  }

  async syncBackendResult(jobId: string): Promise<BackendSyncPayload> {
    const job = this.jobs.find((j) => j.id === jobId)
    if (!job) return { job_id: jobId, status: 'not_found', message: 'Job not found.' }
    if (job.status !== 'completed') {
      return { job_id: jobId, status: job.status, message: 'Job is not completed yet.' }
    }
    const docId = this.jobDocumentId[jobId] || `doc-${Object.keys(this.payloadByDocument).length + 1}`
    this.jobDocumentId[jobId] = docId
    if (!this.payloadByDocument[docId]) {
      this.payloadByDocument[docId] = JSON.parse(JSON.stringify(samplePayload)) as VisualizerPayload
    }
    const fileId = this.jobFileId[jobId]
    const file = this.files.find((f) => f.id === fileId)
    if (file) {
      file.analyzed = true
      file.document_id = docId
      file.updated = 'Feb 18, 2026'
    }
    return {
      job_id: jobId,
      status: 'completed',
      document_id: docId,
      message: 'Backend result synced to local document tables.',
    }
  }

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    if (!projectId) return this.files
    return this.files.filter((row) => this.fileProjectId[row.id] === projectId)
  }

  async getVisualizerPayload(_documentId?: string): Promise<VisualizerPayload> {
    if (_documentId) return this.payloadByDocument[_documentId] || {}
    return this.payloadByDocument['doc-1'] || {}
  }

  async applyEdit(input: {
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: string
    documentId?: string
  }): Promise<{ status: 'ok' | 'error'; message: string }> {
    const docId = input.documentId || 'doc-1'
    const defaultDoc = this.payloadByDocument[docId] || {}
    const root = defaultDoc[input.sentenceText]
    if (!root) {
      return { status: 'error', message: 'Sentence not found.' }
    }
    const stack: VisualizerNode[] = [root]
    while (stack.length > 0) {
      const node = stack.pop() as VisualizerNode
      if (node.node_id === input.nodeId) {
        const current = getByPath(node, input.fieldPath)
        const nextValue = coerceInputValue(input.newValue, current)
        if (!setByPath(node, input.fieldPath, nextValue)) {
          return { status: 'error', message: `Invalid field path: ${input.fieldPath}` }
        }
        return { status: 'ok', message: 'Edit applied.' }
      }
      for (const child of node.linguistic_elements) stack.push(child)
    }
    return { status: 'error', message: 'node_id not found.' }
  }
}
