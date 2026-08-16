import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

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
}

export default function EntityDetailsPanel({ repoId, node, onClose, onAnalyzeImpact }: EntityDetailsPanelProps) {
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

  const typeColor = typeColors[entityType] || 'text-gray-300'

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

  // Also show key AST properties stored directly on the node
  const nodeProps: { label: string; value: string | number | undefined }[] = [
    { label: 'Type', value: entityType },
    { label: 'Path', value: node.path },
    { label: 'Lines', value: node.line_count !== undefined ? `${node.cyclomatic_complexity !== undefined ? node.cyclomatic_complexity : '?'} CC / ${node.line_count} lines` : undefined },
    { label: 'End Line', value: node.end_line },
    { label: 'Language', value: node.language },
  ]

  return (
    <div className="w-96 bg-gray-900 border-l border-gray-700 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex justify-between items-start">
        <div className="overflow-hidden">
          <div className={`text-xs font-semibold uppercase tracking-wide mb-1 ${typeColor}`}>{entityType}</div>
          <h2 className="text-white font-bold text-sm truncate" title={node.label}>{node.label}</h2>
          {node.qualified_name && node.qualified_name !== node.label && (
            <p className="text-gray-500 text-xs mt-1 truncate" title={node.qualified_name}>{node.qualified_name}</p>
          )}
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white ml-2 flex-shrink-0 text-lg leading-none">✕</button>
      </div>

      {/* Investigation and Impact triggers */}
      <div className="px-4 py-2 border-b border-gray-800 flex-shrink-0 space-y-2">
        <button
          onClick={() => navigate(`/repositories/${repoId}/investigation?entity_id=${encodeURIComponent(node.id)}`)}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white text-xs py-1.5 rounded transition font-medium"
        >
          🔍 Open Investigation
        </button>
        {onAnalyzeImpact && (
          <button
            onClick={() => onAnalyzeImpact(node.id, node.label)}
            className="w-full bg-orange-700/20 hover:bg-orange-700/40 border border-orange-700/40 text-orange-300 text-xs py-1.5 rounded transition font-medium"
          >
            ⚡ Analyze Impact
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Docstring */}
        {node.docstring && (
          <div className="p-4 border-b border-gray-800">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Docstring</div>
            <p className="text-gray-300 text-xs leading-relaxed italic">"{node.docstring}"</p>
          </div>
        )}

        {/* Node Properties */}
        <div className="p-4 border-b border-gray-800">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">Properties</div>
          <div className="space-y-2">
            {nodeProps.map(prop =>
              prop.value !== undefined && prop.value !== null ? (
                <div key={prop.label} className="flex justify-between text-xs">
                  <span className="text-gray-500">{prop.label}</span>
                  <span className="text-gray-300 font-mono text-right max-w-[55%] truncate" title={String(prop.value)}>{prop.value}</span>
                </div>
              ) : null
            )}
          </div>
        </div>

        {/* Metrics */}
        {(entityType === 'Function' || entityType === 'Class' || entityType === 'Module') && (
          <div className="p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">Deterministic Metrics</div>
            {isLoading && <p className="text-gray-500 text-xs">Loading metrics...</p>}
            {!isLoading && metricRows.length === 0 && (
              <p className="text-gray-600 text-xs italic">No metrics available for this entity yet. Run analysis first.</p>
            )}
            {metricRows.length > 0 && (
              <div className="space-y-2">
                {metricRows.map(row => (
                  <div key={row.name} className="flex justify-between text-xs items-center">
                    <span className="text-gray-400">{row.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-white font-mono font-semibold">{row.value}</span>
                      <span className={`text-xs px-1 rounded ${row.source === 'deterministic' ? 'bg-blue-900/40 text-blue-400' : 'bg-orange-900/40 text-orange-400'}`}>
                        {row.source === 'deterministic' ? 'DET' : 'HEU'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 pt-3 border-t border-gray-800">
              <div className="flex gap-4 text-xs text-gray-600">
                <div className="flex items-center gap-1"><span className="px-1 bg-blue-900/40 text-blue-400 rounded">DET</span> Deterministic</div>
                <div className="flex items-center gap-1"><span className="px-1 bg-orange-900/40 text-orange-400 rounded">HEU</span> Heuristic</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
