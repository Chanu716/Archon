import React from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { Activity, ShieldAlert, Cpu, AlertTriangle, ArrowLeft, Terminal } from 'lucide-react'

interface HealthData {
  repository_id: string
  snapshot_id: string
  commit_sha: string
  health: {
    total_modules: number
    total_classes: number
    total_functions: number
    average_complexity: number
    maximum_complexity: number
    circular_dependencies: number
    high_complexity_functions: number
    high_coupling_modules: number
  }
}

export const HealthDashboard: React.FC = () => {
  const { id } = useParams<{ id: string }>()

  const { data, isLoading, error } = useQuery<HealthData>({
    queryKey: ['health', id],
    queryFn: async () => {
      const response = await apiClient.get(`/api/v1/metrics/${id}/health`)
      return response.data
    },
  })

  if (isLoading) {
    return (
      <div className="min-h-screen bg-black text-cyan-400 font-pixel p-12 flex items-center justify-center animate-pulse">
        [ COMPUTING_CODEBASE_HEALTH_TELEMETRY… ]
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-black text-white p-8 font-mono crt-grid">
        <div className="pixel-box p-6 border-red-500 max-w-xl mx-auto text-center space-y-4">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto" />
          <h2 className="font-pixel text-sm text-red-400">[ HEALTH_TELEMETRY_UNAVAILABLE ]</h2>
          <p className="text-xs text-neutral-400">Run repository analysis first to generate health metrics snapshot.</p>
          <Link to={`/repositories/${id}/overview`} className="pixel-btn text-xs inline-block">
            ← [ RETURN_TO_OVERVIEW ]
          </Link>
        </div>
      </div>
    )
  }

  const { health } = data

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-10 font-mono crt-grid">
      {/* Top Header */}
      <div className="max-w-6xl mx-auto mb-8 border-b-2 border-white pb-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <Link
            to={`/repositories/${id}/overview`}
            className="text-xs text-neutral-400 hover:text-cyan-400 transition-colors inline-flex items-center gap-1 mb-2"
          >
            ← [ BACK_TO_OVERVIEW ]
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="font-pixel text-xl text-white tracking-wide">
              CODEBASE_HEALTH_RADAR
            </h1>
            <span className="pixel-tag-cyan text-[10px]">SNAPSHOT_ID: {data.snapshot_id?.slice(0, 8) || 'LATEST'}</span>
          </div>
          <p className="text-xs text-neutral-400 font-mono mt-1">Commit: {data.commit_sha || 'HEAD'}</p>
        </div>

        <div className="flex items-center gap-2">
          <Link to={`/repositories/${id}/architecture`} className="pixel-btn-cyan text-xs">
            [ 🌌 ARCHITECTURE_GRAPH ]
          </Link>
        </div>
      </div>

      <div className="max-w-6xl mx-auto space-y-8">
        {/* Structural Metrics */}
        <div>
          <div className="font-pixel text-xs text-neutral-400 mb-3 uppercase">
            [ 01 :: STRUCTURAL_TOPOLOGY ]
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard title="TOTAL_FILES" value={health.total_modules} />
            <MetricCard title="TOTAL_CLASSES" value={health.total_classes} />
            <MetricCard title="TOTAL_FUNCTIONS" value={health.total_functions} />
            <MetricCard
              title="CIRCULAR_CYCLES"
              value={health.circular_dependencies}
              alert={health.circular_dependencies > 0}
            />
          </div>
        </div>

        {/* Complexity & Risk Metrics */}
        <div>
          <div className="font-pixel text-xs text-neutral-400 mb-3 uppercase">
            [ 02 :: COMPLEXITY_&_RISK_FACTORS ]
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard title="AVG_CYCLOMATIC_CC" value={typeof health.average_complexity === 'number' ? health.average_complexity.toFixed(2) : health.average_complexity} />
            <MetricCard
              title="MAX_CYCLOMATIC_CC"
              value={health.maximum_complexity}
              alert={health.maximum_complexity > 15}
            />
            <MetricCard
              title="HIGH_CC_FUNCS"
              value={health.high_complexity_functions}
              alert={health.high_complexity_functions > 0}
            />
            <MetricCard
              title="HIGH_COUPLING_MODS"
              value={health.high_coupling_modules}
              alert={health.high_coupling_modules > 0}
            />
          </div>
        </div>

        {/* Informational Terminal Banner */}
        <div className="pixel-box p-5 space-y-2">
          <div className="flex items-center gap-2 font-pixel text-xs text-cyan-400 border-b border-neutral-800 pb-2">
            <Terminal className="w-4 h-4" />
            <span>[ DETERMINISTIC_METRIC_ENGINE ]</span>
          </div>
          <p className="text-xs text-neutral-400 leading-relaxed font-mono">
            Metrics are computed directly from the AST parser and Neo4j topological graph traversal.
            To inspect specific entity blast radius and call paths, launch the Architecture Graph or Intelligence Workbench.
          </p>
        </div>
      </div>
    </div>
  )
}

const MetricCard: React.FC<{ title: string; value: string | number; alert?: boolean }> = ({ title, value, alert }) => (
  <div className={`pixel-box p-4 ${alert ? 'border-red-500 bg-red-950/20' : ''}`}>
    <span className="text-[10px] text-neutral-500 font-pixel uppercase block mb-1">{title}</span>
    <div className={`text-2xl font-bold font-mono ${alert ? 'text-red-400 animate-pulse' : 'text-white'}`}>
      {value}
    </div>
  </div>
)
