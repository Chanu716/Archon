import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Zap, X, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'

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

const ResolutionBadge = ({ resolution }: { resolution: string }) => {
  const styles: Record<string, string> = {
    exact: 'border-cyan-500 text-cyan-400 bg-cyan-950/60',
    inferred: 'border-purple-500 text-purple-400 bg-purple-950/60',
    unresolved: 'border-neutral-700 text-neutral-500 bg-neutral-900',
  }
  return (
    <span className={`text-[9px] px-1.5 py-0.5 border font-pixel ${styles[resolution] ?? styles.unresolved}`}>
      [{resolution}]
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
  <div className="flex items-start gap-2 py-1.5 border-b border-neutral-900 last:border-0">
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-1.5 flex-wrap">
        <button
          className="text-neutral-200 text-xs font-mono font-bold hover:text-cyan-400 truncate max-w-[170px]"
          title={entity.qualified_name || entity.name}
          onClick={() => onNavigate?.(entity.id)}
        >
          {entity.name}
        </button>
        <ResolutionBadge resolution={entity.resolution} />
      </div>
      {entity.file && (
        <p className="text-neutral-500 text-[10px] mt-0.5 truncate font-mono">{entity.file}</p>
      )}
    </div>
    <span className="text-neutral-500 text-[10px] font-mono flex-shrink-0">d={entity.distance}</span>
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
    unresolved: 'text-neutral-500',
    neutral: 'text-neutral-400',
  }

  return (
    <div className="border-b border-neutral-800">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3.5 py-2 hover:bg-neutral-950 transition text-left"
      >
        <span className={`font-pixel text-[10px] uppercase ${headerColors[variant]}`}>
          [ {title} ]
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-neutral-300 bg-neutral-900 border border-neutral-800 px-1.5 py-0.5">
            {count}
          </span>
          <span className="text-neutral-500 text-xs">{open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}</span>
        </div>
      </button>
      {open && <div className="px-3.5 pb-2.5 bg-black/60">{children}</div>}
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

  const { data, isLoading, error } = useQuery<ImpactResult>({
    queryKey: ['impact', repoId, entityId, direction, depth],
    queryFn: () => api.getImpact(repoId, entityId, direction, depth),
    staleTime: 30_000,
  })

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
    <div className="w-96 flex-shrink-0 bg-black border-l-2 border-white flex flex-col h-full overflow-hidden shadow-pixel z-30 font-mono text-xs">
      {/* Header */}
      <div className="p-3.5 border-b-2 border-white flex justify-between items-start flex-shrink-0 bg-neutral-950">
        <div>
          <div className="font-pixel text-[10px] text-amber-400 mb-0.5">
            [ BLAST_RADIUS_ANALYSIS ]
          </div>
          <h2 className="text-white font-bold text-sm truncate font-mono" title={entityName}>
            {entityName}
          </h2>
        </div>
        <button
          onClick={onClose}
          className="text-neutral-400 hover:text-white p-1 border border-neutral-800 hover:border-white transition text-xs"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Traversal Controls */}
      <div className="p-2.5 border-b border-neutral-800 flex gap-2 flex-shrink-0 bg-neutral-950">
        <select
          value={direction}
          onChange={e => setDirection(e.target.value as typeof direction)}
          className="flex-1 pixel-input px-2 py-1 text-[11px] text-white focus:outline-none"
        >
          <option value="both" className="bg-black">BOTH DIRECTIONS</option>
          <option value="upstream" className="bg-black">UPSTREAM (CALLERS)</option>
          <option value="downstream" className="bg-black">DOWNSTREAM (CALLEES)</option>
        </select>
        <select
          value={depth}
          onChange={e => setDepth(Number(e.target.value))}
          className="pixel-input px-2 py-1 text-[11px] text-white focus:outline-none"
        >
          {[1, 2, 3, 5, 7, 10].map(d => (
            <option key={d} value={d} className="bg-black">DEPTH {d}</option>
          ))}
        </select>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto bg-black">
        {isLoading && (
          <div className="p-6 text-center text-cyan-400 font-pixel text-xs animate-pulse">
            [ TRAVERSING_GRAPH_EDGES… ]
          </div>
        )}

        {error && (
          <div className="p-3 border border-red-500 bg-red-950 text-red-400 text-xs m-3">
            [ERROR] Failed to compute blast radius.
          </div>
        )}

        {data && (
          <>
            {/* Summary Metrics */}
            <div className="p-3.5 border-b border-neutral-800">
              <div className="grid grid-cols-2 gap-2">
                {[
                  ['DIRECT_CALLERS', data.summary.direct_callers, 'text-amber-400'],
                  ['INDIRECT_CALLERS', data.summary.indirect_callers, 'text-amber-300'],
                  ['DIRECT_CALLEES', data.summary.direct_callees, 'text-cyan-400'],
                  ['INDIRECT_CALLEES', data.summary.indirect_callees, 'text-cyan-300'],
                  ['AFFECTED_FILES', data.summary.affected_files, 'text-indigo-400'],
                  ['AFFECTED_MODULES', data.summary.affected_modules, 'text-purple-400'],
                ].map(([label, val, color]) => (
                  <div key={String(label)} className="border border-neutral-800 bg-neutral-950 p-2">
                    <div className={`text-base font-bold font-mono ${color}`}>{val}</div>
                    <div className="text-neutral-500 font-pixel text-[8px] uppercase">{label}</div>
                  </div>
                ))}
              </div>

              {onHighlightNodes && (
                <button
                  onClick={handleVisualizeImpact}
                  className="mt-3 w-full pixel-btn-filled-cyan py-1.5 text-xs flex items-center justify-center gap-1.5"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>[ HIGHLIGHT_IN_GRAPH ]</span>
                </button>
              )}
            </div>

            {data.traversal.truncated && (
              <div className="m-3 p-2 border border-amber-500 bg-amber-950/40 text-amber-400 text-[11px] flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>Results capped at depth {data.traversal.actual_depth_reached}.</span>
              </div>
            )}

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

            <Section title="Affected Files" count={data.summary.affected_files} variant="neutral">
              <div className="space-y-1">
                {data.affected_files.map(f => (
                  <p key={f} className="text-neutral-400 text-[11px] font-mono truncate">{f}</p>
                ))}
              </div>
            </Section>

            <Section title="Affected Modules" count={data.summary.affected_modules} variant="neutral">
              <div className="space-y-1">
                {data.affected_modules.map(m => (
                  <p key={m} className="text-neutral-400 text-[11px] font-mono truncate">{m}</p>
                ))}
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  )
}
