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
  content: string
  translation: string
  translation_provider: string
  phonetic_uk: string
  phonetic_us: string
  cefr_level: string
  tense: string
  project_file: string
  created_document_id: string
  project: string
  file: string
  created: string
  document_id: string
  sentence: string
  node_id: string
  node_type: string
  linguistic_notes: string
  translations_json: string
}

type ExportFormat = 'json' | 'csv'

const DEFAULT_EXPORT_FIELDS: Array<keyof ExportRow> = [
  'content',
  'translation',
  'translation_provider',
  'phonetic_uk',
  'phonetic_us',
  'cefr_level',
  'tense',
  'project_file',
  'created',
  'created_document_id',
]

const EXPORT_FIELD_OPTIONS: Array<{ key: keyof ExportRow; label: string }> = [
  { key: 'content', label: 'content' },
  { key: 'translation', label: 'translation' },
  { key: 'translation_provider', label: 'translation_provider' },
  { key: 'phonetic_uk', label: 'phonetic_uk' },
  { key: 'phonetic_us', label: 'phonetic_us' },
  { key: 'cefr_level', label: 'cefr_level' },
  { key: 'tense', label: 'tense' },
  { key: 'project_file', label: 'project_file' },
  { key: 'created_document_id', label: 'created_document_id' },
  { key: 'project', label: 'project' },
  { key: 'file', label: 'file' },
  { key: 'created', label: 'created' },
  { key: 'document_id', label: 'document_id' },
  { key: 'sentence', label: 'sentence' },
  { key: 'node_id', label: 'node_id' },
  { key: 'node_type', label: 'node_type' },
  { key: 'linguistic_notes', label: 'linguistic_notes' },
  { key: 'translations_json', label: 'translations_json' },
]

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

function normalizePhoneticValue(value: string, sourceContent: string): string {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const source = String(sourceContent || '').trim()
  if (!source) return raw
  // Drop backend fallback where phonetic repeats source text verbatim.
  if (raw.toLowerCase() === source.toLowerCase()) return ''
  return raw
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
      const nodeContent = String(node.content || '')
      const exportRow: ExportRow = {
        content: nodeContent,
        translation: resolveNodeTranslation(node, row.translationProvider),
        translation_provider: row.translationProvider,
        phonetic_uk: normalizePhoneticValue(String(node.phonetic?.uk || ''), nodeContent),
        phonetic_us: normalizePhoneticValue(String(node.phonetic?.us || ''), nodeContent),
        cefr_level: String(node.cefr_level || ''),
        tense: String(node.tense || ''),
        project_file: joinExportPair(row.project, row.file),
        created_document_id: String(row.documentId || ''),
        project: row.project,
        file: row.file,
        created: row.created,
        document_id: row.documentId,
        sentence,
        node_id: String(node.node_id || ''),
        node_type: String(node.type || ''),
        linguistic_notes: notesToExportText(node),
        translations_json: JSON.stringify(node.translations || {}),
      }
      out.push(exportRow)
    }
  }
  return out
}

function downloadTextFile(filename: string, text: string, mimeType: string): void {
  const bom = mimeType.includes('csv') ? '﻿' : ''
  const blob = new Blob([bom + text], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function joinExportPair(left: string, right: string): string {
  const l = String(left || '').trim()
  const r = String(right || '').trim()
  if (l && r) return `${l} | ${r}`
  return l || r
}

function orderExportFields(selectedFields: Array<keyof ExportRow>): Array<keyof ExportRow> {
  const selectedSet = new Set(selectedFields)
  const defaultsInOrder = DEFAULT_EXPORT_FIELDS.filter((field) => selectedSet.has(field))
  const extrasInUserOrder = selectedFields.filter((field) => !DEFAULT_EXPORT_FIELDS.includes(field))
  const out: Array<keyof ExportRow> = []
  const seen = new Set<keyof ExportRow>()
  for (const field of [...defaultsInOrder, ...extrasInUserOrder]) {
    if (seen.has(field)) continue
    seen.add(field)
    out.push(field)
  }
  return out
}

function pickExportFields(rows: ExportRow[], selectedFields: Array<keyof ExportRow>): Array<Partial<ExportRow>> {
  const orderedFields = orderExportFields(selectedFields)
  return rows.map((row) => {
    const out: Partial<ExportRow> = {}
    for (const field of orderedFields) {
      out[field] = row[field]
    }
    return out
  })
}

function toCsvWithFields(rows: ExportRow[], selectedFields: Array<keyof ExportRow>): string {
  const headers = selectedFields.length > 0 ? orderExportFields(selectedFields) : DEFAULT_EXPORT_FIELDS
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const body = rows.map((row) => headers.map((h) => esc((row as Record<string, unknown>)[h])).join(','))
  return [headers.join(','), ...body].join('\n')
}

export function VocabularyPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<VocabRow[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [pendingExportFormat, setPendingExportFormat] = useState<ExportFormat | null>(null)
  const [selectedExportFields, setSelectedExportFields] = useState<Array<keyof ExportRow>>(DEFAULT_EXPORT_FIELDS)

  const fetchPayloadByDocumentId = useCallback(async (documentId: string): Promise<VisualizerPayload | null> => {
    try {
      return await withRetry(() => api.getVisualizerPayload(documentId), 2, 300)
    } catch {
      return null
    }
  }, [api])

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
          items: Math.max(0, Number(row.items_count || 0)),
          created: formatAnalysisTime(row.updated_at),
          settings: String(row.settings || ''),
          documentId: row.document_id ?? null,
          payload: null,
          translationProvider: getTranslationProviderFromSettings(row.settings),
        }
      }

      const loadFromHistory = async (): Promise<VocabRow[]> => {
        const history = await withRetry(() => api.listAnalysisHistory(), 5, 600)
        return history
          .filter((row) => row.contract_current !== false)
          .map((row) => mapHistoryRow(row))
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
        setSelectedIds((prev) => prev.filter((id) => loaded.some((row) => row.id === id)))
        setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [api])

  const selectedCount = selectedIds.length
  const selectedRows = useMemo(() => rows.filter((row) => selectedIds.includes(row.id)), [rows, selectedIds])
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
      const results: Array<{ status: 'ok' | 'error'; message: string; document_id?: string }> = []
      for (const docId of selectedDocumentIds) {
        try {
          results.push(await api.deleteAnalysis(docId))
        } catch {
          results.push({ status: 'error', message: 'delete failed', document_id: docId })
        }
      }
      const deletedIds = new Set(
        results
          .filter((row) => row.status === 'ok')
          .map((row) => String(row.document_id || ''))
          .filter(Boolean),
      )
      if (deletedIds.size > 0) {
        setRows((prev) => prev.filter((row) => !row.documentId || !deletedIds.has(row.documentId)))
        setSelectedIds((prev) => prev.filter((id) => {
          const row = rows.find((item) => item.id === id)
          if (!row) return false
          return !row.documentId || !deletedIds.has(String(row.documentId || ''))
        }))
      }
      if (deletedIds.size !== selectedDocumentIds.length) {
        setLoadError('Some selected analyses were not deleted. Reload page and retry.')
      }
    } finally {
      setDeleting(false)
    }
  }, [api, rows, selectedDocumentIds])

  const confirmExport = useCallback(async () => {
    if (!pendingExportFormat || selectedCount === 0) return
    const freshRows = await resolveRowsForExport(selectedRows)
    const freshExportRows = freshRows.flatMap((row) => toExportRows(row))
    const exportFields = selectedExportFields.length > 0 ? selectedExportFields : DEFAULT_EXPORT_FIELDS
    if (pendingExportFormat === 'json') {
      const narrowed = pickExportFields(freshExportRows, exportFields)
      downloadTextFile(
        `vocabulary_export_${Date.now()}.json`,
        JSON.stringify(narrowed, null, 2),
        'application/json;charset=utf-8',
      )
    } else {
      downloadTextFile(
        `vocabulary_export_${Date.now()}.csv`,
        toCsvWithFields(freshExportRows, exportFields),
        'text/csv;charset=utf-8',
      )
    }
    setPendingExportFormat(null)
  }, [pendingExportFormat, resolveRowsForExport, selectedCount, selectedExportFields, selectedRows])

  return (
    <section className="screen-block vocabulary-page">
      <div className={`vocabulary-actions-shell${selectedCount > 0 ? ' is-open' : ''}`}>
        {selectedCount > 0 ? (
          <div className="actions-row vocabulary-actions-row">
            <button
              type="button"
              className="secondary-btn"
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
              style={{ background: '#2e7d32', color: '#fff', borderColor: '#2e7d32' }}
              onClick={() => {
                setSelectedExportFields(DEFAULT_EXPORT_FIELDS)
                setPendingExportFormat('json')
              }}
            >
              Export JSON
            </button>
            <button
              type="button"
              className="secondary-btn"
              style={{ background: '#2e7d32', color: '#fff', borderColor: '#2e7d32' }}
              onClick={() => {
                setSelectedExportFields(DEFAULT_EXPORT_FIELDS)
                setPendingExportFormat('csv')
              }}
            >
              Export CSV
            </button>
            <button
              type="button"
              className="secondary-btn"
              style={{ background: '#b71c1c', color: '#fff', borderColor: '#b71c1c' }}
              disabled={selectedDocumentIds.length === 0 || deleting}
              onClick={() => {
                void deleteSelectedAnalyses()
              }}
            >
              {deleting ? 'Deleting...' : 'Delete Analyses'}
            </button>
          </div>
        ) : null}
      </div>
      {pendingExportFormat ? (
        <section className="card compact-card">
          <p className="stage-log-title">Choose export fields</p>
          <div className="analysis-feature-badges">
            {EXPORT_FIELD_OPTIONS.map((option) => {
              const active = selectedExportFields.includes(option.key)
              return (
                <button
                  key={`export-field-${option.key}`}
                  type="button"
                  className={`touch-option-btn ${active ? 'active' : ''}`}
                  onClick={() => {
                    setSelectedExportFields((prev) => {
                      if (prev.includes(option.key)) return prev.filter((field) => field !== option.key)
                      return [...prev, option.key]
                    })
                  }}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
          <div className="actions-row">
            <button type="button" onClick={() => setSelectedExportFields(DEFAULT_EXPORT_FIELDS)}>
              Reset Defaults
            </button>
            <button type="button" onClick={() => setPendingExportFormat(null)} className="secondary-btn">
              Cancel
            </button>
            <button type="button" style={{ background: '#2e7d32', color: '#fff', borderColor: '#2e7d32' }} onClick={() => { void confirmExport() }}>
              Export {pendingExportFormat.toUpperCase()}
            </button>
          </div>
        </section>
      ) : null}
      {loading ? <p className="muted">Loading analysis history...</p> : null}
      {!loading && loadError ? <p style={{ color: '#ff8a8a' }}>{loadError}</p> : null}
      {!loading && !loadError && rows.length === 0 ? <p className="muted">No analyzed history yet.</p> : null}
      {rows.length > 0 ? <p className="muted">Tap row to select ({selectedCount} selected).</p> : null}

      <div className="desktop-table">
        <table>
          <thead>
            <tr>
              <th>Project</th>
              <th>File</th>
              <th>Settings</th>
              <th>Items</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const selected = selectedIds.includes(row.id)
              return (
                <tr
                  key={row.id}
                  data-testid={`vocab-row-${row.id}`}
                  className={`vocab-row${selected ? ' is-selected' : ''}`}
                  onClick={() => setSelectedIds((prev) => (prev.includes(row.id) ? prev.filter((id) => id !== row.id) : [...prev, row.id]))}
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    setSelectedIds((prev) => (prev.includes(row.id) ? prev.filter((id) => id !== row.id) : [...prev, row.id]))
                  }}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selected}
                >
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
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mobile-records">
        {rows.map((row) => {
          const selected = selectedIds.includes(row.id)
          const badges = buildAnalysisFeatureBadges(row.settings)
          return (
            <article
              key={`mobile-${row.id}`}
              data-testid={`mobile-vocab-row-${row.id}`}
              className={`mobile-record-card mobile-vocab-row${selected ? ' is-selected' : ''}`}
              onClick={() => setSelectedIds((prev) => (prev.includes(row.id) ? prev.filter((id) => id !== row.id) : [...prev, row.id]))}
              onKeyDown={(event) => {
                if (event.key !== 'Enter' && event.key !== ' ') return
                event.preventDefault()
                setSelectedIds((prev) => (prev.includes(row.id) ? prev.filter((id) => id !== row.id) : [...prev, row.id]))
              }}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
            >
              <div className="mobile-vocab-main">
                <div className="mobile-vocab-topline">
                  <strong className="mobile-vocab-heading">{row.project}</strong>
                </div>
                <div className="mobile-vocab-subline">
                  <strong className="mobile-vocab-heading">{row.file}</strong>
                </div>
                <div className="mobile-vocab-metrics">
                  <div className="mobile-vocab-cell">
                    <span className="mobile-record-label">Items</span>
                    <span className="mobile-vocab-value">{row.items}</span>
                  </div>
                  <div className="mobile-vocab-cell mobile-vocab-created-cell">
                    <span className="mobile-record-label">Created</span>
                    <span className="mobile-vocab-value">{row.created}</span>
                  </div>
                </div>
                <div className="mobile-vocab-settings">
                  <span className="mobile-record-label">Settings</span>
                  <div className="analysis-feature-badges">
                    {badges.map((badge) => (
                      <span key={`mobile-${row.id}-${badge.key}`} className="badge analysis-feature-badge">
                        {badge.label}: {badge.value}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
