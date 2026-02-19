import samplePayload from './frontend_contract_sample.json'
import type {
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
      path: '/uploads/sample.mp4',
      size_bytes: 104857600,
      duration_seconds: 600,
      settings: 'GPT / Bilingual',
      updated: 'Feb 17, 2026',
      analyzed: true,
      document_id: 'doc-1',
    },
    {
      id: 'file-2',
      name: 'draft.mp3',
      path: '/uploads/draft.mp3',
      size_bytes: 5242880,
      duration_seconds: 120,
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
        phonetic: 'Phonetic: on',
      },
      features: {
        phonetic: { enabled: true, reason_if_disabled: '' },
        db_persistence: { enabled: true, reason_if_disabled: '' },
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

  async registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): Promise<{ id: string; project_id: string; name: string; path: string; size_bytes?: number; duration_seconds?: number }> {
    const fileId = `file-${this.files.length + 1}`
    this.fileProjectId[fileId] = input.projectId
    this.files.unshift({
      id: fileId,
      name: input.name,
      path: input.mediaPath,
      size_bytes: input.sizeBytes,
      duration_seconds: input.durationSec,
      settings: 'HF / Runtime',
      updated: new Date().toISOString().slice(0, 10),
      analyzed: false,
    })
    return {
      id: fileId,
      project_id: input.projectId,
      name: input.name,
      path: input.mediaPath,
      size_bytes: input.sizeBytes,
      duration_seconds: input.durationSec,
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
        path: input.mediaPath,
        size_bytes: input.sizeBytes,
        duration_seconds: input.durationSec,
        settings: 'HF / Local',
        updated: 'Feb 18, 2026',
        analyzed: true,
        document_id: docId,
      })
      return {
        result: { route: 'local', message: 'File accepted for local processing.', status: 'completed_local', document_id: docId },
        ui_feedback: {
          severity: 'info',
          title: 'Local processing started',
          message: 'File accepted for local processing.',
        },
      }
    }
    return {
      result: { route: 'reject', message: 'File exceeds local processing limits.' },
      ui_feedback: {
        severity: 'error',
        title: 'File rejected by media policy',
        message: 'File exceeds local processing limits.',
      },
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
