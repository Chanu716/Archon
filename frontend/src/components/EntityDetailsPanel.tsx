import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Sparkles, Search, Zap, X } from 'lucide-react'

interface MetricRow {
  name: string
  value: string | number
  source: string
}

interface EntityDetailsPanelProps {
  repoId: string
  node: {
    id: string
    type: string
    label: string
    qualified_name?: string
    path?: string
    docstring?: string
    line_count?: number
    end_line?: number
    cyclomatic_complexity?: number
    nesting_depth?: number
    [key: string]: any
  }
  onClose: () => void
  onAnalyzeImpact?: (nodeId: string, nodeName: string) => void
  onExpandNode?: (nodeId: string) => void
}

export default function EntityDetailsPanel({
  repoId,
  node,
  onClose,
  onAnalyzeImpact,
  onExpandNode,
}: EntityDetailsPanelProps) {
  const navigate = useNavigate()
  const entityType = node.type
  const entityName = node.qualified_name || node.path || node.label

  const { data: metricsData, isLoading } = useQuery({
    queryKey: ['entityMetrics', repoId, entityType, entityName],
    queryFn: () => api.getEntityMetrics(repoId, entityType, entityName),
    enabled: !!entityName && (entityType === 'Function' || entityType === 'Class' || entityType === 'Module'),
    retry: false,
  })

  const typeColors: Record<string, string> = {
    Repository: 'text-yellow-400',
    Directory: 'text-orange-400',
    File: 'text-indigo-400',
    Module: 'text-blue-400',
    Class: 'text-green-400',
    Function: 'text-pink-400',
    Method: 'text-purple-400',
  }

  const typeColor = typeColors[entityType] || 'text-cyan-400'

  const metricRows: MetricRow[] = []
  if (metricsData?.metrics) {
    const { metrics, sources } = metricsData
    const displayNames: Record<string, string> = {
      cyclomatic_complexity: 'Cyclomatic Complexity',
      nesting_depth: 'Nesting Depth',
      line_count: 'Line Count',
      fan_in: 'Fan-in (Callers)',
      fan_out: 'Fan-out (Calls)',
      incoming_coupling: 'Incoming Coupling',
      outgoing_coupling: 'Outgoing Coupling',
      circular_dependencies: 'Circular Dependencies',
      normalized_complexity: 'Normalized Complexity',
      normalized_coupling: 'Normalized Coupling',
      risk_score: 'Archon Risk Score',
      risk_label: 'Risk Classification',
    }
    const labelMap: Record<number, string> = { 0: 'LOW', 1: 'MODERATE', 2: 'HIGH', 3: 'CRITICAL' }
    for (const [key, val] of Object.entries(metrics)) {
      let displayValue = typeof val === 'number' ? (Number.isInteger(val) ? val : (val as number).toFixed(3)) : String(val)
      if (key === 'risk_label' && typeof val === 'number') {
        displayValue = labelMap[val] || 'UNKNOWN'
      }
      metricRows.push({
        name: displayNames[key] || key,
        value: displayValue,
        source: sources?.[key] || 'deterministic',
      })
    }
  }

  const nodeProps: { label: string; value: string | number | undefined }[] = [
    { label: 'TYPE', value: entityType },
    { label: 'PATH', value: node.path },
    { label: 'COMPLEXITY_LINES', value: node.line_count !== undefined ? `${node.cyclomatic_complexity !== undefined ? node.cyclomatic_complexity : '?'} CC / ${node.line_count} lines` : undefined },
    { label: 'END_LINE', value: node.end_line },
    { label: 'LANGUAGE', value: node.language },
  ]

  return (
    <div className="w-96 flex-shrink-0 bg-black border-l-2 border-white flex flex-col h-full overflow-hidden shadow-pixel z-30 font-mono text-xs">
      {/* Header */}
      <div className="p-3.5 border-b-2 border-white flex justify-between items-start bg-neutral-950">
        <div className="overflow-hidden">
          <div className={`font-pixel text-[10px] uppercase tracking-wider mb-1 ${typeColor}`}>
            [ {entityType} ]
          </div>
          <h2 className="text-white font-bold text-sm truncate font-mono" title={node.label}>
            {node.label}
          </h2>
          {node.qualified_name && node.qualified_name !== node.label && (
            <p className="text-neutral-400 text-[11px] mt-0.5 truncate font-mono" title={node.qualified_name}>
              {node.qualified_name}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-neutral-400 hover:text-white p-1 border border-neutral-800 hover:border-white transition flex-shrink-0 text-xs"
          title="Close Inspector"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Cyber Actions Section */}
      <div className="p-3 border-b border-neutral-800 flex-shrink-0 space-y-2 bg-neutral-950">
        {onExpandNode && (
          <button
            onClick={() => onExpandNode(node.id)}
            className="w-full pixel-btn-cyan text-[11px] py-1.5 flex items-center justify-center gap-1.5"
            title="Expand 1-hop connected child nodes"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>[ + EXPAND_CHILDREN ]</span>
          </button>
        )}
        <button
          onClick={() => navigate(`/repositories/${repoId}/investigation?entity_id=${encodeURIComponent(node.id)}`)}
          className="w-full pixel-btn text-[11px] py-1.5 flex items-center justify-center gap-1.5 hover:border-cyan-400 hover:text-cyan-400"
          title="Open in Intelligence Workbench"
        >
          <Search className="w-3.5 h-3.5" />
          <span>{"[ > OPEN_WORKBENCH ]"}</span>
        </button>
        {onAnalyzeImpact && (
          <button
            onClick={() => onAnalyzeImpact(node.id, node.label)}
            className="w-full pixel-btn text-[11px] py-1.5 flex items-center justify-center gap-1.5 text-amber-400 hover:border-amber-400"
            title="Analyze blast radius impact"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>[ ! BLAST_RADIUS ]</span>
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
        {/* Docstring */}
        {node.docstring && (
          <div className="border border-neutral-800 p-2.5 bg-neutral-950">
            <div className="font-pixel text-[9px] text-neutral-400 uppercase mb-1.5">
              [ DOCSTRING ]
            </div>
            <p className="text-neutral-300 text-xs leading-relaxed italic">
              "{node.docstring}"
            </p>
          </div>
        )}

        {/* Node Properties */}
        <div className="border border-neutral-800 p-2.5 bg-neutral-950">
          <div className="font-pixel text-[9px] text-neutral-400 uppercase mb-2">
            [ ENTITY_PROPERTIES ]
          </div>
          <div className="space-y-1.5">
            {nodeProps.map(prop =>
              prop.value !== undefined && prop.value !== null ? (
                <div key={prop.label} className="flex justify-between items-center text-[11px]">
                  <span className="text-neutral-500 font-pixel text-[9px]">{prop.label}:</span>
                  <span className="text-neutral-200 font-mono text-right max-w-[60%] truncate" title={String(prop.value)}>
                    {prop.value}
                  </span>
                </div>
              ) : null
            )}
          </div>
        </div>

        {/* Code Health Metrics */}
        {(entityType === 'Function' || entityType === 'Class' || entityType === 'Module') && (
          <div className="border border-neutral-800 p-2.5 bg-neutral-950">
            <div className="font-pixel text-[9px] text-neutral-400 uppercase mb-2">
              [ DETERMINISTIC_METRICS ]
            </div>
            {isLoading && <p className="text-cyan-400 text-[11px] animate-pulse">[ FETCHING_METRICS… ]</p>}
            {!isLoading && metricRows.length === 0 && (
              <p className="text-neutral-500 text-[11px]">No metric telemetry available.</p>
            )}
            {metricRows.length > 0 && (
              <div className="space-y-1.5">
                {metricRows.map(row => (
                  <div key={row.name} className="flex justify-between text-[11px] items-center border-b border-neutral-900 pb-1">
                    <span className="text-neutral-400 truncate max-w-[55%]">{row.name}</span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-white font-mono font-bold">{row.value}</span>
                      <span className={`text-[9px] px-1 font-pixel ${row.source === 'deterministic' ? 'bg-cyan-950 text-cyan-400 border border-cyan-800' : 'bg-amber-950 text-amber-400 border border-amber-800'}`}>
                        {row.source === 'deterministic' ? 'DET' : 'HEU'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
