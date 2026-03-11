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
import initSqlJs from 'sql.js'
import sqlWasmUrl from 'sql.js/dist/sql-wasm.wasm?url'

const STORAGE_KEY = 'ela_frontend_workspace_sqlite_b64_v1'
const OPFS_DB_FILE = 'ela_frontend_workspace.sqlite'
const SQLITE_STATE_KEY = 'workspace_state_v1'
const LEGACY_STORAGE_KEY = 'ela_frontend_workspace_v1'
const SQLITE_MEDIA_TABLE = 'media_blob_store'

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

function emptyWorkspaceState(): WorkspaceState {
  return {
    projects: [],
    selected_project_id: null,
    files: [],
    analyses: [],
    translation_config: null,
  }
}

function coerceWorkspaceState(parsed: Partial<WorkspaceState> | null | undefined): WorkspaceState {
  const state: WorkspaceState = {
    projects: Array.isArray(parsed?.projects) ? parsed?.projects : [],
    selected_project_id: typeof parsed?.selected_project_id === 'string' ? parsed.selected_project_id : null,
    files: Array.isArray(parsed?.files) ? parsed?.files : [],
    analyses: Array.isArray(parsed?.analyses) ? parsed?.analyses : [],
    translation_config: parsed?.translation_config ?? null,
  }
  return state
}

function nowIso(): string {
  return new Date().toISOString()
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i])
  return window.btoa(binary)
}

function base64ToBytes(value: string): Uint8Array {
  const binary = window.atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

type SqlDatabase = {
  run: (sql: string, params?: unknown[] | Record<string, unknown>) => void
  exec: (sql: string, params?: unknown[] | Record<string, unknown>) => Array<{ columns: string[]; values: unknown[][] }>
  export: () => Uint8Array
  close: () => void
}

type SqlModule = {
  Database: new (data?: Uint8Array) => SqlDatabase
}

let sqlModule: SqlModule | null = null
let sqliteInitPromise: Promise<void> | null = null
let sqliteDb: SqlDatabase | null = null

function openDbFromSnapshot(snapshot?: Uint8Array | null): SqlDatabase {
  if (!sqlModule) throw new Error('SQLite module not initialized')
  const db = snapshot && snapshot.byteLength > 0 ? new sqlModule.Database(snapshot) : new sqlModule.Database()
  db.run('CREATE TABLE IF NOT EXISTS kv_store (k TEXT PRIMARY KEY, v TEXT NOT NULL)')
  db.run(`
    CREATE TABLE IF NOT EXISTS ${SQLITE_MEDIA_TABLE} (
      k TEXT PRIMARY KEY,
      mime_type TEXT NOT NULL,
      size_bytes INTEGER NOT NULL,
      data_b64 TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
  `)
  return db
}

async function getWorkspaceDirectory(): Promise<FileSystemDirectoryHandle | null> {
  const storage = (navigator as Navigator & {
    storage?: StorageManager & { getDirectory?: () => Promise<FileSystemDirectoryHandle> }
  }).storage
  if (!storage || typeof storage.getDirectory !== 'function') return null
  try {
    return await storage.getDirectory()
  } catch {
    return null
  }
}

async function readPersistedSnapshot(): Promise<Uint8Array | null> {
  const dir = await getWorkspaceDirectory()
  if (dir) {
    try {
      const handle = await dir.getFileHandle(OPFS_DB_FILE, { create: false })
      const file = await handle.getFile()
      const buffer = await file.arrayBuffer()
      return new Uint8Array(buffer)
    } catch {
      // fallback below
    }
  }
  const encoded = String(window.localStorage.getItem(STORAGE_KEY) || '')
  return encoded ? base64ToBytes(encoded) : null
}

async function writePersistedSnapshot(bytes: Uint8Array): Promise<void> {
  const dir = await getWorkspaceDirectory()
  if (dir) {
    const handle = await dir.getFileHandle(OPFS_DB_FILE, { create: true })
    const writable = await handle.createWritable()
    await writable.write(toArrayBuffer(bytes))
    await writable.close()
    window.localStorage.removeItem(STORAGE_KEY)
    return
  }
  window.localStorage.setItem(STORAGE_KEY, bytesToBase64(bytes))
}

async function clearPersistedSnapshot(): Promise<void> {
  const dir = await getWorkspaceDirectory()
  if (dir) {
    try {
      await dir.removeEntry(OPFS_DB_FILE)
    } catch {
      // ignore
    }
  }
  window.localStorage.removeItem(STORAGE_KEY)
}

function readCell(rows: Array<{ values: unknown[][] }>, rowIndex = 0, colIndex = 0): unknown {
  return rows?.[0]?.values?.[rowIndex]?.[colIndex]
}

async function persistDbSnapshot(): Promise<void> {
  const exported = sqliteDb?.export() || new Uint8Array()
  await writePersistedSnapshot(exported)
}

async function sqlitePutBlob(key: string, blob: Blob): Promise<void> {
  await ensureDbReady()
  await ensureDbFresh()
  const arrayBuffer = typeof (blob as Blob & { arrayBuffer?: () => Promise<ArrayBuffer> }).arrayBuffer === 'function'
    ? await (blob as Blob & { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer()
    : await new Response(blob).arrayBuffer()
  const bytes = new Uint8Array(arrayBuffer)
  sqliteDb?.run(
    `INSERT OR REPLACE INTO ${SQLITE_MEDIA_TABLE} (k, mime_type, size_bytes, data_b64, updated_at) VALUES (?, ?, ?, ?, ?)`,
    [key, String(blob.type || 'application/octet-stream'), bytes.length, bytesToBase64(bytes), nowIso()],
  )
  await persistDbSnapshot()
}

async function sqliteGetBlob(key: string): Promise<Blob | null> {
  await ensureDbReady()
  await ensureDbFresh()
  const rows = sqliteDb?.exec(`SELECT mime_type, data_b64 FROM ${SQLITE_MEDIA_TABLE} WHERE k = ? LIMIT 1`, [key]) || []
  const mimeType = String(readCell(rows, 0, 0) || '')
  const dataB64 = String(readCell(rows, 0, 1) || '')
  if (!dataB64) return null
  const bytes = base64ToBytes(dataB64)
  return new Blob([toArrayBuffer(bytes)], { type: mimeType || 'application/octet-stream' })
}

async function sqliteDeleteBlob(key: string): Promise<void> {
  await ensureDbReady()
  await ensureDbFresh()
  sqliteDb?.run(`DELETE FROM ${SQLITE_MEDIA_TABLE} WHERE k = ?`, [key])
  await persistDbSnapshot()
}

async function sqliteDeleteBlobPrefix(prefix: string): Promise<void> {
  const safe = String(prefix || '').trim()
  if (!safe) return
  await ensureDbReady()
  await ensureDbFresh()
  sqliteDb?.run(`DELETE FROM ${SQLITE_MEDIA_TABLE} WHERE k LIKE ?`, [`${safe}%`])
  await persistDbSnapshot()
}

async function sqliteFindBlobByKeySuffix(suffix: string): Promise<{ key: string; blob: Blob } | null> {
  if (!suffix) return null
  await ensureDbReady()
  await ensureDbFresh()
  const rows = sqliteDb?.exec(`SELECT k, mime_type, data_b64 FROM ${SQLITE_MEDIA_TABLE}`) || []
  const values = rows?.[0]?.values || []
  for (const row of values) {
    const key = String(row?.[0] || '')
    if (!key.endsWith(suffix)) continue
    const mimeType = String(row?.[1] || '')
    const dataB64 = String(row?.[2] || '')
    if (!dataB64) continue
    const bytes = base64ToBytes(dataB64)
    return {
      key,
      blob: new Blob([toArrayBuffer(bytes)], { type: mimeType || 'application/octet-stream' }),
    }
  }
  return null
}

function analysisArtifactKey(documentId: string, artifactName: string): string {
  return `analysis_artifact:${String(documentId || '').trim()}:${String(artifactName || '').trim()}`
}

async function ensureDbReady(): Promise<void> {
  if (!sqliteInitPromise) {
    sqliteInitPromise = (async () => {
      sqlModule = (await initSqlJs({
        locateFile: () => {
          const candidate = String(sqlWasmUrl || 'sql-wasm.wasm')
          if (typeof process !== 'undefined' && process?.versions?.node && candidate.startsWith('/node_modules/')) {
            return `${process.cwd()}${candidate}`
          }
          return candidate
        },
      })) as unknown as SqlModule
      const snapshot = await readPersistedSnapshot()
      sqliteDb = openDbFromSnapshot(snapshot)

      // One-time migration from legacy JSON workspace to SQLite snapshot.
      if (!snapshot || snapshot.byteLength === 0) {
        const legacyRaw = String(window.localStorage.getItem(LEGACY_STORAGE_KEY) || '')
        if (legacyRaw) {
          try {
            const parsed = JSON.parse(legacyRaw) as Partial<WorkspaceState>
            const migrated = coerceWorkspaceState(parsed)
            sqliteDb.run('INSERT OR REPLACE INTO kv_store (k, v) VALUES (?, ?)', [SQLITE_STATE_KEY, JSON.stringify(migrated)])
            await persistDbSnapshot()
            window.localStorage.removeItem(LEGACY_STORAGE_KEY)
          } catch {
            // ignore invalid legacy data
          }
        }
      }
    })()
  }
  await sqliteInitPromise
}

async function ensureDbFresh(): Promise<void> {
  return
}

async function loadRawState(): Promise<WorkspaceState> {
  const empty = emptyWorkspaceState()
  try {
    await ensureDbReady()
    await ensureDbFresh()
    const rows = sqliteDb?.exec('SELECT v FROM kv_store WHERE k = ?', [SQLITE_STATE_KEY]) || []
    const raw = rows?.[0]?.values?.[0]?.[0]
    if (typeof raw !== 'string' || !raw) return empty
    const parsed = JSON.parse(raw) as Partial<WorkspaceState>
    return coerceWorkspaceState(parsed)
  } catch {
    return empty
  }
}

async function saveRawState(state: WorkspaceState): Promise<void> {
  await ensureDbReady()
  await ensureDbFresh()
  const payload = JSON.stringify(state)
  sqliteDb?.run('INSERT OR REPLACE INTO kv_store (k, v) VALUES (?, ?)', [SQLITE_STATE_KEY, payload])
  await persistDbSnapshot()
}

async function ensureState(): Promise<WorkspaceState> {
  const state = await loadRawState()
  const hasSelected = Boolean(state.selected_project_id && state.projects.some((p) => p.id === state.selected_project_id))
  const nextSelected = hasSelected ? state.selected_project_id : (state.projects[0]?.id || null)
  if (state.selected_project_id !== nextSelected) {
    state.selected_project_id = nextSelected
    await saveRawState(state)
  }
  return state
}

function pickProject(state: WorkspaceState, projectId?: string): ProjectRow | null {
  const requested = String(projectId || '').trim()
  const found = requested ? state.projects.find((p) => p.id === requested) : null
  return found || state.projects.find((p) => p.id === state.selected_project_id) || state.projects[0] || null
}

function normalizeSettings(settings: string | undefined): string {
  return String(settings || '').trim() || 'Transl: m2m100 / Subs: bilingual / Voice: male / Proc: incremental'
}

function normalizeProjectName(name: string): string {
  return String(name || '')
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase()
}

function countContractNodes(contract: VisualizerPayload): number {
  let total = 0
  const roots = Object.values(contract || {})
  const stack: VisualizerNode[] = roots.filter(Boolean) as VisualizerNode[]
  while (stack.length > 0) {
    const node = stack.pop() as VisualizerNode
    for (const child of node.linguistic_elements || []) {
      total += 1
      stack.push(child)
    }
  }
  return total
}

function matchAnalysisToFile(file: WorkspaceFile, analysis: WorkspaceAnalysis): boolean {
  const fileId = String(file.id || '').trim()
  const filePath = String(file.path || '').trim()
  const fileName = String(file.name || '').trim().toLowerCase()
  const analysisFileId = String(analysis.media_file_id || '').trim()
  const analysisFilePath = String(analysis.file_path || '').trim()
  const analysisFileName = String(analysis.file_name || '').trim().toLowerCase()
  if (analysisFileId && fileId && analysisFileId === fileId) return true
  if (analysisFilePath && filePath && analysisFilePath === filePath) return true
  return Boolean(analysisFileName && fileName && analysisFileName === fileName)
}

function syncFileAnalysisFlags(state: WorkspaceState): void {
  for (const file of state.files) {
    const matches = state.analyses
      .filter((analysis) => analysis.project_id === file.project_id)
      .filter((analysis) => matchAnalysisToFile(file, analysis))
      .sort((a, b) => Date.parse(String(b.updated_at || '')) - Date.parse(String(a.updated_at || '')))
    if (matches.length === 0) {
      file.analyzed = false
      file.document_id = undefined
      continue
    }
    const latest = matches[0]
    if (latest.contract_current === false) {
      file.analyzed = false
      file.document_id = undefined
      file.settings = normalizeSettings(latest.settings)
      continue
    }
    const latestContract = matches.find((analysis) => analysis.contract_current !== false) || latest
    file.analyzed = true
    file.document_id = String(latestContract.document_id || '').trim() || undefined
    file.settings = normalizeSettings(latestContract.settings)
  }
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

type MediaSentenceArtifactRow = {
  sentence_idx: number
  sentence_text: string
  sentence_hash: string
  text_eng: string
  text_ru: string
  start: number
  end: number
  start_ms: number
  end_ms: number
  units: unknown[]
  units_ru: unknown[]
}

function encodeTextArtifact(mime: string, text: string): string {
  return `data:${mime};charset=utf-8,${encodeURIComponent(text)}`
}

function bytesOfText(text: string): number {
  return new TextEncoder().encode(text).length
}

function encodeBinaryArtifact(mime: string, bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i])
  return `data:${mime};base64,${window.btoa(binary)}`
}

async function encodeBlobArtifact(blob: Blob): Promise<string> {
  const urlApi = globalThis.URL as { createObjectURL?: (value: Blob) => string }
  if (typeof urlApi?.createObjectURL === 'function') {
    return urlApi.createObjectURL(blob)
  }
  const arrayBuffer = typeof (blob as Blob & { arrayBuffer?: () => Promise<ArrayBuffer> }).arrayBuffer === 'function'
    ? await (blob as Blob & { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer()
    : await new Response(blob).arrayBuffer()
  return encodeBinaryArtifact(blob.type || 'application/octet-stream', new Uint8Array(arrayBuffer))
}

function formatSrtTime(ms: number): string {
  const safe = Math.max(0, Math.floor(ms))
  const hours = Math.floor(safe / 3600000)
  const minutes = Math.floor((safe % 3600000) / 60000)
  const seconds = Math.floor((safe % 60000) / 1000)
  const millis = safe % 1000
  const pad = (v: number, len: number): string => String(v).padStart(len, '0')
  return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(seconds, 2)},${pad(millis, 3)}`
}

function buildSrt(rows: Array<{ start_ms: number; end_ms: number; text_eng: string; text_ru: string }>, bilingual: boolean): string {
  const blocks = rows
    .map((row, idx) => {
      const lines = bilingual
        ? [String(row.text_eng || '').trim(), String(row.text_ru || '').trim()].filter(Boolean)
        : [String(row.text_eng || '').trim()].filter(Boolean)
      if (lines.length === 0) return ''
      return [
        String(idx + 1),
        `${formatSrtTime(row.start_ms)} --> ${formatSrtTime(Math.max(row.end_ms, row.start_ms + 800))}`,
        ...lines,
        '',
      ].join('\n')
    })
    .filter(Boolean)
  return blocks.join('\n')
}

function pickNodeTranslation(node: VisualizerNode): string {
  const preferred = String(node.active_translation_provider || '').trim()
  const translations = node.translations || {}
  if (preferred && translations[preferred]?.text) {
    return String(translations[preferred].text || '').trim()
  }
  const first = Object.values(translations).find((row) => String(row?.text || '').trim())
  return String(first?.text || '').trim()
}

function simpleHash(input: string): string {
  let h = 2166136261
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return `h${(h >>> 0).toString(16)}`
}

function buildArtifactRowsFromContract(contract: VisualizerPayload): MediaSentenceArtifactRow[] {
  const entries = Object.entries(contract)
  const out: MediaSentenceArtifactRow[] = []
  for (let idx = 0; idx < entries.length; idx += 1) {
    const [sentenceText, sentenceNode] = entries[idx]
    const startMs = idx * 3000
    const endMs = startMs + 2600
    const textRu = pickNodeTranslation(sentenceNode)
    out.push({
      sentence_idx: idx,
      sentence_text: sentenceText,
      sentence_hash: simpleHash(`${idx}:${sentenceText}`),
      text_eng: sentenceText,
      text_ru: textRu,
      start: startMs / 1000,
      end: endMs / 1000,
      start_ms: startMs,
      end_ms: endMs,
      units: [],
      units_ru: [],
    })
  }
  return out
}

function buildContractArtifacts(documentId: string, contract: VisualizerPayload): DocumentArtifact[] {
  const mediaSentences = buildArtifactRowsFromContract(contract)
  const fullText = mediaSentences.map((row) => row.sentence_text).join(' ')
  const contractJson = JSON.stringify(contract, null, 2)
  const contractSentences = mediaSentences.map((row) => ({
    sentence_text: row.sentence_text,
    sentence_node: contract[row.sentence_text],
  }))
  const mediaContract = {
    document_id: documentId,
    source_type: 'audio',
    source_path: '',
    text_hash: simpleHash(fullText),
    media_sentences: mediaSentences,
  }
  const legacySegments = mediaSentences.map((row) => ({
    id: row.sentence_idx + 1,
    text_eng: row.text_eng,
    units: row.units,
    start: row.start,
    end: row.end,
    text_ru: row.text_ru,
    units_ru: row.units_ru,
  }))
  const addText = (name: string, mime: string, text: string): DocumentArtifact => ({
    name,
    size_bytes: bytesOfText(text),
    download_url: encodeTextArtifact(mime, text),
  })

  const artifacts: DocumentArtifact[] = [
    addText('full_text.txt', 'text/plain', fullText),
    addText('contract_visualizer.json', 'application/json', contractJson),
    addText('contract_sentences.json', 'application/json', JSON.stringify(contractSentences, null, 2)),
    addText('media_contract.json', 'application/json', JSON.stringify(mediaContract, null, 2)),
    addText('semantic_units_runtime.json', 'application/json', JSON.stringify(legacySegments, null, 2)),
    addText('bilingual_objects_runtime.json', 'application/json', JSON.stringify(legacySegments, null, 2)),
    addText('subtitles_en.srt', 'application/x-subrip', buildSrt(mediaSentences, false)),
    addText('subtitles_bilingual.srt', 'application/x-subrip', buildSrt(mediaSentences, true)),
    addText(
      'subtitles_target.srt',
      'application/x-subrip',
      buildSrt(mediaSentences.map((row) => ({ ...row, text_eng: '' })), true),
    ),
  ]

  return artifacts
}

export const LocalWorkspace = {
  async __resetForTests(): Promise<void> {
    if (sqliteDb) {
      try {
        sqliteDb.close()
      } catch {
        // ignore
      }
    }
    sqliteDb = null
    sqliteInitPromise = null
    sqlModule = null
    await clearPersistedSnapshot()
    window.localStorage.removeItem(LEGACY_STORAGE_KEY)
  },

  async cacheUploadedMedia(mediaPath: string, file: Blob): Promise<void> {
    const key = String(mediaPath || '').trim()
    if (!key || !(file instanceof Blob)) return
    await sqlitePutBlob(`media_path:${key}`, file)
  },

  async getCachedUploadedMedia(mediaPath: string): Promise<Blob | null> {
    const key = String(mediaPath || '').trim()
    if (!key) return null
    const blob = await sqliteGetBlob(`media_path:${key}`)
    if (blob instanceof Blob) return blob
    const fileName = key.split('/').pop() || ''
    if (!fileName) return null
    const fallback = await sqliteFindBlobByKeySuffix(`/${fileName}`)
    if (!fallback?.blob) return null
    if (fallback.key !== `media_path:${key}`) {
      await sqlitePutBlob(`media_path:${key}`, fallback.blob)
    }
    return fallback.blob
  },

  async cacheAnalysisArtifactBlob(documentId: string, artifactName: string, blob: Blob): Promise<void> {
    const docId = String(documentId || '').trim()
    const name = String(artifactName || '').trim()
    if (!docId || !name || !(blob instanceof Blob)) return
    await sqlitePutBlob(analysisArtifactKey(docId, name), blob)
  },

  async getAnalysisArtifactBlob(documentId: string, artifactName: string): Promise<Blob | null> {
    const docId = String(documentId || '').trim()
    const name = String(artifactName || '').trim()
    if (!docId || !name) return null
    return await sqliteGetBlob(analysisArtifactKey(docId, name))
  },

  async clearAnalysisArtifactBlobs(documentId: string): Promise<void> {
    const docId = String(documentId || '').trim()
    if (!docId) return
    await sqliteDeleteBlobPrefix(`analysis_artifact:${docId}:`)
  },

  buildDocumentArtifacts(documentId: string, contract: VisualizerPayload): DocumentArtifact[] {
    return buildContractArtifacts(String(documentId || '').trim(), contract)
  },

  async listProjects(): Promise<ProjectRow[]> {
    const state = await ensureState()
    return clone([...state.projects].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))))
  },

  async createProject(name: string): Promise<ProjectRow> {
    const state = await ensureState()
    const trimmed = String(name || '').trim().replace(/\s+/g, ' ')
    if (!trimmed) {
      throw new Error('Project name is required.')
    }
    const normalized = normalizeProjectName(trimmed)
    const duplicate = state.projects.some((row) => normalizeProjectName(row.name) === normalized)
    if (duplicate) {
      throw new Error('Project with this name already exists.')
    }
    const ts = nowIso()
    const project: ProjectRow = {
      id: `proj-${Math.random().toString(36).slice(2, 10)}`,
      name: trimmed,
      created_at: ts,
      updated_at: ts,
    }
    state.projects.unshift(project)
    state.selected_project_id = project.id
    await saveRawState(state)
    return clone(project)
  },

  async deleteProject(projectId: string): Promise<{ status: 'ok' | 'error'; message: string; project_id?: string }> {
    const state = await ensureState()
    const id = String(projectId || '').trim()
    if (!id) return { status: 'error', message: 'project id is required' }
    const project = state.projects.find((row) => row.id === id)
    if (!project) return { status: 'error', message: 'project not found', project_id: id }

    const removedFiles = state.files.filter((row) => row.project_id === id)
    const removedPaths = new Set(
      removedFiles
        .map((row) => String(row.media_path || row.path || '').trim())
        .filter(Boolean),
    )

    const removedAnalyses = state.analyses.filter((row) => row.project_id === id)
    state.files = state.files.filter((row) => row.project_id !== id)
    state.analyses = state.analyses.filter((row) => row.project_id !== id)
    state.projects = state.projects.filter((row) => row.id !== id)

    if (state.projects.length === 0) {
      state.selected_project_id = null
    } else if (!state.selected_project_id || state.selected_project_id === id || !state.projects.some((p) => p.id === state.selected_project_id)) {
      state.selected_project_id = state.projects[0].id
    }

    syncFileAnalysisFlags(state)
    await saveRawState(state)

    const stillUsedPaths = new Set(
      state.files
        .map((row) => String(row.media_path || row.path || '').trim())
        .filter(Boolean),
    )
    for (const mediaPath of removedPaths) {
      if (stillUsedPaths.has(mediaPath)) continue
      await sqliteDeleteBlob(`media_path:${mediaPath}`)
    }
    for (const row of removedAnalyses) {
      await sqliteDeleteBlobPrefix(`analysis_artifact:${String(row.document_id || '').trim()}:`)
    }

    return { status: 'ok', message: 'Project and all related data deleted.', project_id: id }
  },

  async getSelectedProject(): Promise<SelectedProject> {
    const state = await ensureState()
    const row = state.projects.find((p) => p.id === state.selected_project_id) || state.projects[0]
    return { project_id: row?.id || null, project_name: row?.name }
  },

  async setSelectedProject(projectId: string): Promise<SelectedProject> {
    const state = await ensureState()
    const row = state.projects.find((p) => p.id === projectId)
    if (!row) return { project_id: null }
    state.selected_project_id = row.id
    await saveRawState(state)
    return { project_id: row.id, project_name: row.name }
  },

  async registerMediaFile(input: {
    projectId: string
    name: string
    mediaPath: string
    sizeBytes: number
    durationSec?: number
  }): Promise<WorkspaceFile> {
    const state = await ensureState()
    const project = pickProject(state, input.projectId)
    if (!project) throw new Error('Project is required to register media file.')
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
    await saveRawState(state)
    return clone(file)
  },

  async getFileById(fileId: string): Promise<WorkspaceFile | null> {
    const state = await ensureState()
    const row = state.files.find((f) => f.id === fileId)
    return row ? clone(row) : null
  },

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    const state = await ensureState()
    const rows = state.files
      .filter((f) => !projectId || f.project_id === projectId)
      .sort((a, b) => String(b.updated).localeCompare(String(a.updated)))
    return clone(rows)
  },

  async deleteFile(fileId: string): Promise<{ status: 'ok' | 'error'; message: string; file_id?: string }> {
    const state = await ensureState()
    const id = String(fileId || '').trim()
    if (!id) return { status: 'error', message: 'file id is required' }
    const file = state.files.find((row) => row.id === id)
    if (!file) return { status: 'error', message: 'file not found', file_id: id }
    const removedAnalyses = state.analyses.filter((row) => row.media_file_id === id)
    state.files = state.files.filter((row) => row.id !== id)
    state.analyses = state.analyses.filter((row) => row.media_file_id !== id)
    syncFileAnalysisFlags(state)
    await saveRawState(state)
    const mediaPath = String(file.media_path || file.path || '').trim()
    if (mediaPath) await sqliteDeleteBlob(`media_path:${mediaPath}`)
    for (const row of removedAnalyses) {
      await sqliteDeleteBlobPrefix(`analysis_artifact:${String(row.document_id || '').trim()}:`)
    }
    return { status: 'ok', message: 'File deleted.', file_id: id }
  },

  async upsertAnalysis(input: {
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
    contractCurrent?: boolean
  }): Promise<AnalysisHistoryRow> {
    const state = await ensureState()
    const ts = nowIso()
    const project = pickProject(state, input.projectId)
    if (!project) throw new Error('Project is required to save analysis.')
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
      items_count: input.contractCurrent === false ? 0 : countContractNodes(input.contract),
      updated_at: ts,
      created_at: existing ? existing.created_at : ts,
      contract_current: input.contractCurrent !== false,
      contract: clone(input.contract),
      artifacts: clone(input.artifacts || existing?.artifacts || []),
    }
    if (existingIdx >= 0) state.analyses[existingIdx] = row
    else state.analyses.unshift(row)
    if (input.mediaFileId) {
      const file = state.files.find((f) => f.id === input.mediaFileId)
      if (file) file.updated = ts
    }
    syncFileAnalysisFlags(state)
    const projectRow = state.projects.find((p) => p.id === project.id)
    if (projectRow) projectRow.updated_at = ts
    await saveRawState(state)
    return clone(row)
  },

  async listAnalysisHistory(projectId?: string): Promise<AnalysisHistoryRow[]> {
    const state = await ensureState()
    let needsPersist = false
    for (const row of state.analyses) {
      if (typeof row.items_count === 'number') continue
      row.items_count = countContractNodes(row.contract)
      needsPersist = true
    }
    if (needsPersist) {
      await saveRawState(state)
    }
    const rows = state.analyses
      .filter((a) => !projectId || a.project_id === projectId)
      .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
      .map((row) => {
        const { contract: _contract, artifacts: _artifacts, ...rest } = row
        return rest
      })
    return clone(rows)
  },

  async getVisualizerPayload(documentId?: string): Promise<VisualizerPayload> {
    const docId = String(documentId || '').trim()
    if (!docId) return {}
    const state = await ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    if (row?.contract_current === false) return {}
    return clone(row?.contract || {})
  },

  async applyEdit(input: {
    documentId: string
    sentenceText: string
    nodeId: string
    fieldPath: string
    newValue: unknown
  }): Promise<{ status: 'ok' | 'error'; message: string }> {
    const state = await ensureState()
    const row = state.analyses.find((a) => a.document_id === input.documentId || a.analysis_id === input.documentId)
    if (!row) return { status: 'error', message: 'Analysis not found.' }
    const sentenceNode = row.contract[input.sentenceText]
    if (!sentenceNode) return { status: 'error', message: 'Sentence not found.' }
    const node = findNodeById(sentenceNode, input.nodeId)
    if (!node) return { status: 'error', message: 'node_id not found.' }
    const ok = setByPath(node, input.fieldPath, input.newValue)
    if (!ok) return { status: 'error', message: `Invalid field path: ${input.fieldPath}` }
    row.updated_at = nowIso()
    await saveRawState(state)
    return { status: 'ok', message: 'Edit applied.' }
  },

  async deleteAnalysis(documentId: string): Promise<{ status: 'ok' | 'error'; message: string; document_id?: string }> {
    const state = await ensureState()
    const docId = String(documentId || '').trim()
    const before = state.analyses.length
    state.analyses = state.analyses.filter((a) => a.document_id !== docId && a.analysis_id !== docId)
    const deleted = before !== state.analyses.length
    if (!deleted) return { status: 'error', message: 'analysis not found', document_id: docId }
    syncFileAnalysisFlags(state)
    await saveRawState(state)
    await sqliteDeleteBlobPrefix(`analysis_artifact:${docId}:`)
    return { status: 'ok', message: 'Analysis artifacts deleted.', document_id: docId }
  },

  async listDocumentArtifacts(documentId: string): Promise<DocumentArtifact[]> {
    const docId = String(documentId || '').trim()
    if (!docId) return []
    const state = await ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    if (!row) return []
    const baseArtifacts = Array.isArray(row.artifacts) && row.artifacts.length > 0
      ? row.artifacts.filter((item) => (
          item?.name !== 'translated_audio_ru.mp3' &&
          item?.name !== 'translated_video_ru.mp4' &&
          item?.name !== 'sentence_link.json' &&
          item?.name !== 'stage_manifest.json'
        ))
      : buildContractArtifacts(docId, row.contract)
    const out = [...clone(baseArtifacts)]
    const translatedAudio = await sqliteGetBlob(analysisArtifactKey(docId, 'translated_audio_ru.mp3'))
    if (translatedAudio) {
      out.push({
        name: 'translated_audio_ru.mp3',
        size_bytes: translatedAudio.size,
        download_url: await encodeBlobArtifact(translatedAudio),
      })
    }
    const translatedVideo = await sqliteGetBlob(analysisArtifactKey(docId, 'translated_video_ru.mp4'))
    if (translatedVideo) {
      out.push({
        name: 'translated_video_ru.mp4',
        size_bytes: translatedVideo.size,
        download_url: await encodeBlobArtifact(translatedVideo),
      })
    }
    return out
  },

  async getTranslationConfig(): Promise<TranslationConfig | null> {
    const state = await ensureState()
    return state.translation_config ? clone(state.translation_config) : clone(DEFAULT_TRANSLATION_CONFIG)
  },

  async saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig> {
    const state = await ensureState()
    state.translation_config = clone(config)
    await saveRawState(state)
    return clone(config)
  },
}
