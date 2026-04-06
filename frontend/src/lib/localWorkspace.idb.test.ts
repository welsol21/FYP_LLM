import 'fake-indexeddb/auto'
import { describe, expect, it, vi } from 'vitest'
import type { TranslationConfig } from '../api/runtimeApi'

const DB_NAME = 'ela_frontend_workspace'
const DB_VERSION = 2
const STORE = 'kv_store'
const STATE_KEY = 'workspace_state_v1'

function requestToPromise<T = unknown>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('IndexedDB request failed'))
  })
}

async function withKvStore(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => Promise<void>): Promise<void> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const next = req.result
      if (!next.objectStoreNames.contains(STORE)) next.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error || new Error('Failed to open IndexedDB'))
  })
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, mode)
    const store = tx.objectStore(STORE)
    fn(store).then(() => undefined).catch(reject)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction failed'))
    tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'))
  })
  db.close()
}

async function overwriteWorkspaceState(rawState: unknown): Promise<void> {
  await withKvStore('readwrite', async (store) => {
    await requestToPromise(store.put(JSON.stringify(rawState), STATE_KEY))
  })
}

function sampleConfig(): TranslationConfig {
  return {
    default_provider: 'gpt',
    providers: [
      { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
      { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: true, credential_fields: ['api_key'], credentials: { api_key: 'secret' } },
      { id: 'deepl', label: 'DeepL', kind: 'builtin', enabled: false, credential_fields: ['auth_key'], credentials: { auth_key: '' } },
      { id: 'lara', label: 'Lara', kind: 'builtin', enabled: false, credential_fields: ['api_id', 'api_secret'], credentials: { api_id: '', api_secret: '' } },
      { id: 'original', label: 'Original only (no translation)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
    ],
  }
}

describe('LocalWorkspace IndexedDB translation config', () => {
  it('keeps provider config from dedicated IDB key even if workspace_state has stale config', async () => {
    vi.resetModules()
    const { LocalWorkspace } = await import('./localWorkspace')
    await LocalWorkspace.__resetForTests()
    await LocalWorkspace.listProjects()

    await LocalWorkspace.createProject('np1')
    const cfg = sampleConfig()
    await LocalWorkspace.saveTranslationConfig(cfg)

    await overwriteWorkspaceState({
      projects: [],
      selected_project_id: null,
      files: [],
      analyses: [],
      translation_config: {
        default_provider: 'm2m100',
        providers: [
          { id: 'm2m100', label: 'M2M100', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
          { id: 'gpt', label: 'OpenAI GPT', kind: 'builtin', enabled: false, credential_fields: ['api_key'], credentials: { api_key: '' } },
          { id: 'original', label: 'Original only (no translation)', kind: 'builtin', enabled: true, credential_fields: [], credentials: {} },
        ],
      },
    })

    vi.resetModules()
    const { LocalWorkspace: ReloadedWorkspace } = await import('./localWorkspace')
    const loaded = await ReloadedWorkspace.getTranslationConfig()

    expect(loaded?.default_provider).toBe('gpt')
    expect(loaded?.providers.find((provider) => provider.id === 'gpt')?.enabled).toBe(true)
    expect(loaded?.providers.find((provider) => provider.id === 'gpt')?.credentials.api_key).toBe('secret')
  })

})
