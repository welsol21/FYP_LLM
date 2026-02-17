import type { VisualizerNode } from '../api/runtimeApi'

type Props = {
  node: VisualizerNode
}

export function VisualizerTree({ node }: Props) {
  return (
    <li>
      <div className="node-box">
        <strong>{node.type}</strong>: {node.content}
        {node.cefr_level ? ` [${node.cefr_level}]` : ''}
      </div>
      {node.children.length > 0 ? (
        <ul>
          {node.children.map((child) => (
            <VisualizerTree key={child.node_id} node={child} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}
