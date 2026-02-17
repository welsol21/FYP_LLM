import { useEffect, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { VisualizerPayload, VisualizerNode } from '../api/runtimeApi'
import { VisualizerTreeLegacy } from '../components/VisualizerTreeLegacy'

export function VisualizerPage() {
  const api = useApi()
  const [rows, setRows] = useState<Array<{ sentence_text: string; tree: VisualizerNode }>>([])
  const [nodeId, setNodeId] = useState('n4')
  const [newValue, setNewValue] = useState('trusted them')
  const [editStatus, setEditStatus] = useState('')

  async function refresh() {
    const payload = await api.getVisualizerPayload()
    const normalized = Object.entries(payload as VisualizerPayload).map(([sentence_text, tree]) => ({
      sentence_text,
      tree,
    }))
    setRows(normalized)
  }

  useEffect(() => {
    refresh()
  }, [api])

  async function onApplyEdit(e: React.FormEvent) {
    e.preventDefault()
    const sentenceText = rows[0]?.sentence_text ?? ''
    if (!sentenceText) return
    const result = await api.applyEdit({
      sentenceText,
      nodeId,
      fieldPath: 'content',
      newValue,
    })
    setEditStatus(result.message)
    await refresh()
  }

  return (
    <section className="visualizer-root">
      <section className="card">
        <h1>Linguistic Visualizer</h1>
        <p>Touch-first tree view aligned with the original ELA main menu flow.</p>
      </section>
      <section className="visualizer-row">
        <form onSubmit={onApplyEdit} className="card quick-edit-grid" aria-label="edit-form">
          <h2>Quick Node Edit</h2>
          <label>
            Node ID
            <input value={nodeId} onChange={(e) => setNodeId(e.target.value)} />
          </label>
          <label>
            New Content
            <input value={newValue} onChange={(e) => setNewValue(e.target.value)} />
          </label>
          <div className="quick-edit-actions">
            <button type="submit">Apply Edit</button>
            {editStatus ? <p className="quick-edit-status">{editStatus}</p> : null}
          </div>
        </form>
        <section className="card">
          {rows.map((row) => (
            <article key={row.sentence_text} className="visualizer-article">
              <h2>{row.sentence_text}</h2>
              <VisualizerTreeLegacy node={row.tree} isRoot />
            </article>
          ))}
        </section>
      </section>
    </section>
  )
}
