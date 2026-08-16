import React, { useState, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2, GitCommit as GitIcon, Activity, Box, Search, ExternalLink } from 'lucide-react'
import AnalystPanel from '@/components/AnalystPanel'
import type {
  InvestigationBaseResponse,
  GitContext,
  ImpactContext,
  EvolutionContext,
  SemanticContext
} from '@/types/investigation'

// Ensure we have an API base URL
const API_BASE = 'http://localhost:8000/api/v1'

const Badge = ({ children, variant, className = '' }: any) => <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${className}`}>{children}</span>;
const Card = ({ children, className = '' }: any) => <div className={`border rounded-lg bg-white shadow-sm ${className}`}>{children}</div>;

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
    enabled: !!repoId && !!entityId
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
    enabled: !!base && !!base.context.file_path // Only fetch if we have a file path
  })

  // 3. Lazy Impact Context
  const { data: impact } = useQuery<ImpactContext>({
    queryKey: ['investigation-impact', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}/impact`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (res.status === 404) return null
      return res.json()
    },
    enabled: !!base
  })

  // 4. Lazy Evolution Context
  const { data: evolution } = useQuery<EvolutionContext>({
    queryKey: ['investigation-evolution', repoId, entityId, snapshotId],
    queryFn: async () => {
      let url = `${API_BASE}/${repoId}/investigation/${encodeURIComponent(entityId!)}/evolution`
      if (snapshotId) url += `?snapshot_id=${snapshotId}`
      const res = await fetch(url)
      if (res.status === 404) return null
      return res.json()
    },
    enabled: !!base
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
    enabled: !!base
  })

  if (!repoId || !entityId) {
    return <div className="p-8">Missing repository or entity context.</div>
  }

  if (baseLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  if (baseError || !base) {
    return <div className="p-8 text-red-500">Error loading investigation: {String(baseError)}</div>
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-6 flex flex-col">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <button 
            onClick={() => navigate(`/repositories/${repoId}/architecture`)}
            className="flex items-center text-sm text-slate-500 hover:text-slate-900 dark:hover:text-slate-100 mb-2"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Architecture
          </button>
          <div className="flex items-center space-x-3">
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {base.context.entity_name}
            </h1>
            <Badge variant="outline" className="text-xs uppercase bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
              {base.context.entity_type}
            </Badge>
          </div>
          <p className="text-sm text-slate-500 mt-1 font-mono">{base.context.qualified_name || base.context.file_path}</p>
        </div>
        
        <div className="flex space-x-3">
          <button
            onClick={() => navigate(`/repositories/${repoId}/architecture?node=${encodeURIComponent(entityId)}`)}
            className="inline-flex items-center px-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            <ExternalLink className="w-4 h-4 mr-2" />
            View in Graph
          </button>
          <button
            onClick={() => setIsAnalystOpen(true)}
            className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 shadow-sm"
          >
            <Search className="w-4 h-4 mr-2" />
            Ask Archon
          </button>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
        <StatCard label="Complexity" value={base.overview.complexity ?? 'N/A'} />
        <StatCard label="Coupling" value={base.overview.coupling ?? 'N/A'} />
        <StatCard label="Risk Score" value={base.overview.risk ?? 'N/A'} highlight={(base.overview.risk ?? 0) > 0.7} />
        <StatCard label="Git Churn" value={git?.churn ?? 'N/A'} icon={<GitIcon className="w-4 h-4 text-slate-400" />} />
        <StatCard label="Callers" value={base.overview.callers ?? 'N/A'} />
        <StatCard label="Callees" value={base.overview.callees ?? 'N/A'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1">
        
        {/* Left Column: Code & Git */}
        <div className="flex flex-col space-y-6">
          <div className="flex-1 border rounded-lg bg-white shadow-sm overflow-hidden">
            <div className="py-3 px-4 border-b">
              <h3 className="text-sm font-medium flex items-center">
                <Box className="w-4 h-4 mr-2 text-indigo-500" />
                Source Code
              </h3>
            </div>
            <div className="overflow-auto max-h-[400px]">
              {base.code ? (
                <pre className="p-4 text-xs font-mono bg-slate-950 text-slate-50 m-0">
                  <code>{base.code.source_code}</code>
                </pre>
              ) : (
                <div className="p-4 text-sm text-slate-500">Source code not available for this entity.</div>
              )}
            </div>
          </div>
          
          <div className="border rounded-lg bg-white shadow-sm">
            <div className="py-3 px-4 border-b">
              <h3 className="text-sm font-medium flex items-center">
                <GitIcon className="w-4 h-4 mr-2 text-indigo-500" />
                Git History
              </h3>
            </div>
            <div className="p-4">
              {!git ? (
                <div className="text-sm text-slate-500">Git history loading or unavailable.</div>
              ) : (
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-500">Total Commits:</span>
                    <span className="font-medium">{git.commit_count}</span>
                  </div>
                  <div className="text-xs font-medium text-slate-900 dark:text-slate-100 mt-4 mb-2">Recent Commits</div>
                  <ul className="space-y-2">
                    {git.recent_commits.map(c => (
                      <li key={c.sha} className="text-xs border-l-2 border-indigo-200 pl-2">
                        <div className="font-mono text-slate-500">{c.sha.substring(0,7)}</div>
                        <div className="truncate">{c.message}</div>
                        <div className="text-slate-400 mt-0.5">{c.author} • {new Date(c.date).toLocaleDateString()}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Middle Column: Health & Impact */}
        <div className="flex flex-col space-y-6">
          <div className="border rounded-lg bg-white shadow-sm">
            <div className="py-3 px-4 border-b">
              <h3 className="text-sm font-medium flex items-center">
                <Activity className="w-4 h-4 mr-2 text-indigo-500" />
                Health Metrics
              </h3>
            </div>
            <div className="p-4">
              {base.health && Object.keys(base.health.metrics).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(base.health.metrics).map(([key, val]) => (
                    <div key={key} className="flex justify-between items-center text-sm border-b border-slate-100 dark:border-slate-800 pb-2">
                      <span className="text-slate-600 dark:text-slate-400 font-medium capitalize">{key.replace(/_/g, ' ')}</span>
                      <span className="font-mono bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">{typeof val === 'number' ? val.toFixed(2).replace('.00', '') : val}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-500">No health metrics available.</div>
              )}
            </div>
          </div>
          
          <div className="border rounded-lg bg-white shadow-sm flex-1">
            <div className="py-3 px-4 border-b">
              <h3 className="text-sm font-medium">Impact Analysis</h3>
            </div>
            <div className="p-4">
              {!impact ? (
                <div className="text-sm text-slate-500">Loading impact...</div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border text-center">
                    <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{impact.affected_entities}</div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider">Affected Entities</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border text-center">
                    <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{impact.direct_callers + impact.indirect_callers}</div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider">Total Callers</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Evolution & Semantic */}
        <div className="flex flex-col space-y-6">
          <div className="border rounded-lg bg-white shadow-sm">
            <div className="py-3 px-4 border-b">
              <h3 className="text-sm font-medium flex items-center">
                <Activity className="w-4 h-4 mr-2 text-indigo-500" />
                Evolution & Drift
              </h3>
            </div>
            <div className="p-4">
              {!evolution ? (
                <div className="text-sm text-slate-500">Loading evolution...</div>
              ) : (
                <div className="space-y-4">
                  {evolution.lifecycle && (
                    <div className="text-sm">
                      Lifecycle State: <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-gray-100">{evolution.lifecycle.state}</span>
                    </div>
                  )}
                  {evolution.drift_findings.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-red-600 mb-2 uppercase">Drift Findings</div>
                      <ul className="space-y-2">
                        {evolution.drift_findings.map((d, i) => (
                          <li key={i} className="text-sm bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 p-2 rounded">
                            {d.description}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {evolution.relationship_changes.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-slate-500 mb-2 uppercase">Dependency Changes</div>
                      <ul className="space-y-1">
                        {evolution.relationship_changes.map((r, i) => (
                          <li key={i} className="text-xs flex items-center space-x-2">
                            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${r.state === 'ADDED' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'}`}>
                              {r.state}
                            </span>
                            <span className="truncate">{r.source_qname} → {r.target_qname}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {evolution.drift_findings.length === 0 && evolution.relationship_changes.length === 0 && (
                    <div className="text-sm text-slate-500">No significant structural changes in this snapshot.</div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="border rounded-lg bg-white shadow-sm flex-1">
            <div className="py-3 px-4 border-b">
              <h3 className="text-sm font-medium flex items-center">
                <Search className="w-4 h-4 mr-2 text-indigo-500" />
                Semantic Neighbors
              </h3>
            </div>
            <div className="p-4">
              {!semantic ? (
                <div className="text-sm text-slate-500">Loading semantic relations...</div>
              ) : (
                <ul className="space-y-3">
                  {semantic.related_entities.length > 0 ? semantic.related_entities.map((r, i) => (
                    <li key={i} className="flex justify-between items-center text-sm">
                      <div className="truncate flex-1 font-medium">{r.name}</div>
                      <span className="ml-2 font-mono text-[10px] shrink-0 bg-slate-100 px-1.5 py-0.5 rounded">
                        {(r.similarity * 100).toFixed(0)}% match
                      </span>
                    </li>
                  )) : (
                    <div className="text-sm text-slate-500">No semantic neighbors found.</div>
                  )}
                </ul>
              )}
            </div>
          </div>
        </div>

      </div>

      {isAnalystOpen && (
        <AnalystPanel repoId={repoId!} onClose={() => setIsAnalystOpen(false)} />
      )}
    </div>
  )
}

function StatCard({ label, value, highlight = false, icon }: { label: string, value: string | number, highlight?: boolean, icon?: React.ReactNode }) {
  return (
    <Card className={`overflow-hidden ${highlight ? 'border-red-200 bg-red-50 dark:bg-red-900/10 dark:border-red-800' : ''}`}>
      <div className="p-3">
        <div className="flex items-center text-xs text-slate-500 font-medium uppercase tracking-wider mb-1 space-x-1">
          {icon}
          <span>{label}</span>
        </div>
        <div className={`text-2xl font-bold ${highlight ? 'text-red-700 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'}`}>
          {value}
        </div>
      </div>
    </Card>
  )
}
