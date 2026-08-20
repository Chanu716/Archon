import React, { useState } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, GitCommit as GitIcon, Activity, Box, Search, ExternalLink, Zap, Terminal } from 'lucide-react'
import AnalystPanel from '@/components/AnalystPanel'
import type {
  InvestigationBaseResponse,
  GitContext,
  ImpactContext,
  EvolutionContext,
  SemanticContext
} from '@/types/investigation'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export default function IntelligenceWorkbench() {
  const { repoId } = useParams<{ repoId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const entityId = searchParams.get('entity_id')
  const snapshotId = searchParams.get('snapshot_id')
  
  const [isAnalystOpen, setIsAnalystOpen] = useState(false)

  // 1. Base Context Query
  const { data: base, isLoading: baseLoading, error: baseError } = useQuery<InvestigationBaseResponse>({
    queryKey: ['investigation-base', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (!res.ok) throw new Error('Failed to load investigation context')
      return res.json()
    },
    enabled: !!repoId && !!entityId,
  })

  // 2. Lazy Git Context
  const { data: git } = useQuery<GitContext>({
    queryKey: ['investigation-git', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}/git`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (res.status === 404) return null
      return res.json()
    },
    enabled: !!base,
  })

  // 3. Lazy Impact Context
  const { data: impact } = useQuery<ImpactContext>({
    queryKey: ['investigation-impact', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}/impact`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (!res.ok) return { direct_callers: 0, indirect_callers: 0, direct_callees: 0, indirect_callees: 0, affected_entities: 0, graph: { nodes: [], edges: [] } }
      return res.json()
    },
    enabled: !!base,
  })

  // 4. Lazy Evolution Context
  const { data: evolution } = useQuery<EvolutionContext>({
    queryKey: ['investigation-evolution', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}/evolution`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (!res.ok) return { lifecycle: null, relationship_changes: [], drift_findings: [] }
      return res.json()
    },
    enabled: !!base,
  })
  
  // 5. Lazy Semantic Context
  const { data: semantic } = useQuery<SemanticContext>({
    queryKey: ['investigation-semantic', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}/semantic`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (res.status === 404) return null
      return res.json()
    },
    enabled: !!base,
  })

  if (!repoId || !entityId) {
    return (
      <div className="min-h-screen bg-black text-white p-8 font-mono crt-grid">
        <div className="pixel-box p-6 max-w-xl mx-auto text-center space-y-4">
          <Terminal className="w-8 h-8 text-neutral-500 mx-auto" />
          <h2 className="font-pixel text-sm text-white">[ MISSING_ENTITY_IDENTIFIER ]</h2>
          <p className="text-xs text-neutral-400">Select an entity from the Architecture Graph to open in the Workbench.</p>
          <button
            onClick={() => navigate(`/repositories/${repoId || ''}/architecture`)}
            className="pixel-btn-filled-cyan text-xs"
          >
            [ OPEN_ARCHITECTURE_GRAPH ]
          </button>
        </div>
      </div>
    )
  }

  if (baseLoading) {
    return (
      <div className="min-h-screen bg-black text-cyan-400 font-pixel p-12 flex items-center justify-center animate-pulse">
        [ ASSEMBLING_MULTI-DIMENSIONAL_DOSSIER… ]
      </div>
    )
  }

  if (baseError || !base) {
    return (
      <div className="min-h-screen bg-black text-white p-8 font-mono crt-grid">
        <div className="pixel-box p-6 border-red-500 max-w-xl mx-auto text-center space-y-4">
          <h2 className="font-pixel text-sm text-red-400">[ INVESTIGATION_FAILED ]</h2>
          <p className="text-xs text-neutral-400">{String(baseError)}</p>
          <button
            onClick={() => navigate(`/repositories/${repoId}/architecture`)}
            className="pixel-btn text-xs"
          >
            ← [ RETURN_TO_ARCHITECTURE ]
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-10 font-mono crt-grid flex flex-col">
      {/* Header */}
      <div className="max-w-7xl w-full mx-auto mb-6 border-b-2 border-white pb-4 flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate(`/repositories/${repoId}/architecture`)}
            className="text-xs text-neutral-400 hover:text-cyan-400 transition-colors inline-flex items-center gap-1 mb-2"
          >
            ← [ BACK_TO_ARCHITECTURE ]
          </button>
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Archon Logo"
              className="w-7 h-7 object-contain filter drop-shadow-[0_0_8px_rgba(6,182,212,0.8)]"
            />
            <h1 className="font-pixel text-xl text-white tracking-wide">
              {base.context.entity_name}
            </h1>
            <span className="pixel-tag-cyan text-[10px]">
              [{base.context.entity_type}]
            </span>
          </div>
          <p className="text-xs text-neutral-400 font-mono mt-1">{base.context.qualified_name || base.context.file_path}</p>
        </div>
        
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => navigate(`/repositories/${repoId}/architecture?node=${encodeURIComponent(entityId)}`)}
            className="pixel-btn text-xs flex items-center gap-1.5"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            [ VIEW_IN_GRAPH ]
          </button>
          <button
            onClick={() => setIsAnalystOpen(true)}
            className="pixel-btn-filled-cyan text-xs flex items-center gap-1.5"
          >
            <Zap className="w-3.5 h-3.5" />
            [ ASK_ANALYST ]
          </button>
        </div>
      </div>

      <div className="max-w-7xl w-full mx-auto space-y-6 flex-1">
        {/* Overview Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <StatCard label="COMPLEXITY" value={base.overview.complexity ?? 'N/A'} />
          <StatCard label="COUPLING" value={base.overview.coupling ?? 'N/A'} />
          <StatCard label="RISK_SCORE" value={base.overview.risk ?? 'N/A'} highlight={(base.overview.risk ?? 0) > 0.7} />
          <StatCard label="GIT_CHURN" value={git?.churn ?? 'N/A'} icon={<GitIcon className="w-3.5 h-3.5 text-neutral-500" />} />
          <StatCard label="CALLERS" value={base.overview.callers ?? 'N/A'} />
          <StatCard label="CALLEES" value={base.overview.callees ?? 'N/A'} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Code & Git */}
          <div className="flex flex-col space-y-6">
            <div className="pixel-box overflow-hidden">
              <div className="py-2.5 px-3.5 border-b border-neutral-800 flex items-center gap-2 font-pixel text-xs text-white">
                <Box className="w-3.5 h-3.5 text-cyan-400" />
                <span>[ SOURCE_AST_CODE ]</span>
              </div>
              <div className="overflow-auto max-h-[360px] bg-black p-3 text-xs font-mono">
                {base.code ? (
                  <pre className="text-cyan-300 leading-relaxed m-0 whitespace-pre-wrap">
                    <code>{base.code.source_code}</code>
                  </pre>
                ) : (
                  <div className="text-neutral-500 text-xs italic">Source code block not attached.</div>
                )}
              </div>
            </div>
            
            <div className="pixel-box p-4">
              <div className="flex items-center gap-2 font-pixel text-xs text-white border-b border-neutral-800 pb-2.5 mb-3">
                <GitIcon className="w-3.5 h-3.5 text-cyan-400" />
                <span>[ GIT_HISTORY ]</span>
              </div>
              {!git ? (
                <div className="text-xs text-neutral-500">Loading git history telemetry…</div>
              ) : (
                <div className="space-y-2.5 text-xs">
                  <div className="flex justify-between text-[11px] text-neutral-400">
                    <span>TOTAL_COMMITS:</span>
                    <span className="text-cyan-400 font-bold font-mono">{git.commit_count}</span>
                  </div>
                  <div className="text-[10px] font-pixel text-neutral-500 uppercase mt-2">[ RECENT_REVISIONS ]</div>
                  <ul className="space-y-2 divide-y divide-neutral-900">
                    {git.recent_commits.map(c => (
                      <li key={c.sha} className="pt-2">
                        <div className="font-mono text-cyan-400 text-[11px]">{c.sha.substring(0, 7)}</div>
                        <div className="text-neutral-200 truncate text-xs">{c.message}</div>
                        <div className="text-neutral-500 text-[10px]">{c.author} • {new Date(c.date).toLocaleDateString()}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Middle Column: Health & Impact */}
          <div className="flex flex-col space-y-6">
            <div className="pixel-box p-4">
              <div className="flex items-center gap-2 font-pixel text-xs text-white border-b border-neutral-800 pb-2.5 mb-3">
                <Activity className="w-3.5 h-3.5 text-green-400" />
                <span>[ ENTITY_HEALTH_FACTORS ]</span>
              </div>
              {base.health && Object.keys(base.health.metrics).length > 0 ? (
                <div className="space-y-1.5 text-xs">
                  {Object.entries(base.health.metrics).map(([key, val]) => (
                    <div key={key} className="flex justify-between items-center py-1 border-b border-neutral-900">
                      <span className="text-neutral-400 uppercase text-[11px]">{key.replace(/_/g, ' ')}</span>
                      <span className="font-mono text-white font-bold">{typeof val === 'number' ? val.toFixed(2).replace('.00', '') : val}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-neutral-500">No entity-specific health metrics computed.</div>
              )}
            </div>
            
            <div className="pixel-box p-4 flex-1">
              <div className="font-pixel text-xs text-amber-400 border-b border-neutral-800 pb-2.5 mb-3">
                [ IMPACT_SUMMARY ]
              </div>
              {!impact ? (
                <div className="text-xs text-neutral-500">Computing impact propagation…</div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div className="border border-neutral-800 bg-neutral-950 p-3 text-center">
                    <div className="text-xl font-bold font-mono text-amber-400">{impact.affected_entities}</div>
                    <div className="text-[9px] font-pixel text-neutral-500 uppercase mt-1">AFFECTED_NODES</div>
                  </div>
                  <div className="border border-neutral-800 bg-neutral-950 p-3 text-center">
                    <div className="text-xl font-bold font-mono text-cyan-400">{impact.direct_callers + impact.indirect_callers}</div>
                    <div className="text-[9px] font-pixel text-neutral-500 uppercase mt-1">TOTAL_CALLERS</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Evolution & Semantic */}
          <div className="flex flex-col space-y-6">
            <div className="pixel-box p-4">
              <div className="font-pixel text-xs text-purple-400 border-b border-neutral-800 pb-2.5 mb-3">
                [ EVOLUTION_&_DRIFT ]
              </div>
              {!evolution ? (
                <div className="text-xs text-neutral-500">Loading evolution state…</div>
              ) : (
                <div className="space-y-3 text-xs">
                  {evolution.lifecycle && (
                    <div className="flex justify-between items-center">
                      <span className="text-neutral-400">STATE:</span>
                      <span className="pixel-tag-cyan">{evolution.lifecycle.state}</span>
                    </div>
                  )}
                  {(evolution.drift_findings ?? []).length > 0 && (
                    <div className="space-y-1.5">
                      <span className="font-pixel text-[9px] text-red-400 uppercase">[ DRIFT_ALERTS ]</span>
                      {(evolution.drift_findings ?? []).map((d, i) => (
                        <div key={i} className="border border-red-500/50 bg-red-950/20 p-2 text-red-300 text-[11px]">
                          {d.description}
                        </div>
                      ))}
                    </div>
                  )}
                  {(evolution.relationship_changes ?? []).length > 0 && (
                    <div className="space-y-1">
                      <span className="font-pixel text-[9px] text-neutral-500 uppercase">[ EDGE_DELTA ]</span>
                      {(evolution.relationship_changes ?? []).map((r, i) => (
                        <div key={i} className="text-[11px] font-mono text-neutral-300 truncate">
                          <span className="text-cyan-400">[{r.state}]</span> {r.source_qname} → {r.target_qname}
                        </div>
                      ))}
                    </div>
                  )}
                  {(evolution.drift_findings ?? []).length === 0 && (evolution.relationship_changes ?? []).length === 0 && (
                    <div className="text-neutral-500 text-xs">No structural mutations in this snapshot.</div>
                  )}
                </div>
              )}
            </div>

            <div className="pixel-box p-4 flex-1">
              <div className="flex items-center gap-2 font-pixel text-xs text-white border-b border-neutral-800 pb-2.5 mb-3">
                <Search className="w-3.5 h-3.5 text-cyan-400" />
                <span>[ SEMANTIC_NEIGHBORS ]</span>
              </div>
              {!semantic ? (
                <div className="text-xs text-neutral-500">Querying vector embeddings…</div>
              ) : (
                <ul className="space-y-2 text-xs">
                  {semantic.related_entities.length > 0 ? semantic.related_entities.map((r, i) => (
                    <li key={i} className="flex justify-between items-center py-1 border-b border-neutral-900">
                      <div className="truncate flex-1 font-mono text-neutral-200">{r.name}</div>
                      <span className="pixel-tag-cyan text-[10px] shrink-0 font-mono ml-2">
                        {(r.similarity * 100).toFixed(0)}%
                      </span>
                    </li>
                  )) : (
                    <div className="text-neutral-500 text-xs italic">No semantic neighbors indexed.</div>
                  )}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>

      {isAnalystOpen && (
        <div className="fixed top-0 right-0 bottom-0 z-50 h-screen">
          <AnalystPanel repoId={repoId!} onClose={() => setIsAnalystOpen(false)} />
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, highlight = false, icon }: { label: string, value: string | number, highlight?: boolean, icon?: React.ReactNode }) {
  return (
    <div className={`pixel-box p-3 ${highlight ? 'border-red-500 bg-red-950/20' : ''}`}>
      <div className="flex items-center text-[9px] font-pixel text-neutral-500 uppercase mb-1 space-x-1">
        {icon}
        <span>{label}</span>
      </div>
      <div className={`text-xl font-bold font-mono ${highlight ? 'text-red-400' : 'text-white'}`}>
        {value}
      </div>
    </div>
  )
}
