import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { useState } from 'react'
import { Box, Activity, GitBranch, TrendingUp, Search, Terminal, Play, ShieldAlert, Cpu } from 'lucide-react'

export default function OverviewPage() {
  const { repoId } = useParams<{ repoId: string }>()
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)

  const { data: repo } = useQuery({
    queryKey: ['repository', repoId],
    queryFn: () => api.getRepositories().then(repos => repos.find((r: any) => r.id === repoId)),
    enabled: !!repoId,
  })

  const { data: jobStatus } = useQuery({
    queryKey: ['jobStatus', currentJobId],
    queryFn: () => api.getJobStatus(currentJobId!),
    enabled: !!currentJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed') return false
      return 3000
    },
    refetchIntervalInBackground: false,
  })

  const analyzeMutation = useMutation({
    mutationFn: () => api.analyzeRepository(repoId!),
    onSuccess: (data) => {
      setCurrentJobId(data.id)
    },
  })

  if (!repo) {
    return (
      <div className="min-h-screen bg-black text-cyan-400 font-pixel p-12 flex items-center justify-center animate-pulse">
        [ LOADING REPOSITORY METADATA… ]
      </div>
    )
  }

  const isAnalyzed = !!(repo.has_snapshot || repo.last_analyzed_at)

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-10 font-mono crt-grid">
      {/* Top Bar Navigation */}
      <div className="max-w-6xl mx-auto mb-8 border-b-2 border-white pb-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <Link
            to="/repositories"
            className="text-xs text-neutral-400 hover:text-cyan-400 transition-colors inline-flex items-center gap-1 mb-2"
          >
            ← [ BACK_TO_REPOSITORIES ]
          </Link>
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Archon Logo"
              className="w-7 h-7 object-contain filter drop-shadow-[0_0_8px_rgba(6,182,212,0.8)]"
            />
            <h1 className="font-pixel text-xl text-white tracking-wide">
              {repo.name}
            </h1>
            <span className="pixel-tag-cyan text-[10px]">
              {repo.source_type?.toUpperCase() || 'GIT'}
            </span>
          </div>
          <p className="text-xs text-neutral-400 font-mono mt-1">{repo.source_url}</p>
        </div>

        <button
          onClick={() => analyzeMutation.mutate()}
          disabled={analyzeMutation.isPending || (jobStatus && jobStatus.status === 'running')}
          className="pixel-btn-filled-cyan flex items-center gap-2 self-start md:self-auto disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          {jobStatus?.status === 'running' ? 'ANALYZING_AST…' : 'TRIGGER_ANALYSIS'}
        </button>
      </div>

      <div className="max-w-6xl mx-auto space-y-6">
        {/* Real-time Analysis Terminal HUD */}
        {jobStatus && (
          <div className="pixel-box-cyan p-5">
            <div className="flex items-center justify-between border-b border-cyan-900/60 pb-2 mb-3">
              <div className="flex items-center gap-2 font-pixel text-xs text-cyan-400">
                <Terminal className="w-4 h-4 animate-spin" />
                <span>[ PIPELINE_STATUS :: {jobStatus.status?.toUpperCase()} ]</span>
              </div>
              <span className="text-[11px] text-cyan-300 font-mono">
                {Math.round(jobStatus.progress || 0)}%
              </span>
            </div>

            <p className="text-xs text-neutral-300 mb-3">
              CURRENT_STAGE: <span className="text-cyan-400 font-bold">{jobStatus.current_stage || 'Initializing parser'}</span>
            </p>

            {/* Stepped Pixel Progress Bar */}
            <div className="w-full bg-neutral-900 border border-neutral-700 h-4 p-0.5 relative overflow-hidden">
              <div
                className="bg-cyan-400 h-full transition-all duration-300 shadow-glow-cyan"
                style={{ width: `${Math.max(2, jobStatus.progress || 0)}%` }}
              />
            </div>

            {jobStatus.error_message && (
              <p className="mt-3 p-2 bg-red-950/60 border border-red-500 text-red-400 text-xs">
                [ERROR] {jobStatus.error_message}
              </p>
            )}
          </div>
        )}

        {/* Quick Navigation Modules Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to={`/repositories/${repoId}/architecture`}
            className={`pixel-box p-5 hover:border-cyan-400 transition-colors flex flex-col justify-between group ${!isAnalyzed ? 'opacity-50 pointer-events-none' : ''}`}
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <Box className="w-6 h-6 text-cyan-400 group-hover:scale-110 transition-transform" />
                <span className="pixel-tag text-[9px]">[ MODULE_01 ]</span>
              </div>
              <h3 className="font-pixel text-sm text-white mb-1 group-hover:text-cyan-400 transition-colors">
                ARCHITECTURE GRAPH
              </h3>
              <p className="text-xs text-neutral-400 font-mono">
                Interactive 3D Galaxy & 2D Planar AST code dependency topology.
              </p>
            </div>
            <div className="mt-4 text-xs font-pixel text-cyan-400 flex items-center gap-1">
              <span>LAUNCH VIEW</span> →
            </div>
          </Link>

          <Link
            to={`/repositories/${repoId}/health`}
            className="pixel-box p-5 hover:border-cyan-400 transition-colors flex flex-col justify-between group"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <Activity className="w-6 h-6 text-green-400 group-hover:scale-110 transition-transform" />
                <span className="pixel-tag text-[9px]">[ MODULE_02 ]</span>
              </div>
              <h3 className="font-pixel text-sm text-white mb-1 group-hover:text-green-400 transition-colors">
                CODE HEALTH RADAR
              </h3>
              <p className="text-xs text-neutral-400 font-mono">
                Cyclomatic complexity, circular dependencies, and risk metrics.
              </p>
            </div>
            <div className="mt-4 text-xs font-pixel text-green-400 flex items-center gap-1">
              <span>LAUNCH VIEW</span> →
            </div>
          </Link>

          <Link
            to={`/repositories/${repoId}/investigation`}
            className="pixel-box p-5 hover:border-cyan-400 transition-colors flex flex-col justify-between group"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <Search className="w-6 h-6 text-purple-400 group-hover:scale-110 transition-transform" />
                <span className="pixel-tag text-[9px]">[ MODULE_03 ]</span>
              </div>
              <h3 className="font-pixel text-sm text-white mb-1 group-hover:text-purple-400 transition-colors">
                INTELLIGENCE WORKBENCH
              </h3>
              <p className="text-xs text-neutral-400 font-mono">
                Deep semantic querying, symbol indexing, and entity investigation.
              </p>
            </div>
            <div className="mt-4 text-xs font-pixel text-purple-400 flex items-center gap-1">
              <span>LAUNCH VIEW</span> →
            </div>
          </Link>
        </div>

        {/* Repository Specs Detail Card */}
        <div className="pixel-box p-6">
          <div className="flex items-center justify-between border-b border-neutral-800 pb-3 mb-4">
            <h2 className="font-pixel text-xs text-white">[ SYSTEM_METADATA ]</h2>
            <Cpu className="w-4 h-4 text-neutral-500" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div className="border border-neutral-800 bg-neutral-950 p-3">
              <span className="text-neutral-500 block text-[10px] uppercase font-pixel mb-1">TARGET_UUID</span>
              <span className="text-neutral-200 font-mono select-all text-[11px]">{repo.id}</span>
            </div>

            <div className="border border-neutral-800 bg-neutral-950 p-3">
              <span className="text-neutral-500 block text-[10px] uppercase font-pixel mb-1">SOURCE_TYPE</span>
              <span className="text-cyan-400 font-mono uppercase">{repo.source_type || 'GITHUB'}</span>
            </div>

            <div className="border border-neutral-800 bg-neutral-950 p-3">
              <span className="text-neutral-500 block text-[10px] uppercase font-pixel mb-1">SNAPSHOT_STATUS</span>
              <span className={isAnalyzed ? 'text-green-400 font-mono' : 'text-neutral-400 font-mono'}>
                {isAnalyzed ? 'ACTIVE_SNAPSHOT' : 'UNANALYZED'}
              </span>
            </div>

            <div className="border border-neutral-800 bg-neutral-950 p-3">
              <span className="text-neutral-500 block text-[10px] uppercase font-pixel mb-1">LAST_SYNC</span>
              <span className="text-neutral-300 font-mono">
                {repo.last_analyzed_at ? new Date(repo.last_analyzed_at).toLocaleString() : 'NEVER'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
