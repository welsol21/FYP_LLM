import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { AnalysisHistoryRow, VisualizerNode, VisualizerPayload } from '../api/runtimeApi'
import { buildAnalysisFeatureBadges, getTranslationProviderFromSettings } from '../lib/analysisSettings'
import { normalizeLinguisticNotes } from '../lib/linguisticNotes'
import { resolveNodeTranslation } from '../lib/translationContract'

export type VocabRow = {
  id: string
  project: string
  file: string
  items: number
  created: string
  settings: string
  documentId: string | null
  payload: VisualizerPayload | null
  translationProvider: string
}

export type ExportRow = {
  project: string
  file: string
  created: string
  document_id: string
  sentence: string
  node_id: string
  node_type: string
  content: string
  cefr_level: string
  tense: string
  linguistic_notes: string
  translation_provider: string
  translation: string
  translations_json: string
  phonetic_uk: string
  phonetic_us: string
} & Record<string, string>

function toProviderColumn(provider: string): string {
  const normalized = String(provider || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return normalized ? `translation_${normalized}` : 'translation_unknown'
}

function collectLinguisticElements(node: VisualizerNode): VisualizerNode[] {
  const out: VisualizerNode[] = []
  const stack = [...(node.linguistic_elements || [])]
  while (stack.length) {
    const current = stack.shift()
    if (!current) continue
    out.push(current)
    for (const child of current.linguistic_elements || []) stack.push(child)
  }
  return out
}

function countPayloadElements(payload: VisualizerPayload | null): number {
  if (!payload) return 0
  let total = 0
  for (const root of Object.values(payload)) {
    if (!root) continue
    total += collectLinguisticElements(root).length
  }
  return total
}

function formatAnalysisTime(value: string): string {
  const ts = Date.parse(String(value || ''))
  if (!Number.isFinite(ts)) return String(value || '')
  return new Date(ts).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function notesToExportText(node: VisualizerNode): string {
  const notes = normalizeLinguisticNotes(node.linguistic_notes)
  const out: string[] = []
  if (notes.intermediate) out.push(`intermediate: ${notes.intermediate}`)
  if (notes.elementary) out.push(`elementary: ${notes.elementary}`)
  if (notes.advanced) out.push(`advanced: ${notes.advanced}`)
  return out.join(' | ')
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

export function toExportRows(row: VocabRow): ExportRow[] {
  if (!row.payload || !row.documentId) return []
  const out: ExportRow[] = []
  for (const [sentence, root] of Object.entries(row.payload)) {
    const elements = collectLinguisticElements(root)
    for (const node of elements) {
      const exportRow: ExportRow = {
        project: row.project,
        file: row.file,
        created: row.created,
        document_id: row.documentId,
        sentence,
        node_id: String(node.node_id || ''),
        node_type: String(node.type || ''),
        content: String(node.content || ''),
        cefr_level: String(node.cefr_level || ''),
        tense: String(node.tense || ''),
        linguistic_notes: notesToExportText(node),
        translation_provider: row.translationProvider,
        translation: resolveNodeTranslation(node, row.translationProvider),
        translations_json: JSON.stringify(node.translations || {}),
        phonetic_uk: String(node.phonetic?.uk || ''),
        phonetic_us: String(node.phonetic?.us || ''),
      }
      if (node.translations && typeof node.translations === 'object') {
        for (const [provider, payload] of Object.entries(node.translations)) {
          const col = toProviderColumn(provider)
          exportRow[col] = String(payload?.text || '')
        }
      }
      out.push(exportRow)
    }
  }
  return out
}

function downloadTextFile(filename: string, text: string, mimeType: string): void {
  const blob = new Blob([text], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function toCsv(rows: ExportRow[]): string {
  const fallbackHeaders = Object.keys({
    project: '',
    file: '',
    created: '',
    document_id: '',
    sentence: '',
    node_id: '',
    node_type: '',
    content: '',
    cefr_level: '',
    tense: '',
    linguistic_notes: '',
    translation: '',
    translation_provider: '',
    translations_json: '',
    phonetic_uk: '',
    phonetic_us: '',
  })
  const headers = rows.length
    ? Array.from(rows.reduce((set, row) => {
      Object.keys(row).forEach((k) => set.add(k))
      return set
    }, new Set<string>()))
    : fallbackHeaders
  const csvHeaders = headers.filter((h) => h !== 'translations_json')
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const body = rows.map((row) => csvHeaders.map((h) => esc((row as Record<string, unknown>)[h])).join(','))
  return [csvHeaders.join(','), ...body].join('\n')
}

export function VocabularyPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<VocabRow[]>([])
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [deleting, setDeleting] = useState(false)

  const fetchPayloadByDocumentId = useCallback(async (documentId: string): Promise<VisualizerPayload | null> => {
    try {
      return await withRetry(() => api.getVisualizerPayload(documentId), 2, 300)
    } catch {
      return null
    }
  }, [api])

  const enrichRowsWithPayload = useCallback(async (documentIds: string[]) => {
    const unique = Array.from(new Set(documentIds.filter(Boolean)))
    for (const documentId of unique) {
      let shouldFetch = false
      setRows((prev) => {
        const hasPayload = prev.some((row) => row.documentId === documentId && row.payload)
        if (!hasPayload) shouldFetch = true
        return prev
      })
      if (!shouldFetch) continue
      const payload = await fetchPayloadByDocumentId(documentId)
      setRows((prev) => prev.map((row) => (
        row.documentId === documentId
          ? { ...row, payload, items: countPayloadElements(payload) }
          : row
      )))
    }
  }, [fetchPayloadByDocumentId])

  const resolveRowsForExport = useCallback(async (selected: VocabRow[]): Promise<VocabRow[]> => {
    return Promise.all(selected.map(async (row) => {
      if (row.payload || !row.documentId) return row
      const payload = await fetchPayloadByDocumentId(row.documentId)
      return { ...row, payload, items: countPayloadElements(payload) }
    }))
  }, [fetchPayloadByDocumentId])

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      setLoadError('')
      const mapHistoryRow = (row: AnalysisHistoryRow): VocabRow => {
        return {
          id: String(row.analysis_id || row.document_id),
          project: String(row.project_name || row.project_id || '-'),
          file: String(row.file_name || row.media_file_id || row.document_id || 'Unknown'),
          items: 0,
          created: formatAnalysisTime(row.updated_at),
          settings: String(row.settings || ''),
          documentId: row.document_id ?? null,
          payload: null,
          translationProvider: getTranslationProviderFromSettings(row.settings),
        }
      }

      const loadFromHistory = async (): Promise<VocabRow[]> => {
        const history = await withRetry(() => api.listAnalysisHistory(), 5, 600)
        return history.map((row) => mapHistoryRow(row))
      }

      const loadLegacy = async (): Promise<VocabRow[]> => {
        const projects = await withRetry(() => api.listProjects(), 4, 500)
        const grouped = await Promise.all(
          projects.map(async (p) => {
            const files = await withRetry(() => api.listFiles(p.id), 3, 400)
            const analyzed = files.filter((f) => f.analyzed)
            return Promise.all(
              analyzed.map(async (f) => {
                return {
                  id: `${p.id}:${f.id}`,
                  project: p.name,
                  file: f.name,
                  items: 0,
                  created: formatAnalysisTime(f.updated),
                  settings: String(f.settings || ''),
                  documentId: f.document_id ?? null,
                  payload: null,
                  translationProvider: getTranslationProviderFromSettings(f.settings),
                }
              }),
            )
          }),
        )
        return grouped.flat().flat()
      }

      let loaded: VocabRow[] = []
      try {
        loaded = await loadFromHistory()
      } catch {
        try {
          loaded = await loadLegacy()
        } catch {
          loaded = []
          if (alive) setLoadError('Failed to load analysis history. Retry in a few seconds.')
        }
      }
      if (alive) {
        setRows(loaded)
        setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [api])

  useEffect(() => {
    const docIds = Object.entries(checked)
      .filter(([, isChecked]) => isChecked)
      .map(([rowId]) => rows.find((row) => row.id === rowId)?.documentId || '')
      .filter((v): v is string => Boolean(v))
    if (!docIds.length) return
    void enrichRowsWithPayload(docIds)
  }, [checked, rows, enrichRowsWithPayload])

  const selectedCount = useMemo(() => Object.values(checked).filter(Boolean).length, [checked])
  const selectedRows = useMemo(() => rows.filter((row) => checked[row.id]), [rows, checked])
  const selectedDocumentId = selectedRows.find((row) => row.documentId)?.documentId ?? null
  const selectedDocumentIds = useMemo(
    () => Array.from(new Set(selectedRows.map((row) => row.documentId).filter((v): v is string => Boolean(v)))),
    [selectedRows],
  )

  const deleteSelectedAnalyses = useCallback(async () => {
    if (!selectedDocumentIds.length) return
    const shouldDelete = window.confirm(`Delete ${selectedDocumentIds.length} selected analysis artifact set(s)?`)
    if (!shouldDelete) return
    setDeleting(true)
    try {
      const results = await Promise.all(selectedDocumentIds.map(async (docId) => {
        try {
          return await api.deleteAnalysis(docId)
        } catch {
          return { status: 'error' as const, message: 'delete failed', document_id: docId }
        }
      }))
      const deletedIds = new Set(
        results
          .filter((row) => row.status === 'ok')
          .map((row) => String(row.document_id || ''))
          .filter(Boolean),
      )
      if (deletedIds.size > 0) {
        setRows((prev) => prev.filter((row) => !row.documentId || !deletedIds.has(row.documentId)))
        setChecked((prev) => {
          const next: Record<string, boolean> = {}
          for (const row of rows) {
            if (deletedIds.has(String(row.documentId || ''))) continue
            if (prev[row.id]) next[row.id] = true
          }
          return next
        })
      }
      if (deletedIds.size !== selectedDocumentIds.length) {
        setLoadError('Some selected analyses were not deleted. Reload page and retry.')
      }
    } finally {
      setDeleting(false)
    }
  }, [api, rows, selectedDocumentIds])

  return (
    <section className="screen-block">
      <div className="page-head">
        <h2 className="page-title">Vocabulary</h2>
        <div className="actions-row">
          <button
            type="button"
            className="secondary-btn"
            disabled={!selectedDocumentId}
            onClick={() => {
              if (!selectedDocumentId) return
              navigate('/visualizer', {
                state: {
                  documentId: selectedDocumentId,
                  documentIds: selectedDocumentIds,
                  documentMeta: Object.fromEntries(
                    selectedRows
                      .filter((row) => row.documentId)
                      .map((row) => [
                        row.documentId as string,
                        { project: row.project, file: row.file },
                      ]),
                  ),
                },
              })
            }}
          >
            Visualizer
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={selectedCount === 0}
            onClick={async () => {
              const freshRows = await resolveRowsForExport(selectedRows)
              const freshExportRows = freshRows.flatMap((row) => toExportRows(row))
              downloadTextFile(
                `vocabulary_export_${Date.now()}.json`,
                JSON.stringify(freshExportRows, null, 2),
                'application/json;charset=utf-8',
              )
            }}
          >
            Export JSON
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={selectedCount === 0}
            onClick={async () => {
              const freshRows = await resolveRowsForExport(selectedRows)
              const freshExportRows = freshRows.flatMap((row) => toExportRows(row))
              downloadTextFile(`vocabulary_export_${Date.now()}.csv`, toCsv(freshExportRows), 'text/csv;charset=utf-8')
            }}
          >
            Export CSV
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={selectedDocumentIds.length === 0 || deleting}
            onClick={() => {
              void deleteSelectedAnalyses()
            }}
          >
            {deleting ? 'Deleting...' : 'Delete Analyses'}
          </button>
        </div>
      </div>
      {loading ? <p className="muted">Loading analysis history...</p> : null}
      {!loading && loadError ? <p style={{ color: '#ff8a8a' }}>{loadError}</p> : null}
      {!loading && !loadError && rows.length === 0 ? <p className="muted">No analyzed history yet.</p> : null}

      <table>
        <thead>
          <tr>
            <th style={{ width: 36 }} />
            <th>Project</th>
            <th>File</th>
            <th>Settings</th>
            <th>Items</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <input
                  type="checkbox"
                  checked={!!checked[row.id]}
                  onChange={(e) => setChecked((prev) => ({ ...prev, [row.id]: e.target.checked }))}
                />
              </td>
              <td>{row.project}</td>
              <td>{row.file}</td>
              <td>
                <div className="analysis-feature-badges">
                  {buildAnalysisFeatureBadges(row.settings).map((badge) => (
                    <span key={`${row.id}-${badge.key}`} className="badge analysis-feature-badge">
                      {badge.label}: {badge.value}
                    </span>
                  ))}
                </div>
              </td>
              <td>{row.items}</td>
              <td>{row.created}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
