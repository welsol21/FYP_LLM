import 'fake-indexeddb/auto'
import { describe, expect, it, vi } from 'vitest'

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

describe('LocalWorkspace cold-start', () => {
  it('returns consistent project/file/history data on parallel reads after reload', async () => {
    vi.resetModules()
    const { LocalWorkspace } = await import('./localWorkspace')
    await LocalWorkspace.__resetForTests()
    await LocalWorkspace.listProjects()

    const projectId = 'proj-cold'
    const fileId = 'file-cold'
    const documentId = 'doc-cold'
    await overwriteWorkspaceState({
      projects: [
        {
          id: projectId,
          name: 'np1',
          created_at: '2026-04-06T20:00:00.000Z',
          updated_at: '2026-04-06T20:00:00.000Z',
        },
      ],
      selected_project_id: projectId,
      files: [
        {
          id: fileId,
          project_id: projectId,
          name: '01.Intro.mp3',
          media_path: '/client-media/demo/01.Intro.mp3',
          path: '/client-media/demo/01.Intro.mp3',
          size_bytes: 100,
          settings: 'Transl: gpt / Subs: bilingual / Voice: male / Proc: incremental',
          updated: '2026-04-06T20:00:00.000Z',
          created_at: '2026-04-06T20:00:00.000Z',
          analyzed: true,
          document_id: documentId,
        },
      ],
      analyses: [
        {
          analysis_id: documentId,
          document_id: documentId,
          project_id: projectId,
          project_name: 'np1',
          media_file_id: fileId,
          file_name: '01.Intro.mp3',
          file_path: '/client-media/demo/01.Intro.mp3',
          settings: 'Transl: gpt / Subs: bilingual / Voice: male / Proc: incremental',
          updated_at: '2026-04-06T20:00:00.000Z',
          created_at: '2026-04-06T20:00:00.000Z',
          contract_current: true,
          contract: {},
          artifacts: [],
          items_count: 0,
        },
      ],
      translation_config: null,
    })

    vi.resetModules()
    const { LocalWorkspace: ReloadedWorkspace } = await import('./localWorkspace')
    const [projects, selected, files, analyses] = await Promise.all([
      ReloadedWorkspace.listProjects(),
      ReloadedWorkspace.getSelectedProject(),
      ReloadedWorkspace.listFiles(),
      ReloadedWorkspace.listAnalysisHistory(),
    ])

    expect(projects).toHaveLength(1)
    expect(selected.project_id).toBe(projectId)
    expect(files).toHaveLength(1)
    expect(files[0].id).toBe(fileId)
    expect(analyses).toHaveLength(1)
    expect(analyses[0].document_id).toBe(documentId)
  }, 15000)
})
