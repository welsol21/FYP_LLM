import type {
  AnalysisHistoryRow,
  DocumentArtifact,
  MediaFileRow,
  ProjectRow,
  SelectedProject,
  TranslationConfig,
  VisualizerNode,
  VisualizerPayload,
} from '../api/runtimeApi'

const STORAGE_KEY = 'ela_frontend_workspace_v1'

type WorkspaceFile = MediaFileRow & {
  project_id: string
  media_path: string
  created_at: string
}

type WorkspaceAnalysis = AnalysisHistoryRow & {
  contract: VisualizerPayload
  artifacts?: DocumentArtifact[]
}

type WorkspaceState = {
  projects: ProjectRow[]
  selected_project_id: string | null
  files: WorkspaceFile[]
  analyses: WorkspaceAnalysis[]
  translation_config: TranslationConfig | null
}

const DEFAULT_TRANSLATION_CONFIG: TranslationConfig = {
  default_provider: 'm2m100',
  providers: [
    { id: 'm2m100', label: 'Our Translator (M2M100)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
    { id: 'hf', label: 'HuggingFace', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
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

function nowIso(): string {
  return new Date().toISOString()
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function fallbackProject(): ProjectRow {
  const ts = nowIso()
  return {
    id: `proj-${Math.random().toString(36).slice(2, 10)}`,
    name: 'New Project 1',
    created_at: ts,
    updated_at: ts,
  }
}

function loadRawState(): WorkspaceState {
  const empty: WorkspaceState = {
    projects: [],
    selected_project_id: null,
    files: [],
    analyses: [],
    translation_config: null,
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return empty
    const parsed = JSON.parse(raw) as Partial<WorkspaceState>
    const state: WorkspaceState = {
      projects: Array.isArray(parsed.projects) ? parsed.projects : [],
      selected_project_id: typeof parsed.selected_project_id === 'string' ? parsed.selected_project_id : null,
      files: Array.isArray(parsed.files) ? parsed.files : [],
      analyses: Array.isArray(parsed.analyses) ? parsed.analyses : [],
      translation_config: parsed.translation_config ?? null,
    }
    return state
  } catch {
    return empty
  }
}

function saveRawState(state: WorkspaceState): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

function ensureState(): WorkspaceState {
  const state = loadRawState()
  if (state.projects.length === 0) {
    const project = fallbackProject()
    state.projects = [project]
    state.selected_project_id = project.id
    saveRawState(state)
    return state
  }
  if (!state.selected_project_id || !state.projects.some((p) => p.id === state.selected_project_id)) {
    state.selected_project_id = state.projects[0].id
    saveRawState(state)
  }
  return state
}

function pickProject(state: WorkspaceState, projectId?: string): ProjectRow {
  const requested = String(projectId || '').trim()
  const found = requested ? state.projects.find((p) => p.id === requested) : null
  return found || state.projects.find((p) => p.id === state.selected_project_id) || state.projects[0]
}

function normalizeSettings(settings: string | undefined): string {
  return String(settings || '').trim() || 'Transl: m2m100 / Subs: bilingual / Voice: male'
}

function parsePath(path: string): Array<string | number> {
  const out: Array<string | number> = []
  const normalized = path.replace(/\[(\d+)\]/g, '.$1')
  for (const part of normalized.split('.').filter(Boolean)) {
    if (/^\d+$/.test(part)) out.push(Number(part))
    else out.push(part)
  }
  return out
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
      if (cur[token] == null) cur[token] = typeof nextToken === 'number' ? [] : {}
      cur = cur[token]
    } else {
      if (typeof cur !== 'object' || cur == null) return false
      const dict = cur as Record<string, unknown>
      if (dict[token] == null) dict[token] = typeof nextToken === 'number' ? [] : {}
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

function findNodeById(root: VisualizerNode, nodeId: string): VisualizerNode | null {
  const stack: VisualizerNode[] = [root]
  while (stack.length > 0) {
    const node = stack.pop() as VisualizerNode
    if (String(node.node_id) === String(nodeId)) return node
    for (const child of node.linguistic_elements || []) stack.push(child)
  }
  return null
}

export const LocalWorkspace = {
  listProjects(): ProjectRow[] {
    const state = ensureState()
    return clone([...state.projects].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))))
  },

  createProject(name: string): ProjectRow {
    const state = ensureState()
    const ts = nowIso()
    const project: ProjectRow = {
      id: `proj-${Math.random().toString(36).slice(2, 10)}`,
      name: String(name || '').trim() || `New Project ${state.projects.length + 1}`,
      created_at: ts,
      updated_at: ts,
    }
    state.projects.unshift(project)
    state.selected_project_id = project.id
    saveRawState(state)
    return clone(project)
  },

  getSelectedProject(): SelectedProject {
    const state = ensureState()
    const row = state.projects.find((p) => p.id === state.selected_project_id) || state.projects[0]
    return { project_id: row?.id || null, project_name: row?.name }
  },

  setSelectedProject(projectId: string): SelectedProject {
    const state = ensureState()
    const row = state.projects.find((p) => p.id === projectId)
    if (!row) return { project_id: null }
    state.selected_project_id = row.id
    saveRawState(state)
    return { project_id: row.id, project_name: row.name }
  },

  registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): WorkspaceFile {
    const state = ensureState()
    const project = pickProject(state, input.projectId)
    const ts = nowIso()
    const file: WorkspaceFile = {
      id: `file-${Math.random().toString(36).slice(2, 10)}`,
      project_id: project.id,
      name: input.name,
      path: input.mediaPath,
      media_path: input.mediaPath,
      size_bytes: input.sizeBytes,
      duration_seconds: input.durationSec,
      settings: normalizeSettings(undefined),
      updated: ts,
      created_at: ts,
      analyzed: false,
    }
    state.files.unshift(file)
    const projectRow = state.projects.find((p) => p.id === project.id)
    if (projectRow) projectRow.updated_at = ts
    saveRawState(state)
    return clone(file)
  },

  getFileById(fileId: string): WorkspaceFile | null {
    const state = ensureState()
    const row = state.files.find((f) => f.id === fileId)
    return row ? clone(row) : null
  },

  listFiles(projectId?: string): MediaFileRow[] {
    const state = ensureState()
    const rows = state.files
      .filter((f) => !projectId || f.project_id === projectId)
      .sort((a, b) => String(b.updated).localeCompare(String(a.updated)))
    return clone(rows)
  },

  upsertAnalysis(input: {
    documentId: string
    projectId: string
    mediaFileId?: string
    fileName: string
    filePath?: string
    sizeBytes?: number
    durationSeconds?: number
    settings: string
    contract: VisualizerPayload
    artifacts?: DocumentArtifact[]
  }): AnalysisHistoryRow {
    const state = ensureState()
    const ts = nowIso()
    const project = pickProject(state, input.projectId)
    const existingIdx = state.analyses.findIndex((a) => a.document_id === input.documentId)
    const existing = existingIdx >= 0 ? state.analyses[existingIdx] : null
    const row: WorkspaceAnalysis = {
      analysis_id: input.documentId,
      document_id: input.documentId,
      project_id: project.id,
      project_name: project.name,
      media_file_id: input.mediaFileId || null,
      file_name: input.fileName,
      file_path: input.filePath || '',
      size_bytes: input.sizeBytes,
      duration_seconds: input.durationSeconds,
      settings: normalizeSettings(input.settings),
      updated_at: ts,
      created_at: existing ? existing.created_at : ts,
      contract_current: true,
      contract: clone(input.contract),
      artifacts: clone(input.artifacts || existing?.artifacts || []),
    }
    if (existingIdx >= 0) state.analyses[existingIdx] = row
    else state.analyses.unshift(row)
    if (input.mediaFileId) {
      const file = state.files.find((f) => f.id === input.mediaFileId)
      if (file) {
        file.analyzed = true
        file.document_id = input.documentId
        file.updated = ts
        file.settings = normalizeSettings(input.settings)
      }
    }
    const projectRow = state.projects.find((p) => p.id === project.id)
    if (projectRow) projectRow.updated_at = ts
    saveRawState(state)
    return clone(row)
  },

  listAnalysisHistory(projectId?: string): AnalysisHistoryRow[] {
    const state = ensureState()
    const rows = state.analyses
      .filter((a) => !projectId || a.project_id === projectId)
      .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
      .map((row) => {
        const { contract: _contract, artifacts: _artifacts, ...rest } = row
        return rest
      })
    return clone(rows)
  },

  getVisualizerPayload(documentId?: string): VisualizerPayload {
    const docId = String(documentId || '').trim()
    if (!docId) return {}
    const state = ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    return clone(row?.contract || {})
  },

  applyEdit(input: {
    documentId: string
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: unknown
  }): { status: 'ok' | 'error'; message: string } {
    const state = ensureState()
    const row = state.analyses.find((a) => a.document_id === input.documentId || a.analysis_id === input.documentId)
    if (!row) return { status: 'error', message: 'Analysis not found.' }
    const sentenceNode = row.contract[input.sentenceText]
    if (!sentenceNode) return { status: 'error', message: 'Sentence not found.' }
    const node = findNodeById(sentenceNode, input.nodeId)
    if (!node) return { status: 'error', message: 'node_id not found.' }
    const ok = setByPath(node, input.fieldPath, input.newValue)
    if (!ok) return { status: 'error', message: `Invalid field path: ${input.fieldPath}` }
    row.updated_at = nowIso()
    saveRawState(state)
    return { status: 'ok', message: 'Edit applied.' }
  },

  deleteAnalysis(documentId: string): { status: 'ok' | 'error'; message: string; document_id?: string } {
    const state = ensureState()
    const docId = String(documentId || '').trim()
    const before = state.analyses.length
    state.analyses = state.analyses.filter((a) => a.document_id !== docId && a.analysis_id !== docId)
    const deleted = before !== state.analyses.length
    if (!deleted) return { status: 'error', message: 'analysis not found', document_id: docId }
    for (const file of state.files) {
      if (String(file.document_id || '') === docId) {
        file.analyzed = false
        file.document_id = undefined
        file.updated = nowIso()
      }
    }
    saveRawState(state)
    return { status: 'ok', message: 'Analysis artifacts deleted.', document_id: docId }
  },

  listDocumentArtifacts(documentId: string): DocumentArtifact[] {
    const docId = String(documentId || '').trim()
    if (!docId) return []
    const state = ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    if (!row) return []
    return clone(Array.isArray(row.artifacts) ? row.artifacts : [])
  },

  getTranslationConfig(): TranslationConfig | null {
    const state = ensureState()
    return state.translation_config ? clone(state.translation_config) : clone(DEFAULT_TRANSLATION_CONFIG)
  },

  saveTranslationConfig(config: TranslationConfig): TranslationConfig {
    const state = ensureState()
    state.translation_config = clone(config)
    saveRawState(state)
    return clone(config)
  },
}
