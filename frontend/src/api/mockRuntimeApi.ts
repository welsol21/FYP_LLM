import samplePayload from './frontend_contract_sample.json'
import type {
  AnalysisHistoryRow,
  AnalyzeTextPayload,
  DocumentArtifact,
  MediaFileRow,
  MediaProgressPayload,
  MediaSubmissionPayload,
  ProjectRow,
  RuntimeApi,
  RuntimeUiState,
  SelectedProject,
  TranslationConfig,
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

function countPayloadElements(payload: VisualizerPayload | null | undefined): number {
  if (!payload) return 0
  let total = 0
  const stack: VisualizerNode[] = Object.values(payload).filter(Boolean) as VisualizerNode[]
  while (stack.length > 0) {
    const node = stack.pop() as VisualizerNode
    for (const child of node.linguistic_elements || []) {
      total += 1
      stack.push(child)
    }
  }
  return total
}

export class MockRuntimeApi implements RuntimeApi {
  private translationConfig: TranslationConfig = {
    default_provider: 'm2m100',
    providers: [
      { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
      { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: false, credential_fields: ['api_key'], credentials: { api_key: '' } },
      { id: 'deepl', label: 'DeepL', kind: 'builtin', enabled: false, credential_fields: ['auth_key'], credentials: { auth_key: '' } },
      { id: 'lara', label: 'Lara', kind: 'builtin', enabled: false, credential_fields: ['api_id', 'api_secret'], credentials: { api_id: '', api_secret: '' } },
      { id: 'original', label: 'Original only (no translation)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
    ],
  }
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
      settings: 'Transl: m2m100 / Subs: bilingual_sequential / Voice: male / Proc: incremental',
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
      settings: 'Transl: m2m100 / Subs: source_only / Voice: male / Proc: incremental',
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
    const trimmed = String(name || '').trim().replace(/\s+/g, ' ')
    if (!trimmed) {
      throw new Error('Project name is required.')
    }
    const normalized = trimmed.toLowerCase()
    const duplicate = this.projects.some((row) => String(row.name || '').trim().replace(/\s+/g, ' ').toLowerCase() === normalized)
    if (duplicate) {
      throw new Error('Project with this name already exists.')
    }
    const now = new Date().toISOString()
    const row: ProjectRow = {
      id: `proj-${this.projects.length + 1}`,
      name: trimmed,
      created_at: now,
      updated_at: now,
    }
    this.projects.unshift(row)
    return row
  }

  async deleteProject(projectId: string): Promise<{ status: 'ok' | 'error'; message: string; project_id?: string }> {
    const id = String(projectId || '').trim()
    if (!id) return { status: 'error', message: 'project id is required' }
    const existed = this.projects.some((p) => p.id === id)
    if (!existed) return { status: 'error', message: 'project not found', project_id: id }
    this.projects = this.projects.filter((p) => p.id !== id)
    const removedFileIds = new Set(
      this.files
        .filter((f) => this.fileProjectId[f.id] === id)
        .map((f) => f.id),
    )
    this.files = this.files.filter((f) => !removedFileIds.has(f.id))
    for (const fileId of removedFileIds) {
      delete this.fileProjectId[fileId]
    }
    for (const [docId, payload] of Object.entries(this.payloadByDocument)) {
      const linked = this.files.some((f) => f.document_id === docId)
      if (!linked || !payload) delete this.payloadByDocument[docId]
    }
    if (this.selectedProjectId === id) {
      this.selectedProjectId = this.projects[0]?.id ?? null
    }
    return { status: 'ok', message: 'Project and related data deleted.', project_id: id }
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
      settings: `Transl: ${this.translationConfig.default_provider} / Subs: bilingual / Voice: male / Proc: incremental`,
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
    translationProvider?: string
    subtitlesMode?: string
    voiceChoice?: string
    forceFullReprocess?: boolean
    onProgress?: (payload: MediaProgressPayload) => void
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
        settings: `Transl: ${input.translationProvider || this.translationConfig.default_provider} / Subs: ${input.subtitlesMode || 'bilingual'} / Voice: ${input.voiceChoice || 'male'} / Proc: ${input.forceFullReprocess ? 'force' : 'incremental'}`,
        updated: 'Feb 18, 2026',
        analyzed: true,
        document_id: docId,
      })
      const response: MediaSubmissionPayload = {
        result: { route: 'local', message: 'Local processing completed.', status: 'completed_local', document_id: docId },
        ui_feedback: {
          severity: 'info',
          title: 'Local processing completed',
          message: 'Local processing completed.',
        },
      }
      input.onProgress?.({
        stage_name: 'completed',
        message: response.ui_feedback.message,
        stage_logs: ['Local processing completed.'],
        stage_progress: [100, 100, 100, 100, 100],
      })
      return response
    }
    const response: MediaSubmissionPayload = {
      result: { route: 'reject', message: 'File exceeds local processing limits.' },
      ui_feedback: {
        severity: 'error',
        title: 'File rejected by media policy',
        message: 'File exceeds local processing limits.',
      },
    }
    input.onProgress?.({
      stage_name: 'rejected',
      message: response.ui_feedback.message,
      stage_logs: [response.ui_feedback.message],
      stage_progress: [100, 0, 0, 0, 0],
    })
    return response
  }

  async getTranslationConfig(): Promise<TranslationConfig> {
    const cfg = JSON.parse(JSON.stringify(this.translationConfig)) as TranslationConfig
    cfg.providers = cfg.providers.filter((p) => p.id !== 'hf')
    if (cfg.default_provider === 'hf') cfg.default_provider = 'm2m100'
    return cfg
  }

  async saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig> {
    this.translationConfig = JSON.parse(JSON.stringify(config)) as TranslationConfig
    return this.getTranslationConfig()
  }

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    if (!projectId) return this.files
    return this.files.filter((row) => this.fileProjectId[row.id] === projectId)
  }

  async deleteFile(fileId: string): Promise<{ status: 'ok' | 'error'; message: string; file_id?: string }> {
    const id = String(fileId || '').trim()
    if (!id) return { status: 'error', message: 'fileId is required.' }
    const row = this.files.find((item) => item.id === id)
    if (!row) return { status: 'error', message: 'file not found', file_id: id }
    const docId = String(row.document_id || '').trim()
    if (docId) delete this.payloadByDocument[docId]
    this.files = this.files.filter((item) => item.id !== id)
    delete this.fileProjectId[id]
    return { status: 'ok', message: 'File and related analyses deleted.', file_id: id }
  }

  async listAnalysisHistory(projectId?: string): Promise<AnalysisHistoryRow[]> {
    const projectRows = this.projects.reduce<Record<string, string>>((acc, row) => {
      acc[row.id] = row.name
      return acc
    }, {})
    const candidates = this.files.filter((row) => {
      if (!row.analyzed || !row.document_id) return false
      const fileProjectId = this.fileProjectId[row.id]
      if (projectId && fileProjectId !== projectId) return false
      return true
    })
    return candidates
      .map((row) => {
        const pid = this.fileProjectId[row.id] || ''
        return {
          analysis_id: String(row.document_id || row.id),
          document_id: String(row.document_id || ''),
          project_id: pid,
          project_name: projectRows[pid] || pid,
          media_file_id: row.id,
          file_name: row.name,
          file_path: row.path,
          size_bytes: row.size_bytes,
          duration_seconds: row.duration_seconds,
          settings: row.settings,
          items_count: countPayloadElements(this.payloadByDocument[String(row.document_id || '')]),
          updated_at: row.updated,
          created_at: row.updated,
          contract_current: true,
        }
      })
      .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
  }

  async deleteAnalysis(documentId: string): Promise<{ status: 'ok' | 'error'; message: string; document_id?: string }> {
    const docId = String(documentId || '').trim()
    if (!docId) {
      return { status: 'error', message: 'documentId is required.' }
    }
    const existed = Boolean(this.payloadByDocument[docId])
    delete this.payloadByDocument[docId]
    this.files = this.files.map((row) => (
      row.document_id === docId
        ? { ...row, analyzed: false, document_id: undefined }
        : row
    ))
    return existed
      ? { status: 'ok', message: 'Analysis artifacts deleted.', document_id: docId }
      : { status: 'error', message: 'analysis not found', document_id: docId }
  }

  async listDocumentArtifacts(documentId: string): Promise<DocumentArtifact[]> {
    if (!documentId || !this.payloadByDocument[documentId]) return []
    const payload = this.payloadByDocument[documentId] || {}
    const fullText = Object.keys(payload).join(' ')
    const subtitles = Object.keys(payload)
      .map((row, idx) => `${idx + 1}\n00:00:${String(idx * 3).padStart(2, '0')},000 --> 00:00:${String(idx * 3 + 2).padStart(2, '0')},000\n${row}\n`)
      .join('\n')
    const contractSentences = Object.entries(payload).map(([sentence_text, sentence_node]) => ({ sentence_text, sentence_node }))
    const encode = (mime: string, text: string): string => `data:${mime};charset=utf-8,${encodeURIComponent(text)}`
    const sizeOf = (text: string): number => new TextEncoder().encode(text).length
    return [
      {
        name: 'full_text.txt',
        size_bytes: sizeOf(fullText),
        download_url: encode('text/plain', fullText),
      },
      {
        name: 'subtitles_en.srt',
        size_bytes: sizeOf(subtitles),
        download_url: encode('application/x-subrip', subtitles),
      },
      {
        name: 'subtitles_bilingual.srt',
        size_bytes: sizeOf(subtitles),
        download_url: encode('application/x-subrip', subtitles),
      },
      {
        name: 'contract_sentences.json',
        size_bytes: sizeOf(JSON.stringify(contractSentences)),
        download_url: encode('application/json', JSON.stringify(contractSentences, null, 2)),
      },
    ]
  }

  async getVisualizerPayload(_documentId?: string): Promise<VisualizerPayload> {
    if (_documentId) return this.payloadByDocument[_documentId] || {}
    return this.payloadByDocument['doc-1'] || {}
  }

  async analyzeText(input: { rawText: string; sentences?: string[] }): Promise<AnalyzeTextPayload> {
    const raw = input.rawText.trim()
    const sentenceSource = Array.isArray(input.sentences) && input.sentences.length > 0
      ? input.sentences
      : raw
          .split(/(?<=[.!?])\s+/)
          .map((s) => s.trim())
          .filter(Boolean)
    return {
      raw_text: raw,
      sentences: sentenceSource,
      razbor: sentenceSource.map((sentence, idx) => ({
        id: `mock_${idx + 1}`,
        input: sentence,
        analysis: {
          architecture: {
            sentence_type: 'Simple',
            communicative_type: 'Declarative',
            clauses: [{ role: 'main', marker: null, relation: 'main predication', span: sentence }],
          },
          constituents_heuristic: {
            subject_span: null,
            predicate_span: null,
            post_predicate_span: sentence,
          },
          constituents: [],
          morphology: { tokens: [] },
          verb_system: { per_clause: [] },
          meaning_pragmatics: {
            speech_act: 'declarative',
            time_reference: 'Present/General',
            pragmatic_notes: [],
          },
          lexis: {
            register: 'neutral',
            collocations: [],
            semantic_precision: { issues: [], high_precision_signals: [] },
          },
          cefr: { level: 'A1', markers: [] },
        },
        notes: {
          elementary: '',
          intermediate: '',
          advanced: '',
        },
      })),
      contract: JSON.parse(JSON.stringify(samplePayload)) as VisualizerPayload,
      notes_sources: sentenceSource.map(() => 'mock'),
    }
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
