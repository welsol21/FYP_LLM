import { useEffect, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { VisualizerPayloadRow } from '../api/runtimeApi'
import { VisualizerTree } from '../components/VisualizerTree'

export function VisualizerPage() {
  const api = useApi()
  const [rows, setRows] = useState<VisualizerPayloadRow[]>([])
  const [nodeId, setNodeId] = useState('p1')
  const [newValue, setNewValue] = useState('trusted them')
  const [editStatus, setEditStatus] = useState('')

  async function refresh() {
    const payload = await api.getVisualizerPayload()
    setRows(payload)
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
    <section className="card">
      <h1>Linguistic Visualizer</h1>
      <form onSubmit={onApplyEdit} className="card" aria-label="edit-form">
        <h2>Quick Node Edit</h2>
        <label>
          Node ID
          <input value={nodeId} onChange={(e) => setNodeId(e.target.value)} />
        </label>
        <label>
          New Content
          <input value={newValue} onChange={(e) => setNewValue(e.target.value)} />
        </label>
        <button type="submit">Apply Edit</button>
        {editStatus ? <p>{editStatus}</p> : null}
      </form>
      {rows.map((row) => (
        <article key={row.sentence_text}>
          <h2>{row.sentence_text}</h2>
          <ul>
            <VisualizerTree node={row.tree} />
          </ul>
        </article>
      ))}
    </section>
  )
}
