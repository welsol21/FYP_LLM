import { useMemo, useState } from 'react'
import type { VisualizerNode } from '../api/runtimeApi'

const colorMap: Record<string, string> = {
  sentence: '#fdf6e3',
  'modal phrase': '#f7c948',
  'verb phrase': '#e9b949',
  'noun phrase': '#f4a259',
  'prepositional phrase': '#dfaf2b',
  'adjective phrase': '#f6aa64',
  'adverbial phrase': '#e6a141',
  pronoun: '#6dbf4b',
  verb: '#3d9970',
  'auxiliary verb': '#4ecdc4',
  'modal verb': '#2ecc71',
  noun: '#a8d582',
  adjective: '#b2e672',
  adverb: '#ace1af',
  preposition: '#8faf5a',
  determiner: '#567d46',
  article: '#567d46',
  conjunction: '#228b22',
}

const topLevelPalette = ['#f6c90e', '#3ec1d3', '#ff6f59', '#7bd389', '#a78bfa', '#f59e0b']

function labelOf(node: VisualizerNode): string {
  return node.part_of_speech
}

function colorOf(label: string): string {
  return colorMap[label.toLowerCase()] ?? '#c7c7c7'
}

type Token = { text: string; tone: string }

function orderedChildren(node: VisualizerNode): VisualizerNode[] {
  const src = node.linguistic_elements.map((child, idx) => ({ child, idx }))
  const parent = node.content.toLowerCase()
  const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const firstBoundaryIndex = (text: string): number => {
    const needle = text.trim().toLowerCase()
    if (!needle) return Number.MAX_SAFE_INTEGER
    const pattern = new RegExp(`\\b${escapeRegExp(needle)}\\b`, 'i')
    const match = pattern.exec(parent)
    return match ? match.index : Number.MAX_SAFE_INTEGER
  }
  return src
    .sort((a, b) => {
    const ai = firstBoundaryIndex(a.child.content)
    const bi = firstBoundaryIndex(b.child.content)
    const av = ai === -1 ? Number.MAX_SAFE_INTEGER : ai
    const bv = bi === -1 ? Number.MAX_SAFE_INTEGER : bi
      if (av !== bv) return av - bv
      return a.idx - b.idx
    })
    .map((entry) => entry.child)
}

function stableTopLevelTone(nodeId: string): string {
  let hash = 0
  for (let i = 0; i < nodeId.length; i += 1) {
    hash = (hash * 31 + nodeId.charCodeAt(i)) >>> 0
  }
  return topLevelPalette[hash % topLevelPalette.length]
}

function nodeTokens(node: VisualizerNode, level: number): Token[] {
  if (level === 0 && node.linguistic_elements.length > 0) {
    return orderedChildren(node).map((child) => ({
      text: child.content,
      tone: colorOf(labelOf(child)),
    }))
  }
  const tone = level === 1 && node.linguistic_elements.length === 0 ? stableTopLevelTone(node.node_id) : colorOf(labelOf(node))
  return [{ text: node.content, tone }]
}

type Props = {
  node: VisualizerNode
  isRoot?: boolean
  level?: number
}

export function VisualizerTreeLegacy({ node, isRoot = false, level = 0 }: Props) {
  const [childrenOpen, setChildrenOpen] = useState(isRoot)
  const label = labelOf(node)
  const tone = useMemo(() => {
    if (level === 1 && node.linguistic_elements.length === 0) return stableTopLevelTone(node.node_id)
    return colorOf(label)
  }, [label, level, node.linguistic_elements.length, node.node_id])
  const children = useMemo(() => orderedChildren(node), [node])
  const tokens = useMemo(() => nodeTokens(node, level), [node, level])
  const hasChildren = children.length > 0
  const cefrText = node.cefr_level ?? '-'
  const tenseText = node.tense == null || node.tense === '' ? '-' : node.tense
  const notesText = node.linguistic_notes.length
    ? node.linguistic_notes.join(' ')
    : (node.notes?.map((note) => note?.text?.trim()).filter(Boolean).join(' ') || '-')
  const translationText = node.translation?.text?.trim() ? node.translation.text : '-'
  const phoneticText =
    node.phonetic?.uk || node.phonetic?.us
      ? `${node.phonetic?.uk ? `UK /${node.phonetic.uk}/` : ''}${node.phonetic?.uk && node.phonetic?.us ? ' | ' : ''}${node.phonetic?.us ? `US /${node.phonetic.us}/` : ''}`
      : '-'

  return (
    <div className="lv-node-wrap">
      <div className="lv-node-top">
        <span className="lv-label-chip" style={{ backgroundColor: tone }}>
          {label}
        </span>
        {node.cefr_level ? <span className="lv-cefr-pill">{node.cefr_level}</span> : null}
        {hasChildren ? (
          <button
            type="button"
            className="lv-collapse-btn"
            onClick={() => setChildrenOpen((prev) => !prev)}
            aria-label={`toggle-children-${node.node_id}`}
          >
            {childrenOpen ? 'Collapse' : 'Expand'}
          </button>
        ) : null}
      </div>

      <div className="lv-content-line">
        {tokens.map((token, idx) => (
          <span key={`${node.node_id}-${idx}-${token.text}`} className="lv-content-token" style={{ borderBottomColor: token.tone }}>
            {token.text}
          </span>
        ))}
      </div>

      <div className="lv-details-card">
        <div><strong>CEFR:</strong> {cefrText}</div>
        <div><strong>Tense:</strong> {tenseText}</div>
        <div><strong>Linguistic Notes:</strong> {notesText}</div>
        <div><strong>Translation:</strong> {translationText}</div>
        <div><strong>Phonetic:</strong> {phoneticText}</div>
      </div>

      {hasChildren && childrenOpen ? (
        <div className="lv-children-col">
          {children.map((child) => (
            <div key={child.node_id} className="lv-child-item">
              <VisualizerTreeLegacy node={child} level={level + 1} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
