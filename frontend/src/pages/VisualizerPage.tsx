import { useEffect, useState } from 'react'
import { useApi } from '../api/apiContext'
import type { VisualizerPayload, VisualizerNode } from '../api/runtimeApi'
import { VisualizerTreeLegacy } from '../components/VisualizerTreeLegacy'

const BASIC_EDIT_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'content', label: 'Content' },
  { key: 'cefr_level', label: 'CEFR' },
  { key: 'tense', label: 'Tense' },
  { key: 'linguistic_notes', label: 'Linguistic Notes' },
  { key: 'translation.text', label: 'Translation' },
  { key: 'phonetic.uk', label: 'Phonetic (UK)' },
  { key: 'phonetic.us', label: 'Phonetic (US)' },
]

const ADVANCED_EDIT_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'part_of_speech', label: 'Node Label (part_of_speech)' },
  { key: 'grammatical_role', label: 'Grammatical Role' },
  { key: 'aspect', label: 'Aspect' },
  { key: 'mood', label: 'Mood' },
  { key: 'voice', label: 'Voice' },
  { key: 'finiteness', label: 'Finiteness' },
  { key: 'tam_construction', label: 'TAM Construction' },
  { key: 'dep_label', label: 'Dependency Label' },
  { key: 'translation.source_lang', label: 'Translation Source Language' },
  { key: 'translation.target_lang', label: 'Translation Target Language' },
]

const NULL_SENTINEL = '__NULL__'
const VALUE_PREVIEW_ROWS = 4

const ADVANCED_SELECT_OPTIONS: Record<string, Array<{ value: string; label: string }>> = {
  part_of_speech: [
    { value: 'sentence', label: 'sentence' },
    { value: 'noun phrase', label: 'noun phrase' },
    { value: 'verb phrase', label: 'verb phrase' },
    { value: 'prepositional phrase', label: 'prepositional phrase' },
    { value: 'adjective phrase', label: 'adjective phrase' },
    { value: 'adverbial phrase', label: 'adverbial phrase' },
    { value: 'noun', label: 'noun' },
    { value: 'proper noun', label: 'proper noun' },
    { value: 'pronoun', label: 'pronoun' },
    { value: 'verb', label: 'verb' },
    { value: 'auxiliary verb', label: 'auxiliary verb' },
    { value: 'modal verb', label: 'modal verb' },
    { value: 'adjective', label: 'adjective' },
    { value: 'adverb', label: 'adverb' },
    { value: 'preposition', label: 'preposition' },
    { value: 'article', label: 'article' },
    { value: 'coordinating conjunction', label: 'coordinating conjunction' },
    { value: 'subordinating conjunction', label: 'subordinating conjunction' },
    { value: 'particle', label: 'particle' },
    { value: 'numeral', label: 'numeral' },
    { value: 'interjection', label: 'interjection' },
    { value: 'punctuation', label: 'punctuation' },
    { value: 'other', label: 'other' },
  ],
  grammatical_role: [
    { value: 'subject', label: 'subject' },
    { value: 'predicate', label: 'predicate' },
    { value: 'object', label: 'object' },
    { value: 'complement', label: 'complement' },
    { value: 'modifier', label: 'modifier' },
    { value: 'adjunct', label: 'adjunct' },
    { value: 'determiner', label: 'determiner' },
    { value: 'auxiliary', label: 'auxiliary' },
    { value: 'linker', label: 'linker' },
    { value: 'coordinator', label: 'coordinator' },
    { value: 'conjunct', label: 'conjunct' },
    { value: 'clause', label: 'clause' },
    { value: 'other', label: 'other' },
  ],
  aspect: [
    { value: NULL_SENTINEL, label: 'null' },
    { value: 'simple', label: 'simple' },
    { value: 'perfect', label: 'perfect' },
    { value: 'progressive', label: 'progressive' },
    { value: 'perfect_progressive', label: 'perfect_progressive' },
  ],
  mood: [
    { value: NULL_SENTINEL, label: 'null' },
    { value: 'indicative', label: 'indicative' },
    { value: 'imperative', label: 'imperative' },
    { value: 'subjunctive', label: 'subjunctive' },
    { value: 'modal', label: 'modal' },
  ],
  voice: [
    { value: NULL_SENTINEL, label: 'null' },
    { value: 'active', label: 'active' },
    { value: 'passive', label: 'passive' },
  ],
  finiteness: [
    { value: NULL_SENTINEL, label: 'null' },
    { value: 'finite', label: 'finite' },
    { value: 'non-finite', label: 'non-finite' },
  ],
  tam_construction: [
    { value: NULL_SENTINEL, label: 'null' },
    { value: 'none', label: 'none' },
    { value: 'modal_perfect', label: 'modal_perfect' },
  ],
  dep_label: [
    { value: 'ROOT', label: 'ROOT' },
    { value: 'nsubj', label: 'nsubj' },
    { value: 'nsubjpass', label: 'nsubjpass' },
    { value: 'csubj', label: 'csubj' },
    { value: 'csubjpass', label: 'csubjpass' },
    { value: 'obj', label: 'obj' },
    { value: 'dobj', label: 'dobj' },
    { value: 'iobj', label: 'iobj' },
    { value: 'pobj', label: 'pobj' },
    { value: 'attr', label: 'attr' },
    { value: 'acomp', label: 'acomp' },
    { value: 'oprd', label: 'oprd' },
    { value: 'amod', label: 'amod' },
    { value: 'nmod', label: 'nmod' },
    { value: 'advmod', label: 'advmod' },
    { value: 'advcl', label: 'advcl' },
    { value: 'det', label: 'det' },
    { value: 'aux', label: 'aux' },
    { value: 'auxpass', label: 'auxpass' },
    { value: 'prep', label: 'prep' },
    { value: 'cc', label: 'cc' },
    { value: 'conj', label: 'conj' },
  ],
  'translation.source_lang': [
    { value: 'en', label: 'en' },
    { value: 'ru', label: 'ru' },
    { value: 'uk', label: 'uk' },
    { value: 'de', label: 'de' },
    { value: 'fr', label: 'fr' },
    { value: 'es', label: 'es' },
    { value: 'it', label: 'it' },
    { value: 'pt', label: 'pt' },
    { value: 'pl', label: 'pl' },
    { value: 'tr', label: 'tr' },
    { value: 'zh', label: 'zh' },
    { value: 'ja', label: 'ja' },
    { value: 'ko', label: 'ko' },
    { value: 'ar', label: 'ar' },
  ],
  'translation.target_lang': [
    { value: 'en', label: 'en' },
    { value: 'ru', label: 'ru' },
    { value: 'uk', label: 'uk' },
    { value: 'de', label: 'de' },
    { value: 'fr', label: 'fr' },
    { value: 'es', label: 'es' },
    { value: 'it', label: 'it' },
    { value: 'pt', label: 'pt' },
    { value: 'pl', label: 'pl' },
    { value: 'tr', label: 'tr' },
    { value: 'zh', label: 'zh' },
    { value: 'ja', label: 'ja' },
    { value: 'ko', label: 'ko' },
    { value: 'ar', label: 'ar' },
  ],
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

function getValueByPath(root: unknown, path: string): unknown {
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

function serializeEditValue(value: unknown): string {
  if (value == null) return ''
  if (Array.isArray(value)) {
    return value.map((v) => (typeof v === 'string' ? v : JSON.stringify(v))).join('\n')
  }
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function normalizeAdvancedFieldValue(field: string, serialized: string): string {
  const options = ADVANCED_SELECT_OPTIONS[field] || []
  const hasNullOption = options.some((opt) => opt.value === NULL_SENTINEL)
  if (hasNullOption && serialized === '') return NULL_SENTINEL
  return serialized
}

function decodeEditorValue(raw: string): string {
  return raw
}

export function VisualizerPage() {
  const api = useApi()
  const [rows, setRows] = useState<Array<{ sentence_text: string; tree: VisualizerNode }>>([])
  const [activeSentenceIndex, setActiveSentenceIndex] = useState(0)
  const [isNarrowScreen, setIsNarrowScreen] = useState(
    typeof window !== 'undefined' ? window.innerWidth <= 860 : false,
  )
  const [quickEditOpen, setQuickEditOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [nodeId, setNodeId] = useState('')
  const [selectedNodeLabel, setSelectedNodeLabel] = useState('')
  const [selectedNode, setSelectedNode] = useState<VisualizerNode | null>(null)
  const [basicField, setBasicField] = useState('content')
  const [advancedField, setAdvancedField] = useState(ADVANCED_EDIT_FIELDS[0].key)
  const [advancedValueExpanded, setAdvancedValueExpanded] = useState(false)
  const [newValue, setNewValue] = useState('')
  const [editStatus, setEditStatus] = useState('')

  async function refresh() {
    const payload = await api.getVisualizerPayload()
    const normalized = Object.entries(payload as VisualizerPayload).map(([sentence_text, tree]) => ({
      sentence_text,
      tree,
    }))
    setRows(normalized)
    setActiveSentenceIndex((prev) => {
      if (normalized.length === 0) return 0
      return Math.min(prev, normalized.length - 1)
    })
  }

  useEffect(() => {
    refresh()
  }, [api])

  useEffect(() => {
    const onResize = () => setIsNarrowScreen(window.innerWidth <= 860)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    setNodeId('')
    setSelectedNodeLabel('')
    setSelectedNode(null)
    setBasicField('content')
    setAdvancedField(ADVANCED_EDIT_FIELDS[0].key)
    setAdvancedOpen(false)
    setAdvancedValueExpanded(false)
    setNewValue('')
    setEditStatus('')
  }, [activeSentenceIndex])

  async function onApplyEdit(e: React.FormEvent) {
    e.preventDefault()
    const sentenceText = rows[activeSentenceIndex]?.sentence_text ?? ''
    const fieldPath = advancedOpen ? advancedField : basicField
    if (!sentenceText || !nodeId) {
      setEditStatus('Select a node first by tapping/clicking its label.')
      return
    }
    if (!fieldPath) {
      setEditStatus('Field path is required.')
      return
    }
    const valueForSubmit = newValue === NULL_SENTINEL ? '__NULL__' : newValue
    const result = await api.applyEdit({
      sentenceText,
      nodeId,
      fieldPath,
      newValue: valueForSubmit,
    })
    setEditStatus(result.message)
    await refresh()
  }

  const activeRow = rows[activeSentenceIndex]
  const hasPrev = activeSentenceIndex > 0
  const hasNext = activeSentenceIndex < rows.length - 1

  function onSelectNode(node: VisualizerNode) {
    setNodeId(node.node_id)
    setSelectedNodeLabel(node.part_of_speech)
    setSelectedNode(node)
    const path = advancedOpen ? advancedField : basicField
    const serialized = serializeEditValue(getValueByPath(node, path))
    if (advancedOpen) {
      setNewValue(normalizeAdvancedFieldValue(path, serialized))
    } else {
      setNewValue(serialized)
    }
    setEditStatus('')
    setQuickEditOpen(true)
  }

  function onChangeBasicField(path: string) {
    setBasicField(path)
    if (!selectedNode) return
    setNewValue(serializeEditValue(getValueByPath(selectedNode, path)))
  }

  function onChangeAdvancedField(path: string) {
    setAdvancedField(path)
    setAdvancedValueExpanded(false)
    if (!selectedNode) return
    const serialized = serializeEditValue(getValueByPath(selectedNode, path))
    setNewValue(normalizeAdvancedFieldValue(path, serialized))
  }

  const activeFieldPath = advancedOpen ? advancedField : basicField
  const advancedOptions = ADVANCED_SELECT_OPTIONS[advancedField] || []
  const useAdvancedSelect = advancedOpen && advancedOptions.length > 0
  const valueGridColumns = isNarrowScreen ? 1 : 2
  const valueRows = Math.ceil(advancedOptions.length / valueGridColumns)
  const hasOverflowValues = useAdvancedSelect && valueRows > VALUE_PREVIEW_ROWS
  const valuesExpanded = !hasOverflowValues || advancedValueExpanded
  const maxPreviewItems = Math.max(VALUE_PREVIEW_ROWS * valueGridColumns, 1)
  const visibleAdvancedOptions = valuesExpanded ? advancedOptions : advancedOptions.slice(0, maxPreviewItems)
  const optionsToRender =
    visibleAdvancedOptions.length > 0
      ? visibleAdvancedOptions
      : advancedOptions.slice(0, Math.min(maxPreviewItems, advancedOptions.length))
  const showTextarea = activeFieldPath === 'linguistic_notes' || newValue.includes('\n') || newValue.length > 80

  return (
    <section className="visualizer-root">
      <section className="visualizer-row">
        <form onSubmit={onApplyEdit} className="card quick-edit-grid" aria-label="edit-form">
          <div className="quick-edit-header">
            <h2>Quick Node Edit</h2>
            <div className="quick-edit-header-actions">
              {quickEditOpen ? (
                <button
                  type="button"
                  className="quick-edit-advanced-toggle"
                  onClick={() => setAdvancedOpen((prev) => !prev)}
                >
                  {advancedOpen ? 'Basic' : 'Advanced'}
                </button>
              ) : null}
              <button
                type="button"
                className="quick-edit-toggle"
                onClick={() => setQuickEditOpen((prev) => !prev)}
                aria-label="toggle-quick-edit"
              >
                {quickEditOpen ? 'Collapse' : 'Expand'}
              </button>
            </div>
          </div>
          {quickEditOpen ? (
            <>
              <p className="quick-edit-help">
                Select a node by tapping/clicking its label (<code>sentence</code>, <code>noun phrase</code>, etc.).
                Edit visible fields in Basic mode, or use Advanced mode for linguist-only fields.
              </p>
              <p className="quick-edit-meta">
                Selected Node: {selectedNodeLabel || '-'}
              </p>
              {advancedOpen ? (
                <div>
                  <label>Advanced Field</label>
                  <div className="touch-choice-grid">
                    {ADVANCED_EDIT_FIELDS.map((field) => (
                      <button
                        key={field.key}
                        type="button"
                        className={`touch-choice-btn ${advancedField === field.key ? 'active' : ''}`}
                        onClick={() => onChangeAdvancedField(field.key)}
                      >
                        {field.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div>
                  <label>Field</label>
                  <div className="touch-choice-grid">
                    {BASIC_EDIT_FIELDS.map((field) => (
                      <button
                        key={field.key}
                        type="button"
                        className={`touch-choice-btn ${basicField === field.key ? 'active' : ''}`}
                        onClick={() => onChangeBasicField(field.key)}
                      >
                        {field.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <label>
                New Content
                {useAdvancedSelect ? (
                  <div className="touch-value-picker">
                    <div className="touch-value-picker-top">
                      <span className="touch-value-current">
                        <span className="touch-value-current-label">Selected</span>
                        <span className="touch-value-current-value">
                          {(advancedOptions.find((opt) => opt.value === (newValue || NULL_SENTINEL))?.label) || '-'}
                        </span>
                      </span>
                      {hasOverflowValues ? (
                        <button
                          type="button"
                          className="quick-edit-toggle"
                          onClick={() => setAdvancedValueExpanded((prev) => !prev)}
                        >
                          {valuesExpanded ? 'Collapse Values' : 'Expand Values'}
                        </button>
                      ) : null}
                    </div>
                    <div className="touch-choice-grid touch-choice-grid-values">
                      {optionsToRender.map((opt) => {
                        const currentValue = newValue || NULL_SENTINEL
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            className={`touch-choice-btn ${currentValue === opt.value ? 'active' : ''}`}
                            onClick={() => setNewValue(decodeEditorValue(opt.value))}
                          >
                            {opt.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ) : showTextarea ? (
                  <textarea value={newValue} onChange={(e) => setNewValue(e.target.value)} rows={4} />
                ) : (
                  <input value={newValue} onChange={(e) => setNewValue(e.target.value)} />
                )}
              </label>
              <div className="quick-edit-actions">
                <button type="submit">Apply Edit</button>
                {editStatus ? <p className="quick-edit-status">{editStatus}</p> : null}
              </div>
            </>
          ) : null}
        </form>
        <section className="card">
          <div className="sentence-nav">
            <button type="button" onClick={() => setActiveSentenceIndex((v) => Math.max(0, v - 1))} disabled={!hasPrev}>
              Prev
            </button>
            <span className="sentence-nav-status">
              {rows.length === 0 ? '0 / 0' : `${activeSentenceIndex + 1} / ${rows.length}`}
            </span>
            <button
              type="button"
              onClick={() => setActiveSentenceIndex((v) => Math.min(rows.length - 1, v + 1))}
              disabled={!hasNext}
            >
              Next
            </button>
          </div>
          {activeRow ? (
            <article key={activeRow.sentence_text} className="visualizer-article">
              <VisualizerTreeLegacy
                node={activeRow.tree}
                isRoot
                selectedNodeId={nodeId}
                onNodeSelect={onSelectNode}
              />
            </article>
          ) : null}
        </section>
      </section>
    </section>
  )
}
