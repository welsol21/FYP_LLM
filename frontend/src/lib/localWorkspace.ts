import type {
  AnalysisHistoryRow,
  DocumentArtifact,
  MediaFileRow,
  ProjectRow,
  SelectedProject,
  TranslationConfig,
  TranslationProviderConfig,
  VisualizerNode,
  VisualizerPayload,
} from '../api/runtimeApi'
import { getTranslationProviderFromSettings } from './analysisSettings'
import { recordRuntimeDiagnostic } from './runtimeDiagnostics'

const IDB_DB_NAME = 'ela_frontend_workspace'
const IDB_DB_VERSION = 2
const IDB_STATE_STORE = 'kv_store'
const IDB_BLOB_STORE = 'blob_store'
const SQLITE_STATE_KEY = 'workspace_state_v1'
const SQLITE_TRANSLATION_CONFIG_KEY = 'translation_config_v1'
const LEGACY_STORAGE_KEY = 'ela_frontend_workspace_v1'

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

function emptyWorkspaceState(): WorkspaceState {
  return {
    projects: [],
    selected_project_id: null,
    files: [],
    analyses: [],
    translation_config: null,
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

function readString(row: Record<string, unknown> | null, keys: string[], fallback = ''): string {
  if (!row) return fallback
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'string' && value.trim()) return value
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return fallback
}

function readNumber(row: Record<string, unknown> | null, keys: string[]): number | undefined {
  if (!row) return undefined
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return undefined
}

function readBoolean(row: Record<string, unknown> | null, keys: string[], fallback = false): boolean {
  if (!row) return fallback
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'boolean') return value
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase()
      if (normalized === 'true') return true
      if (normalized === 'false') return false
    }
    if (typeof value === 'number') {
      if (value === 1) return true
      if (value === 0) return false
    }
  }
  return fallback
}

function normalizeProjectRow(raw: unknown): ProjectRow | null {
  const row = asRecord(raw)
  if (!row) return null
  const id = readString(row, ['id', 'project_id', 'projectId']).trim()
  const name = readString(row, ['name', 'project_name', 'projectName']).trim()
  if (!id || !name) return null
  const createdAt = readString(row, ['created_at', 'createdAt', 'updated_at', 'updatedAt'], nowIso())
  const updatedAt = readString(row, ['updated_at', 'updatedAt', 'created_at', 'createdAt'], createdAt)
  return {
    id,
    name,
    created_at: createdAt,
    updated_at: updatedAt,
  }
}

function normalizeFileRow(raw: unknown): WorkspaceFile | null {
  const row = asRecord(raw)
  if (!row) return null
  const id = readString(row, ['id', 'file_id', 'fileId']).trim()
  const name = readString(row, ['name', 'file_name', 'fileName']).trim()
  const mediaPath = readString(row, ['media_path', 'mediaPath', 'path', 'file_path', 'filePath']).trim()
  if (!id || !name || !mediaPath) return null
  const updated = readString(row, ['updated', 'updated_at', 'updatedAt', 'created_at', 'createdAt'], nowIso())
  const createdAt = readString(row, ['created_at', 'createdAt', 'updated', 'updated_at', 'updatedAt'], updated)
  const documentId = readString(row, ['document_id', 'documentId']).trim()
  const settings = readString(row, ['settings'], normalizeSettings(undefined))
  const projectId = readString(row, ['project_id', 'projectId']).trim()
  const analyzed = readBoolean(row, ['analyzed'], Boolean(documentId))
  return {
    id,
    project_id: projectId,
    name,
    path: mediaPath,
    media_path: mediaPath,
    size_bytes: readNumber(row, ['size_bytes', 'sizeBytes']),
    duration_seconds: readNumber(row, ['duration_seconds', 'durationSec', 'durationSeconds']),
    settings: normalizeSettings(settings),
    updated,
    created_at: createdAt,
    analyzed,
    document_id: documentId || undefined,
  }
}

function normalizeAnalysisRow(raw: unknown): WorkspaceAnalysis | null {
  const row = asRecord(raw)
  if (!row) return null
  const documentId = readString(row, ['document_id', 'documentId', 'analysis_id', 'analysisId']).trim()
  const analysisId = readString(row, ['analysis_id', 'analysisId', 'document_id', 'documentId'], documentId).trim()
  const fileName = readString(row, ['file_name', 'fileName', 'name']).trim()
  if (!documentId || !analysisId || !fileName) return null
  const rawContract = row.contract ?? row.visualizer_payload ?? row.visualizerPayload ?? row.analysis_contract ?? row.analysisContract
  const contract = asRecord(rawContract) ? (clone(rawContract) as VisualizerPayload) : {}
  const contractCurrent = readBoolean(row, ['contract_current', 'contractCurrent'], true)
  const updatedAt = readString(row, ['updated_at', 'updatedAt', 'created_at', 'createdAt'], nowIso())
  const createdAt = readString(row, ['created_at', 'createdAt', 'updated_at', 'updatedAt'], updatedAt)
  const itemsCount = readNumber(row, ['items_count', 'itemsCount'])
  const rawArtifacts = row.artifacts ?? row.document_artifacts ?? row.documentArtifacts
  const artifacts = Array.isArray(rawArtifacts) ? clone(rawArtifacts as DocumentArtifact[]) : []
  return {
    analysis_id: analysisId,
    document_id: documentId,
    project_id: readString(row, ['project_id', 'projectId']).trim(),
    project_name: readString(row, ['project_name', 'projectName']).trim(),
    media_file_id: readString(row, ['media_file_id', 'mediaFileId', 'file_id', 'fileId']).trim() || null,
    file_name: fileName,
    file_path: readString(row, ['file_path', 'filePath', 'path']).trim(),
    size_bytes: readNumber(row, ['size_bytes', 'sizeBytes']),
    duration_seconds: readNumber(row, ['duration_seconds', 'durationSeconds', 'durationSec']),
    settings: normalizeSettings(readString(row, ['settings'], normalizeSettings(undefined))),
    items_count: typeof itemsCount === 'number' ? itemsCount : (contractCurrent ? countContractNodes(contract) : 0),
    updated_at: updatedAt,
    created_at: createdAt,
    contract_current: contractCurrent,
    contract,
    artifacts,
  }
}

function normalizeTranslationConfig(raw: unknown): TranslationConfig | null {
  const row = asRecord(raw)
  if (!row) return null
  const rawProviders = Array.isArray(row.providers) ? row.providers : []
  const customProviders: TranslationProviderConfig[] = rawProviders
    .map((item) => {
      const p = asRecord(item)
      if (!p) return null
      const id = readString(p, ['id']).trim()
      if (!id) return null
      const credentialFields = Array.isArray(p.credential_fields)
        ? p.credential_fields
        : (Array.isArray(p.credentialFields) ? p.credentialFields : [])
      const normalizedCredentialFields = credentialFields
        .map((value) => String(value || '').trim())
        .filter(Boolean)
      const credentialsRow = asRecord(p.credentials) || {}
      const credentials: Record<string, string> = {}
      for (const field of normalizedCredentialFields) {
        credentials[field] = String(credentialsRow[field] || '')
      }
      return {
        id,
        label: readString(p, ['label'], id),
        kind: readString(p, ['kind'], 'custom'),
        enabled: readBoolean(p, ['enabled'], true),
        credential_fields: normalizedCredentialFields,
        credentials,
      } satisfies TranslationProviderConfig
    })
    .filter((value): value is TranslationProviderConfig => Boolean(value))

  const byId = new Map(customProviders.map((provider) => [provider.id, provider]))
  const mergedProviders: TranslationProviderConfig[] = DEFAULT_TRANSLATION_CONFIG.providers.map((builtin) => {
    const next = byId.get(builtin.id)
    if (!next) return clone(builtin)
    const credentials: Record<string, string> = { ...builtin.credentials, ...(next.credentials || {}) }
    return {
      ...builtin,
      label: next.label || builtin.label,
      kind: next.kind || builtin.kind,
      enabled: Boolean(next.enabled),
      credential_fields: next.credential_fields.length > 0 ? next.credential_fields : builtin.credential_fields,
      credentials,
    }
  })
  for (const provider of customProviders) {
    if (DEFAULT_TRANSLATION_CONFIG.providers.some((builtin) => builtin.id === provider.id)) continue
    mergedProviders.push(provider)
  }
  const requestedDefault = readString(row, ['default_provider', 'defaultProvider'], 'm2m100').trim()
  const fallbackDefault = mergedProviders.find((provider) => provider.enabled)?.id || 'm2m100'
  const defaultProvider = mergedProviders.some((provider) => provider.id === requestedDefault)
    ? requestedDefault
    : fallbackDefault
  return {
    default_provider: defaultProvider,
    providers: mergedProviders,
  }
}

function sanitizeTranslationConfig(config: TranslationConfig | null | undefined): TranslationConfig {
  return normalizeTranslationConfig(config) || clone(DEFAULT_TRANSLATION_CONFIG)
}

function repairProjectLinks(state: WorkspaceState): boolean {
  const projectsById = new Map(state.projects.map((project) => [project.id, project]))
  const projectIdByName = new Map(
    state.projects
      .map((project) => [normalizeProjectName(project.name), project.id] as const)
      .filter(([name]) => Boolean(name)),
  )
  const singleProjectId = state.projects.length === 1 ? state.projects[0].id : ''
  let changed = false

  for (const analysis of state.analyses) {
    let nextProjectId = String(analysis.project_id || '').trim()
    if (!nextProjectId || !projectsById.has(nextProjectId)) {
      const byName = projectIdByName.get(normalizeProjectName(String(analysis.project_name || '')))
      if (byName) nextProjectId = byName
    }
    if ((!nextProjectId || !projectsById.has(nextProjectId)) && analysis.media_file_id) {
      const byFileId = state.files.find((file) => String(file.id || '').trim() === String(analysis.media_file_id || '').trim())
      const candidate = String(byFileId?.project_id || '').trim()
      if (candidate && projectsById.has(candidate)) nextProjectId = candidate
    }
    if ((!nextProjectId || !projectsById.has(nextProjectId)) && (analysis.file_path || analysis.file_name)) {
      const byFile = state.files.find((file) => matchAnalysisToFile(file, analysis))
      const candidate = String(byFile?.project_id || '').trim()
      if (candidate && projectsById.has(candidate)) nextProjectId = candidate
    }
    if ((!nextProjectId || !projectsById.has(nextProjectId)) && state.selected_project_id && projectsById.has(state.selected_project_id)) {
      nextProjectId = state.selected_project_id
    }
    if ((!nextProjectId || !projectsById.has(nextProjectId)) && singleProjectId) {
      nextProjectId = singleProjectId
    }
    if (nextProjectId && nextProjectId !== analysis.project_id) {
      analysis.project_id = nextProjectId
      changed = true
    }
    const expectedName = projectsById.get(nextProjectId)?.name || ''
    if (expectedName && expectedName !== analysis.project_name) {
      analysis.project_name = expectedName
      changed = true
    }
  }

  for (const file of state.files) {
    let nextProjectId = String(file.project_id || '').trim()
    if (!nextProjectId || !projectsById.has(nextProjectId)) {
      const byAnalysis = state.analyses.find((analysis) => matchAnalysisToFile(file, analysis))
      const candidate = String(byAnalysis?.project_id || '').trim()
      if (candidate && projectsById.has(candidate)) nextProjectId = candidate
    }
    if ((!nextProjectId || !projectsById.has(nextProjectId)) && state.selected_project_id && projectsById.has(state.selected_project_id)) {
      nextProjectId = state.selected_project_id
    }
    if ((!nextProjectId || !projectsById.has(nextProjectId)) && singleProjectId) {
      nextProjectId = singleProjectId
    }
    if (nextProjectId && nextProjectId !== file.project_id) {
      file.project_id = nextProjectId
      changed = true
    }
  }

  return changed
}

function coerceWorkspaceState(parsed: Partial<WorkspaceState> | null | undefined): WorkspaceState {
  const root = asRecord(parsed)
  const selectedProjectId = readString(root, ['selected_project_id', 'selectedProjectId']).trim() || null
  const rawProjects = Array.isArray(root?.projects) ? root.projects : []
  const projects = rawProjects
    .map((item) => normalizeProjectRow(item))
    .filter((item): item is ProjectRow => Boolean(item))
  const projectsById = new Map(projects.map((project) => [project.id, project]))
  const firstProjectId = projects[0]?.id || ''
  const rawFiles = Array.isArray(root?.files) ? root.files : []
  const files = rawFiles
    .map((item) => normalizeFileRow(item))
    .filter((item): item is WorkspaceFile => Boolean(item))
  const rawAnalyses = Array.isArray(root?.analyses)
    ? root.analyses
    : (Array.isArray(root?.analysis_history) ? root.analysis_history : [])
  const analyses = rawAnalyses
    .map((item) => normalizeAnalysisRow(item))
    .filter((item): item is WorkspaceAnalysis => Boolean(item))

  // Recover missing project links from related rows or singleton project setups.
  for (const analysis of analyses) {
    if (!analysis.project_id) {
      const linkedFile = files.find((file) => {
        const fileId = String(file.id || '').trim()
        const filePath = String(file.path || '').trim()
        const fileName = String(file.name || '').trim().toLowerCase()
        const analysisFileId = String(analysis.media_file_id || '').trim()
        const analysisFilePath = String(analysis.file_path || '').trim()
        const analysisFileName = String(analysis.file_name || '').trim().toLowerCase()
        if (analysisFileId && fileId && analysisFileId === fileId) return true
        if (analysisFilePath && filePath && analysisFilePath === filePath) return true
        return Boolean(analysisFileName && fileName && analysisFileName === fileName)
      })
      analysis.project_id = String(linkedFile?.project_id || '').trim()
    }
    if (!analysis.project_id && selectedProjectId) analysis.project_id = selectedProjectId
    if (!analysis.project_id && firstProjectId) analysis.project_id = firstProjectId
    if (!analysis.project_name) {
      analysis.project_name = projectsById.get(analysis.project_id)?.name || ''
    }
  }

  for (const file of files) {
    if (!file.project_id) {
      const linked = analyses.find((analysis) => {
        const fileId = String(file.id || '').trim()
        const filePath = String(file.path || '').trim()
        const fileName = String(file.name || '').trim().toLowerCase()
        const analysisFileId = String(analysis.media_file_id || '').trim()
        const analysisFilePath = String(analysis.file_path || '').trim()
        const analysisFileName = String(analysis.file_name || '').trim().toLowerCase()
        if (analysisFileId && fileId && analysisFileId === fileId) return true
        if (analysisFilePath && filePath && analysisFilePath === filePath) return true
        return Boolean(analysisFileName && fileName && analysisFileName === fileName)
      })
      file.project_id = String(linked?.project_id || '').trim()
    }
    if (!file.project_id && selectedProjectId) file.project_id = selectedProjectId
    if (!file.project_id && firstProjectId) file.project_id = firstProjectId
  }

  const normalizedSelected = selectedProjectId && projects.some((project) => project.id === selectedProjectId)
    ? selectedProjectId
    : (projects[0]?.id || null)

  const state: WorkspaceState = {
    projects,
    selected_project_id: normalizedSelected,
    files,
    analyses,
    translation_config: normalizeTranslationConfig(root?.translation_config ?? root?.translationConfig),
  }
  repairProjectLinks(state)
  return state
}

function nowIso(): string {
  return new Date().toISOString()
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

type BlobRecord = {
  key: string
  mime_type: string
  size_bytes: number
  data_blob: Blob
  updated_at: string
}

let idbPromise: Promise<IDBDatabase | null> | null = null
let memoryState: WorkspaceState = emptyWorkspaceState()
let memoryBlobs = new Map<string, BlobRecord>()
let stateStoreWriteQueue: Promise<void> = Promise.resolve()
let dbReadyPromise: Promise<void> | null = null
let dbReady = false

function hasIndexedDb(): boolean {
  return typeof indexedDB !== 'undefined'
}

function idbErrorDetails(error: unknown): { name: string; message: string } {
  if (error instanceof DOMException || error instanceof Error) {
    return { name: String(error.name || 'Error'), message: String(error.message || 'Unknown IndexedDB error') }
  }
  return { name: 'UnknownError', message: String(error || 'Unknown IndexedDB error') }
}

function openIndexedDb(): Promise<IDBDatabase | null> {
  if (!hasIndexedDb()) return Promise.resolve(null)
  if (!idbPromise) {
    recordRuntimeDiagnostic('workspace.idb', 'open.start')
    idbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(IDB_DB_NAME, IDB_DB_VERSION)
      req.onupgradeneeded = () => {
        const db = req.result
        if (!db.objectStoreNames.contains(IDB_STATE_STORE)) db.createObjectStore(IDB_STATE_STORE)
        if (!db.objectStoreNames.contains(IDB_BLOB_STORE)) db.createObjectStore(IDB_BLOB_STORE, { keyPath: 'key' })
        recordRuntimeDiagnostic('workspace.idb', 'open.upgrade', { version: IDB_DB_VERSION })
      }
      req.onsuccess = () => {
        recordRuntimeDiagnostic('workspace.idb', 'open.success')
        resolve(req.result)
      }
      req.onerror = () => {
        recordRuntimeDiagnostic('workspace.idb', 'open.error', idbErrorDetails(req.error), 'error')
        reject(req.error || new Error('Failed to open IndexedDB'))
      }
    })
  }
  return idbPromise
}

async function withStore<T>(
  storeName: string,
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => void | Promise<T>,
): Promise<T | undefined> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const db = await openIndexedDb()
    if (!db) return undefined
    if (!db.objectStoreNames.contains(storeName)) {
      recordRuntimeDiagnostic('workspace.idb', 'store.missing', { storeName, mode, version: db.version, attempt }, 'error')
      db.close()
      idbPromise = null
      if (attempt === 0) continue
      throw new Error(`IndexedDB store is missing: ${storeName}`)
    }
    try {
      return await new Promise<T>((resolve, reject) => {
        const tx = db.transaction(storeName, mode)
        const store = tx.objectStore(storeName)
        let fnResult: T | undefined
        let fnFailed = false

        tx.oncomplete = () => {
          if (fnFailed) return
          resolve(fnResult as T)
        }
        tx.onerror = () => {
          recordRuntimeDiagnostic(
            'workspace.idb',
            'tx.error',
            { storeName, mode, ...idbErrorDetails(tx.error) },
            'error',
          )
          reject(tx.error || new Error('IndexedDB transaction failed'))
        }
        tx.onabort = () => {
          recordRuntimeDiagnostic(
            'workspace.idb',
            'tx.abort',
            { storeName, mode, ...idbErrorDetails(tx.error) },
            'error',
          )
          reject(tx.error || new Error('IndexedDB transaction aborted'))
        }

        Promise.resolve(fn(store))
          .then((value) => {
            fnResult = value as T | undefined
          })
          .catch((error) => {
            fnFailed = true
            try {
              tx.abort()
            } catch {
              // ignore abort errors and reject with original error
            }
            reject(error)
          })
      })
    } catch (error) {
      if (attempt === 0 && error instanceof DOMException && error.name === 'NotFoundError') {
        recordRuntimeDiagnostic('workspace.idb', 'tx.retry_missing_store', { storeName, mode }, 'error')
        db.close()
        idbPromise = null
        continue
      }
      throw error
    }
  }
  return undefined
}

function queueStateStoreWrite<T>(task: () => Promise<T>): Promise<T> {
  const run = stateStoreWriteQueue.then(task, task)
  stateStoreWriteQueue = run.then(() => undefined, () => undefined)
  return run
}

function requestToPromise<T = unknown>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => {
      recordRuntimeDiagnostic('workspace.idb', 'request.error', idbErrorDetails(request.error), 'error')
      reject(request.error || new Error('IndexedDB request failed'))
    }
  })
}

async function idbGetState(): Promise<WorkspaceState> {
  const value = await withStore<string | undefined>(IDB_STATE_STORE, 'readonly', async (store) => {
    return await requestToPromise(store.get(SQLITE_STATE_KEY))
  })
  if (typeof value !== 'string' || !value) {
    const cfgOnly = await idbGetTranslationConfig()
    if (cfgOnly) {
      const fallback = clone(memoryState)
      fallback.translation_config = clone(cfgOnly)
      return fallback
    }
    return clone(memoryState)
  }
  try {
    const coerced = coerceWorkspaceState(JSON.parse(value) as Partial<WorkspaceState>)
    const configFromKey = await idbGetTranslationConfig()
    if (configFromKey) {
      coerced.translation_config = clone(configFromKey)
      return coerced
    }
    if (coerced.translation_config) {
      // One-time migration from legacy embedded state payload to dedicated key.
      try {
        await idbPutTranslationConfig(coerced.translation_config)
      } catch (err) {
        recordRuntimeDiagnostic('workspace.translation_config', 'migrate_to_dedicated_key_failed', err, 'error')
      }
    }
    return coerced
  } catch {
    return emptyWorkspaceState()
  }
}

async function idbPutState(state: WorkspaceState): Promise<void> {
  const snapshot = clone(state)
  const persisted = { ...snapshot, translation_config: null }
  await queueStateStoreWrite(async () => {
    await withStore(IDB_STATE_STORE, 'readwrite', async (store) => {
      await requestToPromise(store.put(JSON.stringify(persisted), SQLITE_STATE_KEY))
    })
  })
  memoryState = snapshot
}

async function idbGetTranslationConfig(): Promise<TranslationConfig | null> {
  const value = await withStore<string | undefined>(IDB_STATE_STORE, 'readonly', async (store) => {
    return await requestToPromise(store.get(SQLITE_TRANSLATION_CONFIG_KEY))
  })
  if (typeof value !== 'string' || !value) return null
  try {
    return sanitizeTranslationConfig(JSON.parse(value) as TranslationConfig)
  } catch {
    return null
  }
}

async function idbPutTranslationConfig(config: TranslationConfig): Promise<void> {
  const snapshot = sanitizeTranslationConfig(config)
  await queueStateStoreWrite(async () => {
    await withStore(IDB_STATE_STORE, 'readwrite', async (store) => {
      await requestToPromise(store.put(JSON.stringify(snapshot), SQLITE_TRANSLATION_CONFIG_KEY))
    })
  })
}

async function idbPutBlob(key: string, blob: Blob): Promise<void> {
  const record: BlobRecord = {
    key,
    mime_type: String(blob.type || 'application/octet-stream'),
    size_bytes: blob.size,
    data_blob: blob,
    updated_at: nowIso(),
  }
  await withStore(IDB_BLOB_STORE, 'readwrite', async (store) => {
    await requestToPromise(store.put(record))
  })
  // IndexedDB is the source of truth in modern browsers. Keeping large blobs
  // in the in-memory fallback map duplicates RAM usage and can crash mobile tabs.
  memoryBlobs.delete(key)
}

async function idbGetBlobRecord(key: string): Promise<BlobRecord | null> {
  const record = await withStore<BlobRecord | undefined>(IDB_BLOB_STORE, 'readonly', async (store) => {
    return await requestToPromise(store.get(key))
  })
  if (record) return record
  return memoryBlobs.get(key) || null
}

async function sqlitePutBlob(key: string, blob: Blob): Promise<void> {
  if (!key || !(blob instanceof Blob)) return
  if (!hasIndexedDb()) {
    memoryBlobs.set(key, {
      key,
      mime_type: String(blob.type || 'application/octet-stream'),
      size_bytes: blob.size,
      data_blob: blob,
      updated_at: nowIso(),
    })
    return
  }
  await idbPutBlob(key, blob)
}

async function sqliteGetBlob(key: string): Promise<Blob | null> {
  if (!key) return null
  if (!hasIndexedDb()) return memoryBlobs.get(key)?.data_blob || null
  return (await idbGetBlobRecord(key))?.data_blob || null
}

async function sqliteDeleteBlob(key: string): Promise<void> {
  memoryBlobs.delete(key)
  if (!hasIndexedDb()) return
  await withStore(IDB_BLOB_STORE, 'readwrite', async (store) => {
    await requestToPromise(store.delete(key))
  })
}

async function sqliteDeleteBlobPrefix(prefix: string): Promise<void> {
  const safe = String(prefix || '').trim()
  if (!safe) return
  for (const key of [...memoryBlobs.keys()]) {
    if (key.startsWith(safe)) memoryBlobs.delete(key)
  }
  if (!hasIndexedDb()) return
  await withStore(IDB_BLOB_STORE, 'readwrite', async (store) => {
    const keys = await requestToPromise(store.getAllKeys())
    await Promise.all(
      keys
        .map((value) => String(value || ''))
        .filter((key) => key.startsWith(safe))
        .map((key) => requestToPromise(store.delete(key))),
    )
  })
}

async function sqliteFindBlobByKeySuffix(suffix: string): Promise<{ key: string; blob: Blob } | null> {
  if (!suffix) return null
  if (!hasIndexedDb()) {
    for (const [key, record] of memoryBlobs.entries()) {
      if (key.endsWith(suffix)) return { key, blob: record.data_blob }
    }
    return null
  }
  const rows = await withStore<BlobRecord[]>(IDB_BLOB_STORE, 'readonly', async (store) => {
    return await requestToPromise(store.getAll())
  }) || []
  for (const row of rows) {
    const key = String(row?.key || '')
    if (!key.endsWith(suffix)) continue
    if (!(row?.data_blob instanceof Blob)) continue
    return { key, blob: row.data_blob }
  }
  return null
}

async function resetIndexedDb(): Promise<void> {
  memoryState = emptyWorkspaceState()
  memoryBlobs = new Map<string, BlobRecord>()
  const openDb = await openIndexedDb()
  if (openDb) {
    openDb.close()
  }
  idbPromise = null
  stateStoreWriteQueue = Promise.resolve()
  dbReadyPromise = null
  dbReady = false
  if (!hasIndexedDb()) return
  await new Promise<void>((resolve, reject) => {
    const req = indexedDB.deleteDatabase(IDB_DB_NAME)
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error || new Error('Failed to delete IndexedDB database'))
    req.onblocked = () => resolve()
  })
}

function analysisArtifactKey(documentId: string, artifactName: string): string {
  return `analysis_artifact:${String(documentId || '').trim()}:${String(artifactName || '').trim()}`
}

async function ensureDbReady(): Promise<void> {
  if (dbReady) return
  if (dbReadyPromise) {
    await dbReadyPromise
    return
  }
  dbReadyPromise = (async () => {
    const legacyRaw = String(window.localStorage.getItem(LEGACY_STORAGE_KEY) || '')
    if (!hasIndexedDb()) {
      if (legacyRaw) {
        try {
          memoryState = coerceWorkspaceState(JSON.parse(legacyRaw) as Partial<WorkspaceState>)
        } catch {
          memoryState = emptyWorkspaceState()
        }
        window.localStorage.removeItem(LEGACY_STORAGE_KEY)
      }
      dbReady = true
      return
    }
    await openIndexedDb()
    const state = await idbGetState()
    const isEmpty =
      state.projects.length === 0 &&
      state.files.length === 0 &&
      state.analyses.length === 0 &&
      !state.translation_config &&
      !state.selected_project_id
    if (isEmpty && legacyRaw) {
      try {
        const migrated = coerceWorkspaceState(JSON.parse(legacyRaw) as Partial<WorkspaceState>)
        await idbPutState(migrated)
        if (migrated.translation_config) {
          try {
            await idbPutTranslationConfig(migrated.translation_config)
          } catch (err) {
            recordRuntimeDiagnostic('workspace.translation_config', 'legacy_migration_persist_failed', err, 'error')
          }
        }
        memoryState = clone(migrated)
        window.localStorage.removeItem(LEGACY_STORAGE_KEY)
      } catch {
        memoryState = state
      }
    } else {
      memoryState = state
    }
    dbReady = true
  })()
  try {
    await dbReadyPromise
  } finally {
    dbReadyPromise = null
  }
}

async function ensureDbFresh(): Promise<void> {
  return
}

async function loadRawState(): Promise<WorkspaceState> {
  await ensureDbReady()
  await ensureDbFresh()
  // ensureDbReady() loads memoryState from IndexedDB on first call; all writes
  // go through saveRawState() which keeps memoryState current.
  // Re-reading from IDB on every call is unnecessary and very slow on WebKitGTK.
  //
  // We do a SHALLOW clone of the state: scalar fields and lightweight arrays are
  // copied, but analysis contracts (large VisualizerPayload objects) are kept as
  // shared references. This is safe because:
  //   - read-only callers never mutate contract objects;
  //   - applyEdit() mutates in-place but immediately calls saveRawState() which
  //     replaces memoryState with a full deep-clone of the modified state;
  //   - upsertAnalysis() always replaces the entire analysis entry with a fresh clone.
  const m = memoryState
  return {
    projects: m.projects.map((p) => ({ ...p })),
    selected_project_id: m.selected_project_id,
    files: m.files.map((f) => ({ ...f })),
    analyses: m.analyses.map((a) => ({ ...a })),
    translation_config: m.translation_config
      ? {
          ...m.translation_config,
          providers: m.translation_config.providers.map((p) => ({
            ...p,
            credentials: { ...p.credentials },
          })),
        }
      : null,
  }
}

async function saveRawState(state: WorkspaceState): Promise<void> {
  const snapshot = clone(state)
  await ensureDbReady()
  await ensureDbFresh()
  if (!hasIndexedDb()) {
    memoryState = snapshot
    return
  }
  await idbPutState(snapshot)
}

async function ensureState(): Promise<WorkspaceState> {
  const state = await loadRawState()
  const fileFlagsBefore = state.files
    .map((file) => `${file.id}|${file.analyzed ? 1 : 0}|${String(file.document_id || '')}|${String(file.settings || '')}`)
    .join('||')
  syncFileAnalysisFlags(state)
  const fileFlagsAfter = state.files
    .map((file) => `${file.id}|${file.analyzed ? 1 : 0}|${String(file.document_id || '')}|${String(file.settings || '')}`)
    .join('||')
  const hasSelected = Boolean(state.selected_project_id && state.projects.some((p) => p.id === state.selected_project_id))
  const nextSelected = hasSelected ? state.selected_project_id : (state.projects[0]?.id || null)
  const linksFixed = repairProjectLinks(state)
  if (state.selected_project_id !== nextSelected || fileFlagsBefore !== fileFlagsAfter || linksFixed) {
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

function matchAnalysisToAnalysis(target: WorkspaceAnalysis, candidate: WorkspaceAnalysis): boolean {
  if (target.project_id !== candidate.project_id) return false
  const targetFileId = String(target.media_file_id || '').trim()
  const candidateFileId = String(candidate.media_file_id || '').trim()
  if (targetFileId && candidateFileId && targetFileId === candidateFileId) return true
  const targetPath = String(target.file_path || '').trim()
  const candidatePath = String(candidate.file_path || '').trim()
  if (targetPath && candidatePath && targetPath === candidatePath) return true
  const targetName = String(target.file_name || '').trim().toLowerCase()
  const candidateName = String(candidate.file_name || '').trim().toLowerCase()
  return Boolean(targetName && candidateName && targetName === candidateName)
}

function normalizeProviderKey(value: string | undefined): string {
  const raw = String(value || '').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_')
  return raw || ''
}

function analysisProviderOf(row: WorkspaceAnalysis): string {
  const fromSettings = normalizeProviderKey(getTranslationProviderFromSettings(row.settings || '', 'm2m100'))
  if (fromSettings) return fromSettings
  const firstNode = Object.values(row.contract || {})[0]
  const active = normalizeProviderKey(firstNode?.active_translation_provider)
  if (active) return active
  const firstKey = firstNode?.translations && typeof firstNode.translations === 'object'
    ? normalizeProviderKey(Object.keys(firstNode.translations)[0])
    : ''
  return firstKey || 'm2m100'
}

function buildNodeIndex(root: VisualizerNode): Map<string, VisualizerNode> {
  const out = new Map<string, VisualizerNode>()
  const stack: VisualizerNode[] = [root]
  while (stack.length > 0) {
    const node = stack.pop() as VisualizerNode
    out.set(String(node.node_id || ''), node)
    for (const child of node.linguistic_elements || []) stack.push(child)
  }
  return out
}

function pickTranslationRowForProvider(
  node: VisualizerNode,
  provider: string,
): { text: string; source_lang?: string; target_lang?: string; created_at?: string; origin?: string } | null {
  const translations = node.translations || {}
  for (const [key, row] of Object.entries(translations)) {
    if (normalizeProviderKey(key) !== provider) continue
    if (row && String(row.text || '').trim()) return row
  }
  const active = normalizeProviderKey(node.active_translation_provider)
  if (active === provider) {
    const first = Object.values(translations).find((row) => String(row?.text || '').trim())
    if (first) return first
  }
  return null
}

function enrichContractTranslationsFromAnalyses(
  baseContract: VisualizerPayload,
  baseRow: WorkspaceAnalysis,
  analyses: WorkspaceAnalysis[],
): VisualizerPayload {
  const enriched = clone(baseContract)
  const providerSeen = new Set<string>()
  for (const sentenceNode of Object.values(enriched)) {
    const active = normalizeProviderKey(sentenceNode.active_translation_provider)
    if (active) providerSeen.add(active)
  }

  const related = analyses
    .filter((row) => row.document_id !== baseRow.document_id)
    .filter((row) => row.contract_current !== false)
    .filter((row) => matchAnalysisToAnalysis(baseRow, row))
    .sort((a, b) => Date.parse(String(b.updated_at || '')) - Date.parse(String(a.updated_at || '')))

  for (const relatedRow of related) {
    const provider = analysisProviderOf(relatedRow)
    if (!provider || providerSeen.has(provider)) continue
    let addedAny = false
    for (const [sentenceText, baseSentenceNode] of Object.entries(enriched)) {
      const relatedSentenceNode = relatedRow.contract[sentenceText]
      if (!relatedSentenceNode) continue
      const baseIndex = buildNodeIndex(baseSentenceNode)
      const relatedIndex = buildNodeIndex(relatedSentenceNode)
      for (const [nodeId, targetNode] of baseIndex.entries()) {
        const sourceNode = relatedIndex.get(nodeId)
        if (!sourceNode) continue
        const picked = pickTranslationRowForProvider(sourceNode, provider)
        if (!picked || !String(picked.text || '').trim()) continue
        if (!targetNode.translations || typeof targetNode.translations !== 'object') {
          targetNode.translations = {}
        }
        if (!targetNode.translations[provider] || !String(targetNode.translations[provider].text || '').trim()) {
          targetNode.translations[provider] = {
            text: String(picked.text || '').trim(),
            source_lang: picked.source_lang || 'en',
            target_lang: picked.target_lang || 'ru',
            created_at: picked.created_at,
            origin: picked.origin || 'provider',
          }
          addedAny = true
        }
      }
    }
    if (addedAny) providerSeen.add(provider)
  }

  return enriched
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
    const latestContract = matches.find((analysis) => analysis.contract_current !== false)
    if (!latestContract) {
      file.analyzed = false
      file.document_id = undefined
      file.settings = normalizeSettings(latest.settings)
      continue
    }
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
  const entries = Object.entries(contract).sort((a, b) => {
    const aIdx = typeof a[1]?.sentence_idx === 'number' ? a[1].sentence_idx : Number.MAX_SAFE_INTEGER
    const bIdx = typeof b[1]?.sentence_idx === 'number' ? b[1].sentence_idx : Number.MAX_SAFE_INTEGER
    if (aIdx !== bIdx) return aIdx - bIdx
    return a[0].localeCompare(b[0])
  })
  const out: MediaSentenceArtifactRow[] = []
  for (let idx = 0; idx < entries.length; idx += 1) {
    const [sentenceText, sentenceNode] = entries[idx]
    const resolvedSentenceText = String(sentenceNode?.content || sentenceText || '').trim()
    const startMs = idx * 3000
    const endMs = startMs + 2600
    const textRu = pickNodeTranslation(sentenceNode)
    out.push({
      sentence_idx: typeof sentenceNode?.sentence_idx === 'number' ? sentenceNode.sentence_idx : idx,
      sentence_text: resolvedSentenceText,
      sentence_hash: String(sentenceNode?.sentence_hash || simpleHash(`${idx}:${resolvedSentenceText}`)),
      text_eng: resolvedSentenceText,
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
  const orderedEntries = Object.entries(contract).sort((a, b) => {
    const aIdx = typeof a[1]?.sentence_idx === 'number' ? a[1].sentence_idx : Number.MAX_SAFE_INTEGER
    const bIdx = typeof b[1]?.sentence_idx === 'number' ? b[1].sentence_idx : Number.MAX_SAFE_INTEGER
    if (aIdx !== bIdx) return aIdx - bIdx
    return a[0].localeCompare(b[0])
  })
  const mediaSentences = buildArtifactRowsFromContract(contract)
  const fullText = mediaSentences.map((row) => row.sentence_text).join(' ')
  const contractJson = JSON.stringify(contract, null, 2)
  const contractSentences = orderedEntries.map(([sentenceText, sentenceNode]) => ({
    sentence_text: String(sentenceNode?.content || sentenceText || '').trim(),
    sentence_node: sentenceNode,
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
    await resetIndexedDb()
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
    recordRuntimeDiagnostic('workspace.project', 'create.start', { name })
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
    recordRuntimeDiagnostic('workspace.project', 'create.success', project)
    return clone(project)
  },

  async deleteProject(projectId: string): Promise<{ status: 'ok' | 'error'; message: string; project_id?: string }> {
    recordRuntimeDiagnostic('workspace.project', 'delete.start', { projectId })
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

    const result = { status: 'ok', message: 'Project and all related data deleted.', project_id: id } as const
    recordRuntimeDiagnostic('workspace.project', 'delete.success', result)
    return result
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
    recordRuntimeDiagnostic('workspace.file', 'register.start', input)
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
    recordRuntimeDiagnostic('workspace.file', 'register.success', { id: file.id, name: file.name, path: file.path })
    return clone(file)
  },

  async getFileById(fileId: string): Promise<WorkspaceFile | null> {
    const state = await ensureState()
    const row = state.files.find((f) => f.id === fileId)
    return row ? clone(row) : null
  },

  async listFiles(projectId?: string): Promise<MediaFileRow[]> {
    const state = await ensureState()
    return state.files
      .filter((f) => !projectId || f.project_id === projectId)
      .sort((a, b) => String(b.updated).localeCompare(String(a.updated)))
      .map((f) => ({ ...f }))
  },

  async deleteFile(fileId: string): Promise<{ status: 'ok' | 'error'; message: string; file_id?: string }> {
    recordRuntimeDiagnostic('workspace.file', 'delete.start', { fileId })
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
    const result = { status: 'ok', message: 'File deleted.', file_id: id } as const
    recordRuntimeDiagnostic('workspace.file', 'delete.success', result)
    return result
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
    recordRuntimeDiagnostic('workspace.analysis', 'upsert.start', {
      documentId: input.documentId,
      fileName: input.fileName,
      contractCurrent: input.contractCurrent !== false,
      artifacts: Array.isArray(input.artifacts) ? input.artifacts.length : 0,
    })
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
    recordRuntimeDiagnostic('workspace.analysis', 'upsert.success', {
      documentId: row.document_id,
      items: row.items_count,
      contractCurrent: row.contract_current,
    })
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
      .filter((a) => (!projectId || a.project_id === projectId) && a.contract_current !== false)
      .sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)))
      .map((row) => {
        const { contract: _contract, artifacts: _artifacts, ...rest } = row
        return rest
      })
    return clone(rows)
  },

  async updateAnalysisTranslations(documentId: string, translations: Record<string, string>): Promise<void> {
    const docId = String(documentId || '').trim()
    if (!docId) return
    const state = await ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    if (!row) return
    const contract: VisualizerPayload = clone(row.contract || {})
    for (const [sentenceText, translatedText] of Object.entries(translations)) {
      const node = contract[sentenceText]
      if (!node) continue
      node.translations = { ...(node.translations || {}), client: { text: translatedText } }
      node.active_translation_provider = 'client'
    }
    row.contract = contract
    row.artifacts = buildContractArtifacts(docId, contract)
    row.updated_at = nowIso()
    await saveRawState(state)
  },

  async getVisualizerPayload(documentId?: string): Promise<VisualizerPayload> {
    const docId = String(documentId || '').trim()
    if (!docId) return {}
    const state = await ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    if (row?.contract_current === false) return {}
    if (!row) return {}
    const payload = enrichContractTranslationsFromAnalyses(row.contract || {}, row, state.analyses)
    recordRuntimeDiagnostic('workspace.visualizer', 'payload.loaded', {
      documentId: docId,
      sentences: Object.keys(payload || {}).length,
    })
    return payload
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

  async getRawAnalysis(documentId: string): Promise<WorkspaceAnalysis | null> {
    const docId = String(documentId || '').trim()
    if (!docId) return null
    const state = await ensureState()
    const row = state.analyses.find((a) => a.document_id === docId || a.analysis_id === docId)
    return row ? clone(row) : null
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
    await ensureDbReady()
    await ensureDbFresh()
    const cfgFromIdb = hasIndexedDb() ? await idbGetTranslationConfig() : null
    let cfg = cfgFromIdb
    if (!cfg) cfg = sanitizeTranslationConfig(memoryState.translation_config)
    // One-time migration: remove the 'hf' provider that was dropped in favour of 'm2m100'.
    if (cfg.providers.some((p) => p.id === 'hf')) {
      cfg.providers = cfg.providers.filter((p) => p.id !== 'hf')
      if (cfg.default_provider === 'hf') cfg.default_provider = 'm2m100'
    }
    const currentMemory = sanitizeTranslationConfig(memoryState.translation_config)
    const changed = JSON.stringify(currentMemory) !== JSON.stringify(cfg)
    if (changed) {
      memoryState.translation_config = clone(cfg)
    }
    if (hasIndexedDb() && (changed || !cfgFromIdb)) {
      try {
        await idbPutTranslationConfig(cfg)
      } catch (err) {
        recordRuntimeDiagnostic('workspace.translation_config', 'persist_dedicated_key_failed', err, 'error')
      }
    }
    return clone(cfg)
  },

  async saveTranslationConfig(config: TranslationConfig): Promise<TranslationConfig> {
    await ensureDbReady()
    await ensureDbFresh()
    const cfg = sanitizeTranslationConfig(config)
    if (hasIndexedDb()) {
      await idbPutTranslationConfig(cfg)
    }
    memoryState.translation_config = clone(cfg)
    return clone(cfg)
  },
}
