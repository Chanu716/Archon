import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ImpactedEntity {
  id: string
  type: string
  name: string
  qualified_name: string | null
  file: string | null
  distance: number
  relationship: string
  resolution: string
  path: string[]
}

interface ImpactResult {
  target_id: string
  target_name: string
  target_type: string
  snapshot_id: string
  direct_callers: ImpactedEntity[]
  indirect_callers: ImpactedEntity[]
  direct_callees: ImpactedEntity[]
  indirect_callees: ImpactedEntity[]
  affected_files: string[]
  affected_modules: string[]
  affected_classes: string[]
  unresolved_references: ImpactedEntity[]
  summary: {
    direct_callers: number
    indirect_callers: number
    direct_callees: number
    indirect_callees: number
    affected_files: number
    affected_modules: number
    affected_classes: number
    unresolved_references: number
  }
  traversal: {
    max_depth: number
    max_nodes: number
    actual_depth_reached: number
    nodes_visited: number
    truncated: boolean
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

const ResolutionBadge = ({ resolution }: { resolution: string }) => {
  const styles: Record<string, string> = {
    exact: 'bg-blue-900/40 text-blue-400 border border-blue-700/40',
    inferred: 'bg-purple-900/40 text-purple-400 border border-purple-700/40',
    unresolved: 'bg-gray-800 text-gray-500 border border-gray-700',
  }
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${styles[resolution] ?? styles.unresolved}`}>
      {resolution}
    </span>
  )
}

const EntityRow = ({
  entity,
  onNavigate,
}: {
  entity: ImpactedEntity
  onNavigate?: (id: string) => void
}) => (
  <div className="flex items-start gap-2 py-1.5 border-b border-gray-800/60 last:border-0">
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-1.5 flex-wrap">
        <button
          className="text-gray-200 text-xs font-medium hover:text-white truncate max-w-[180px]"
          title={entity.qualified_name || entity.name}
          onClick={() => onNavigate?.(entity.id)}
        >
          {entity.name}
        </button>
        <ResolutionBadge resolution={entity.resolution} />
      </div>
      {entity.file && (
        <p className="text-gray-600 text-xs mt-0.5 truncate">{entity.file}</p>
      )}
      {entity.path.length > 1 && (
        <p className="text-gray-600 text-xs mt-0.5 font-mono truncate" title={entity.path.join(' → ')}>
          {entity.path.join(' → ')}
        </p>
      )}
    </div>
    <span className="text-gray-600 text-xs flex-shrink-0 mt-0.5">d={entity.distance}</span>
  </div>
)

const Section = ({
  title,
  count,
  children,
  defaultOpen = false,
  variant = 'neutral',
}: {
  title: string
  count: number
  children: React.ReactNode
  defaultOpen?: boolean
  variant?: 'upstream' | 'downstream' | 'unresolved' | 'neutral'
}) => {
  const [open, setOpen] = useState(defaultOpen)
  if (count === 0) return null

  const headerColors: Record<string, string> = {
    upstream: 'text-amber-400',
    downstream: 'text-cyan-400',
    unresolved: 'text-gray-500',
    neutral: 'text-gray-400',
  }

  return (
    <div className="border-b border-gray-800">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-800/40 transition"
      >
        <span className={`text-xs font-semibold uppercase tracking-wide ${headerColors[variant]}`}>
          {title}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-400 bg-gray-800 px-1.5 py-0.5 rounded">{count}</span>
          <span className="text-gray-600 text-xs">{open ? '▲' : '▼'}</span>
        </div>
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

interface ImpactPanelProps {
  repoId: string
  entityId: string
  entityName: string
  onClose: () => void
  onHighlightNodes?: (nodeIds: string[], mode: 'direct' | 'indirect' | 'unresolved') => void
  onNavigateToNode?: (nodeId: string) => void
}

export default function ImpactPanel({
  repoId,
  entityId,
  entityName,
  onClose,
  onHighlightNodes,
  onNavigateToNode,
}: ImpactPanelProps) {
  const [direction, setDirection] = useState<'both' | 'upstream' | 'downstream'>('both')
  const [depth, setDepth] = useState(5)

  const { data, isLoading, error, refetch } = useQuery<ImpactResult>({
    queryKey: ['impact', repoId, entityId, direction, depth],
    queryFn: () => api.getImpact(repoId, entityId, direction, depth),
    staleTime: 30_000,
  })

  // Notify the graph canvas about impacted nodes for visual mode
  const handleVisualizeImpact = () => {
    if (!data || !onHighlightNodes) return
    const directIds = [...data.direct_callers, ...data.direct_callees].map(e => e.id)
    const indirectIds = [...data.indirect_callers, ...data.indirect_callees].map(e => e.id)
    const unresolvedIds = data.unresolved_references.map(e => e.id)
    onHighlightNodes(directIds, 'direct')
    onHighlightNodes(indirectIds, 'indirect')
    onHighlightNodes(unresolvedIds, 'unresolved')
  }

  return (
    <div className="w-96 bg-gray-900 border-l border-gray-700 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex justify-between items-start flex-shrink-0">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-orange-400 mb-1">
            Impact Analysis
          </div>
          <h2 className="text-white font-bold text-sm truncate" title={entityName}>{entityName}</h2>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white ml-2 text-lg leading-none flex-shrink-0">✕</button>
      </div>

      {/* Controls */}
      <div className="p-3 border-b border-gray-800 flex gap-2 flex-shrink-0">
        <select
          value={direction}
          onChange={e => setDirection(e.target.value as typeof direction)}
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-blue-500"
        >
          <option value="both">Both directions</option>
          <option value="upstream">Upstream (callers)</option>
          <option value="downstream">Downstream (callees)</option>
        </select>
        <select
          value={depth}
          onChange={e => setDepth(Number(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-blue-500"
        >
          {[1, 2, 3, 5, 7, 10].map(d => (
            <option key={d} value={d}>Depth {d}</option>
          ))}
        </select>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-6 text-center text-gray-500 text-sm">Traversing graph…</div>
        )}
        {error && (
          <div className="p-4 text-red-400 text-xs">
            Failed to load impact data. Entity may not be in graph.
          </div>
        )}
        {data && (
          <>
            {/* Summary cards */}
            <div className="p-4 border-b border-gray-800">
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['Direct Callers', data.summary.direct_callers, 'text-amber-400'],
                  ['Indirect Callers', data.summary.indirect_callers, 'text-amber-300/60'],
                  ['Direct Callees', data.summary.direct_callees, 'text-cyan-400'],
                  ['Indirect Callees', data.summary.indirect_callees, 'text-cyan-300/60'],
                  ['Affected Files', data.summary.affected_files, 'text-indigo-400'],
                  ['Affected Modules', data.summary.affected_modules, 'text-blue-400'],
                ].map(([label, val, color]) => (
                  <div key={String(label)} className="bg-gray-800/50 rounded p-2">
                    <div className={`text-lg font-bold font-mono ${color}`}>{val}</div>
                    <div className="text-gray-500 text-xs">{label}</div>
                  </div>
                ))}
              </div>

              {/* Visualize button */}
              {onHighlightNodes && (
                <button
                  onClick={handleVisualizeImpact}
                  className="mt-3 w-full bg-orange-700/30 hover:bg-orange-700/50 border border-orange-700/50 text-orange-300 text-xs py-1.5 rounded transition"
                >
                  Highlight in Graph
                </button>
              )}
            </div>

            {/* Truncation warning */}
            {data.traversal.truncated && (
              <div className="mx-4 mt-3 p-2 bg-yellow-900/20 border border-yellow-800/40 rounded text-yellow-400 text-xs">
                ⚠ Results truncated — visited {data.traversal.nodes_visited}/{data.traversal.max_nodes} nodes at depth {data.traversal.actual_depth_reached}/{data.traversal.max_depth}. Increase depth/limit to see more.
              </div>
            )}

            {/* Upstream sections */}
            <Section title="Direct Callers" count={data.summary.direct_callers} variant="upstream" defaultOpen>
              {data.direct_callers.map(e => (
                <EntityRow key={e.id} entity={e} onNavigate={onNavigateToNode} />
              ))}
            </Section>

            <Section title="Indirect Callers" count={data.summary.indirect_callers} variant="upstream">
              {data.indirect_callers.map(e => (
                <EntityRow key={e.id} entity={e} onNavigate={onNavigateToNode} />
              ))}
            </Section>

            {/* Downstream sections */}
            <Section title="Direct Callees" count={data.summary.direct_callees} variant="downstream" defaultOpen>
              {data.direct_callees.map(e => (
                <EntityRow key={e.id} entity={e} onNavigate={onNavigateToNode} />
              ))}
            </Section>

            <Section title="Indirect Callees" count={data.summary.indirect_callees} variant="downstream">
              {data.indirect_callees.map(e => (
                <EntityRow key={e.id} entity={e} onNavigate={onNavigateToNode} />
              ))}
            </Section>

            {/* Containers */}
            <Section title="Affected Files" count={data.summary.affected_files} variant="neutral">
              <div className="space-y-1">
                {data.affected_files.map(f => (
                  <p key={f} className="text-gray-400 text-xs font-mono truncate">{f}</p>
                ))}
              </div>
            </Section>

            <Section title="Affected Modules" count={data.summary.affected_modules} variant="neutral">
              <div className="space-y-1">
                {data.affected_modules.map(m => (
                  <p key={m} className="text-gray-400 text-xs font-mono truncate">{m}</p>
                ))}
              </div>
            </Section>

            {/* Unresolved */}
            <Section title="Unresolved References" count={data.summary.unresolved_references} variant="unresolved">
              <p className="text-gray-600 text-xs mb-2">These call targets could not be statically resolved. They may or may not be impacted.</p>
              {data.unresolved_references.map(e => (
                <EntityRow key={e.id} entity={e} onNavigate={onNavigateToNode} />
              ))}
            </Section>

            {/* Traversal metadata */}
            <div className="p-4 border-t border-gray-800 mt-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-600 mb-2">Traversal Info</div>
              <div className="space-y-1 text-xs">
                {[
                  ['Nodes visited', data.traversal.nodes_visited],
                  ['Depth reached', data.traversal.actual_depth_reached],
                  ['Max depth', data.traversal.max_depth],
                  ['Source', 'Deterministic (Neo4j BFS)'],
                ].map(([k, v]) => (
                  <div key={String(k)} className="flex justify-between">
                    <span className="text-gray-600">{k}</span>
                    <span className="text-gray-400 font-mono">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
