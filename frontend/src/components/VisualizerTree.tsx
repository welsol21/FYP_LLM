import { useMemo, useState } from 'react'
import type { VisualizerNode } from '../api/runtimeApi'

type Props = {
  node: VisualizerNode
  depth?: number
}

const COLOR_MAP: Record<string, string> = {
  sentence: '#f0d45a',
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

function resolveLabel(node: VisualizerNode): string {
  return node.part_of_speech ?? node.phraseType ?? node.type
}

function toneForLabel(label: string): string {
  return COLOR_MAP[label.toLowerCase()] ?? '#7a8699'
}

export function VisualizerTree({ node, depth = 0 }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [showDetails, setShowDetails] = useState(depth === 0)
  const label = resolveLabel(node)
  const borderColor = useMemo(() => toneForLabel(label), [label])
  const hasChildren = node.children.length > 0

  return (
    <div className="visualizer-node parse-node" style={{ borderLeftColor: borderColor }}>
      <div className="visualizer-node-head">
        <div className="visualizer-node-title">
          <button
            type="button"
            className="node-chip"
            style={{ backgroundColor: borderColor }}
            onClick={() => setShowDetails((prev) => !prev)}
            aria-label={`details-${node.node_id}`}
          >
            {label}
          </button>
          {node.cefr_level ? <span className="pill level">{node.cefr_level}</span> : null}
          {depth === 0 ? <span className="pill">root</span> : null}
        </div>
        {hasChildren ? (
          <button
            type="button"
            className="tree-toggle"
            onClick={() => setExpanded((prev) => !prev)}
            aria-label={`toggle-${node.node_id}`}
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        ) : null}
      </div>
      <div className="node-content-strip">
        {hasChildren ? (
          node.children.map((child) => {
            const childLabel = resolveLabel(child)
            return (
              <span
                key={child.node_id}
                className="child-content"
                style={{ borderBottomColor: toneForLabel(childLabel) }}
              >
                {child.content}
              </span>
            )
          })
        ) : (
          <span className="child-content own" style={{ borderBottomColor: borderColor }}>
            {node.content}
          </span>
        )}
      </div>
      {showDetails ? (
        <div className="node-details">
          {node.cefr_level ? <div><strong>CEFR:</strong> {node.cefr_level}</div> : null}
          {node.tense ? <div><strong>Tense:</strong> {node.tense}</div> : null}
          {node.linguistic_notes?.length ? <div><strong>Linguistic Notes:</strong> {node.linguistic_notes.join(' ')}</div> : null}
          {node.translation?.text ? <div><strong>Translation:</strong> {node.translation.text}</div> : null}
          {node.phonetic?.uk || node.phonetic?.us ? (
            <div>
              <strong>Phonetic:</strong>{' '}
              {node.phonetic?.uk ? `UK /${node.phonetic.uk}/` : ''}
              {node.phonetic?.uk && node.phonetic?.us ? ' | ' : ''}
              {node.phonetic?.us ? `US /${node.phonetic.us}/` : ''}
            </div>
          ) : null}
        </div>
      ) : null}
      {hasChildren && expanded ? (
        <div className="tree-children">
          {node.children.map((child) => (
            <VisualizerTree key={child.node_id} node={child} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
