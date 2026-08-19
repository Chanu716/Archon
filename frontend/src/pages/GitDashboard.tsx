import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { formatDistanceToNow } from 'date-fns'
import { GitBranch, GitCommit, Users, Flame, AlertCircle } from 'lucide-react'

function RiskBadge({ label, score }: { label: string; score?: number }) {
  const colors: Record<string, string> = {
    CRITICAL: 'border-red-500 text-red-400 bg-red-950/60',
    HIGH:     'border-orange-500 text-orange-400 bg-orange-950/60',
    MODERATE: 'border-amber-500 text-amber-400 bg-amber-950/60',
    LOW:      'border-green-500 text-green-400 bg-green-950/60',
  }
  
  return (
    <span className={`text-[10px] px-2 py-0.5 border font-pixel ${colors[label] || 'border-neutral-700 text-neutral-400'}`}>
      [{label}] {score !== undefined && `(${score.toFixed(2)})`}
    </span>
  )
}

export default function GitDashboard() {
  const { repoId } = useParams<{ repoId: string }>()

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['gitOverview', repoId],
    queryFn: () => api.getGitOverview(repoId!),
    enabled: !!repoId,
  })

  const { data: hotspots } = useQuery({
    queryKey: ['gitHotspots', repoId],
    queryFn: () => api.getGitHotspots(repoId!),
    enabled: !!repoId && overview?.git_available,
  })

  const { data: recentFiles } = useQuery({
    queryKey: ['gitFilesRecent', repoId],
    queryFn: () => api.getGitFiles(repoId!, 'recent', 5),
    enabled: !!repoId && overview?.git_available,
  })

  const { data: churnedFiles } = useQuery({
    queryKey: ['gitFilesChurn', repoId],
    queryFn: () => api.getGitFiles(repoId!, 'churn', 5),
    enabled: !!repoId && overview?.git_available,
  })

  const { data: commits } = useQuery({
    queryKey: ['gitCommits', repoId],
    queryFn: () => api.getGitCommits(repoId!, 5),
    enabled: !!repoId && overview?.git_available,
  })

  const { data: contributors } = useQuery({
    queryKey: ['gitContributors', repoId],
    queryFn: () => api.getGitContributors(repoId!),
    enabled: !!repoId && overview?.git_available,
  })

  if (overviewLoading) {
    return (
      <div className="min-h-screen bg-black text-cyan-400 font-pixel p-12 flex items-center justify-center animate-pulse">
        [ COMPUTING_GIT_HISTORY_MATRIX… ]
      </div>
    )
  }

  if (overview && !overview.git_available) {
    return (
      <div className="min-h-screen bg-black text-white p-8 font-mono crt-grid">
        <div className="pixel-box p-6 border-amber-500 max-w-xl mx-auto text-center space-y-4">
          <AlertCircle className="w-8 h-8 text-amber-400 mx-auto" />
          <h2 className="font-pixel text-sm text-amber-400">[ GIT_ANALYSIS_NOT_AVAILABLE ]</h2>
          <p className="text-xs text-neutral-400">Git analysis is not available for this target repository.</p>
          <Link to={`/repositories/${repoId}/overview`} className="pixel-btn text-xs inline-block">
            ← [ RETURN_TO_OVERVIEW ]
          </Link>
        </div>
      </div>
    )
  }

  const hotspotList = Array.isArray(hotspots) ? hotspots : []
  const recentFileList = Array.isArray(recentFiles) ? recentFiles : []
  const churnedFileList = Array.isArray(churnedFiles) ? churnedFiles : []
  const contributorList = Array.isArray(contributors) ? contributors : []
  const commitList = Array.isArray(commits) ? commits : []

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-10 font-mono crt-grid">
      {/* Top Header */}
      <div className="max-w-6xl mx-auto mb-8 border-b-2 border-white pb-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <Link
            to={`/repositories/${repoId}/overview`}
            className="text-xs text-neutral-400 hover:text-cyan-400 transition-colors inline-flex items-center gap-1 mb-2"
          >
            ← [ BACK_TO_OVERVIEW ]
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="font-pixel text-xl text-white tracking-wide">
              GIT_INTELLIGENCE_MATRIX
            </h1>
            <span className="pixel-tag-cyan text-[10px]">
              HEAD: {overview?.snapshot_commit_sha?.substring(0, 8) || 'N/A'}
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto space-y-6">
        {/* Top metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="pixel-box p-4">
            <span className="text-[10px] text-neutral-500 font-pixel uppercase block mb-1">COMMITS_ANALYZED</span>
            <div className="text-2xl font-bold font-mono text-cyan-400">{overview?.total_commits ?? 0}</div>
          </div>
          <div className="pixel-box p-4">
            <span className="text-[10px] text-neutral-500 font-pixel uppercase block mb-1">CONTRIBUTORS</span>
            <div className="text-2xl font-bold font-mono text-purple-400">{overview?.total_contributors ?? 0}</div>
          </div>
        </div>

        {/* Hotspots */}
        <div className="pixel-box p-5">
          <div className="flex justify-between items-center border-b border-neutral-800 pb-3 mb-4">
            <div className="flex items-center gap-2 font-pixel text-xs text-amber-400">
              <Flame className="w-4 h-4" />
              <span>[ RISK_HOTSPOTS :: CHURN_COUPLING ]</span>
            </div>
            <span className="text-[10px] text-neutral-500 font-mono">Heuristic v1</span>
          </div>
          <div className="divide-y divide-neutral-900">
            {hotspotList.length === 0 && (
              <div className="py-4 text-xs text-neutral-500">No critical risk hotspots detected.</div>
            )}
            {hotspotList.map((h: any) => (
              <div key={h.file_path} className="py-2.5 flex items-center justify-between hover:bg-neutral-950">
                <div className="font-mono text-xs text-neutral-200 truncate max-w-lg">{h.file_path}</div>
                <RiskBadge label={h.risk_label} score={h.risk_score} />
              </div>
            ))}
          </div>
        </div>

        {/* Recent & Churned Files */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="pixel-box p-5">
            <div className="font-pixel text-xs text-white border-b border-neutral-800 pb-3 mb-3">
              [ RECENTLY_CHANGED_FILES ]
            </div>
            <div className="divide-y divide-neutral-900">
              {recentFileList.map((f: any) => (
                <div key={f.file_path} className="py-2.5 flex items-center justify-between">
                  <div className="truncate max-w-[240px]">
                    <div className="font-mono text-xs text-neutral-200 truncate" title={f.file_path}>{f.file_path}</div>
                    <div className="text-[10px] text-neutral-500 mt-0.5">
                      {f.commit_count} commits • {f.last_changed_at ? formatDistanceToNow(new Date(f.last_changed_at), { addSuffix: true }) : 'unknown'}
                    </div>
                  </div>
                  <span className="pixel-tag text-[10px] text-neutral-300">
                    {f.insertions + f.deletions} churn
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="pixel-box p-5">
            <div className="font-pixel text-xs text-white border-b border-neutral-800 pb-3 mb-3">
              [ MOST_CHURNED_FILES ]
            </div>
            <div className="divide-y divide-neutral-900">
              {churnedFileList.map((f: any) => (
                <div key={f.file_path} className="py-2.5 flex items-center justify-between">
                  <div className="truncate max-w-[240px]">
                    <div className="font-mono text-xs text-neutral-200 truncate" title={f.file_path}>{f.file_path}</div>
                    <div className="text-[10px] text-neutral-500 mt-0.5">
                      <span className="text-green-400">+{f.insertions}</span> <span className="text-red-400">-{f.deletions}</span>
                    </div>
                  </div>
                  <span className="pixel-tag text-[10px] text-cyan-400">
                    {f.churn} churn
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Contributors Table */}
        <div className="pixel-box p-5">
          <div className="font-pixel text-xs text-white border-b border-neutral-800 pb-3 mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-cyan-400" />
            <span>[ REPOSITORY_CONTRIBUTORS ]</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead className="text-[10px] font-pixel text-neutral-500 border-b border-neutral-800">
                <tr>
                  <th className="py-2 px-3">AUTHOR</th>
                  <th className="py-2 px-3">COMMITS</th>
                  <th className="py-2 px-3">FILES</th>
                  <th className="py-2 px-3">LINES (+)</th>
                  <th className="py-2 px-3">LINES (-)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-900 text-neutral-300">
                {contributorList.map((c: any) => (
                  <tr key={c.author_email} className="hover:bg-neutral-950">
                    <td className="py-2.5 px-3 font-medium text-white">
                      {c.author_name}
                      <div className="text-[10px] text-neutral-500">{c.author_email}</div>
                    </td>
                    <td className="py-2.5 px-3 text-cyan-400 font-bold">{c.commit_count}</td>
                    <td className="py-2.5 px-3 text-neutral-300">{c.files_touched}</td>
                    <td className="py-2.5 px-3 text-green-400">+{c.insertions}</td>
                    <td className="py-2.5 px-3 text-red-400">-{c.deletions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Commits */}
        <div className="pixel-box p-5">
          <div className="font-pixel text-xs text-white border-b border-neutral-800 pb-3 mb-3 flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-cyan-400" />
            <span>[ RECENT_COMMITS ]</span>
          </div>
          <div className="divide-y divide-neutral-900">
            {commitList.map((c: any) => (
              <div key={c.sha} className="py-2.5 hover:bg-neutral-950">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-cyan-400 text-xs font-bold">{c.sha.substring(0, 8)}</span>
                  <span className="text-neutral-200 text-xs">{c.author_name}</span>
                  <span className="text-neutral-500 text-[10px] ml-auto">
                    {formatDistanceToNow(new Date(c.committed_at), { addSuffix: true })}
                  </span>
                </div>
                <div className="text-xs text-neutral-400 font-mono truncate">{c.message.split('\n')[0]}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
