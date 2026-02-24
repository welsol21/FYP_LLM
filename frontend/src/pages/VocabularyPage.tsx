import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/apiContext'
import type { VisualizerNode, VisualizerPayload } from '../api/runtimeApi'
import { resolveNodeTranslation } from '../lib/translationContract'

type VocabRow = {
  id: string
  project: string
  file: string
  items: number
  created: string
  documentId: string | null
  payload: VisualizerPayload | null
  translationProvider: string
}

type ExportRow = {
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

function parseTranslationProvider(settings: string): string {
  const match = String(settings || '').match(/Transl:\s*([^/]+)/i)
  return match?.[1]?.trim().toLowerCase() || 'backend_m2m100'
}

function toExportRows(row: VocabRow): ExportRow[] {
  if (!row.payload || !row.documentId) return []
  const out: ExportRow[] = []
  for (const [sentence, root] of Object.entries(row.payload)) {
    const elements = collectLinguisticElements(root)
    for (const node of elements) {
      out.push({
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
        linguistic_notes: Array.isArray(node.linguistic_notes) ? node.linguistic_notes.join(' | ') : '',
        translation_provider: row.translationProvider,
        translation: resolveNodeTranslation(node, row.translationProvider),
        translations_json: JSON.stringify(node.translations || {}),
        phonetic_uk: String(node.phonetic?.uk || ''),
        phonetic_us: String(node.phonetic?.us || ''),
      })
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
  const headers = Object.keys(rows[0] || {
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
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const body = rows.map((row) => headers.map((h) => esc((row as Record<string, unknown>)[h])).join(','))
  return [headers.join(','), ...body].join('\n')
}

export function VocabularyPage() {
  const api = useApi()
  const navigate = useNavigate()
  const [rows, setRows] = useState<VocabRow[]>([])
  const [checked, setChecked] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let alive = true
    ;(async () => {
      const projects = await api.listProjects()
      const grouped = await Promise.all(
        projects.map(async (p) => {
          const files = await api.listFiles(p.id)
          const analyzed = files.filter((f) => f.analyzed)
          return Promise.all(
            analyzed.map(async (f) => {
              const payload = f.document_id ? await api.getVisualizerPayload(f.document_id) : null
              return {
                id: `${p.id}:${f.id}`,
                project: p.name,
                file: f.name,
                items: countPayloadElements(payload),
                created: new Date(f.updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
                documentId: f.document_id ?? null,
                payload,
                translationProvider: parseTranslationProvider(f.settings),
              }
            }),
          )
        }),
      )
      if (alive) setRows(grouped.flat().flat())
    })()
    return () => {
      alive = false
    }
  }, [api])

  const selectedCount = useMemo(() => Object.values(checked).filter(Boolean).length, [checked])
  const selectedRows = useMemo(() => rows.filter((row) => checked[row.id]), [rows, checked])
  const exportRows = useMemo(() => selectedRows.flatMap((row) => toExportRows(row)), [selectedRows])
  const selectedDocumentId = selectedRows.find((row) => row.documentId)?.documentId ?? null

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
              navigate('/visualizer', { state: { documentId: selectedDocumentId } })
            }}
          >
            Visualizer
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={selectedCount === 0}
            onClick={() =>
              downloadTextFile(
                `vocabulary_export_${Date.now()}.json`,
                JSON.stringify(exportRows, null, 2),
                'application/json;charset=utf-8',
              )
            }
          >
            Export JSON
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={selectedCount === 0}
            onClick={() => downloadTextFile(`vocabulary_export_${Date.now()}.csv`, toCsv(exportRows), 'text/csv;charset=utf-8')}
          >
            Export CSV
          </button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th style={{ width: 36 }} />
            <th>Project</th>
            <th>File</th>
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
              <td>{row.items}</td>
              <td>{row.created}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
