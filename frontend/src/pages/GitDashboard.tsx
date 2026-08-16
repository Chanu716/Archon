import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { formatDistanceToNow } from 'date-fns'

function RiskBadge({ label, score }: { label: string; score?: number }) {
  const colors: Record<string, string> = {
    CRITICAL: 'bg-red-900/40 text-red-400 border border-red-700/40',
    HIGH:     'bg-orange-900/40 text-orange-400 border border-orange-700/40',
    MODERATE: 'bg-yellow-900/40 text-yellow-400 border border-yellow-700/40',
    LOW:      'bg-green-900/40 text-green-400 border border-green-700/40',
  }
  
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-mono ${colors[label] || 'bg-gray-800 text-gray-500'}`}>
      {label} {score !== undefined && `(${score.toFixed(2)})`}
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
    return <div className="p-8 text-gray-400">Loading Git Intelligence...</div>
  }

  if (overview && !overview.git_available) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-white mb-4">Git Intelligence</h1>
        <div className="bg-yellow-900/20 border border-yellow-800 rounded p-4 text-yellow-300">
          Git analysis is not available for this repository. It may have been imported from a non-Git source.
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 flex-col overflow-y-auto">
      {/* Header */}
      <div className="p-4 border-b border-gray-800 flex items-center justify-between sticky top-0 bg-gray-950/80 backdrop-blur z-10">
        <div className="flex items-center gap-4">
          <Link to={`/repositories/${repoId}/overview`} className="text-gray-500 hover:text-white text-sm">← Back</Link>
          <h1 className="text-xl font-bold text-white">Git Intelligence</h1>
        </div>
        <div className="text-sm text-gray-500 font-mono">
          Snapshot Cutoff: {overview?.snapshot_commit_sha?.substring(0, 8)}
        </div>
      </div>

      <div className="p-6 max-w-6xl mx-auto w-full space-y-6">
        
        {/* Top metrics */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-gray-900 border border-gray-800 rounded p-4">
            <div className="text-sm text-gray-500 mb-1 uppercase tracking-wide font-semibold">Commits Analyzed</div>
            <div className="text-2xl font-bold font-mono text-blue-400">{overview?.total_commits}</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded p-4">
            <div className="text-sm text-gray-500 mb-1 uppercase tracking-wide font-semibold">Contributors</div>
            <div className="text-2xl font-bold font-mono text-purple-400">{overview?.total_contributors}</div>
          </div>
        </div>

        {/* Hotspots */}
        <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex justify-between items-center bg-gray-900/50">
            <h2 className="font-semibold text-gray-200">Archon Risk Hotspots</h2>
            <span className="text-xs text-gray-500">Based on Risk Heuristic v1 (Complexity + Coupling + Churn)</span>
          </div>
          <div className="divide-y divide-gray-800">
            {hotspots?.length === 0 && (
              <div className="p-4 text-sm text-gray-500">No critical or high-risk files detected.</div>
            )}
            {hotspots?.map((h: any) => (
              <div key={h.file_path} className="p-4 flex items-center justify-between hover:bg-gray-800/50">
                <div className="font-mono text-sm text-gray-300">{h.file_path}</div>
                <RiskBadge label={h.risk_label} score={h.risk_score} />
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Recently Changed */}
          <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/50">
              <h2 className="font-semibold text-gray-200">Recently Changed Files</h2>
            </div>
            <div className="divide-y divide-gray-800">
              {recentFiles?.map((f: any) => (
                <div key={f.file_path} className="p-4 flex items-center justify-between hover:bg-gray-800/50">
                  <div>
                    <div className="font-mono text-sm text-gray-300 truncate max-w-sm" title={f.file_path}>{f.file_path}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {f.commit_count} commits • {f.last_changed_at ? formatDistanceToNow(new Date(f.last_changed_at), { addSuffix: true }) : 'unknown'}
                    </div>
                  </div>
                  <div className="text-xs font-mono text-gray-400 bg-gray-800 px-2 py-1 rounded">
                    {f.insertions + f.deletions} churn
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Most Churned */}
          <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/50">
              <h2 className="font-semibold text-gray-200">Most Churned Files</h2>
            </div>
            <div className="divide-y divide-gray-800">
              {churnedFiles?.map((f: any) => (
                <div key={f.file_path} className="p-4 flex items-center justify-between hover:bg-gray-800/50">
                  <div>
                    <div className="font-mono text-sm text-gray-300 truncate max-w-sm" title={f.file_path}>{f.file_path}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      <span className="text-green-500/80">+{f.insertions}</span> <span className="text-red-500/80">-{f.deletions}</span>
                    </div>
                  </div>
                  <div className="text-xs font-mono text-gray-400 bg-gray-800 px-2 py-1 rounded flex items-center gap-2">
                    <span>{f.churn} churn</span>
                    <span className="text-gray-600">({(f.normalized_churn * 100).toFixed(0)}%)</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Contributors */}
        <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/50">
            <h2 className="font-semibold text-gray-200">Contributors</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-500 uppercase bg-gray-800/50">
                <tr>
                  <th className="px-4 py-3">Author</th>
                  <th className="px-4 py-3">Commits</th>
                  <th className="px-4 py-3">Files Touched</th>
                  <th className="px-4 py-3">Insertions</th>
                  <th className="px-4 py-3">Deletions</th>
                  <th className="px-4 py-3">Last Active</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 text-gray-300">
                {contributors?.map((c: any) => (
                  <tr key={c.author_email} className="hover:bg-gray-800/50">
                    <td className="px-4 py-3 font-medium">
                      {c.author_name}
                      <div className="text-xs text-gray-600 font-normal">{c.author_email}</div>
                    </td>
                    <td className="px-4 py-3 font-mono text-blue-400">{c.commit_count}</td>
                    <td className="px-4 py-3 font-mono">{c.files_touched}</td>
                    <td className="px-4 py-3 font-mono text-green-500/80">+{c.insertions}</td>
                    <td className="px-4 py-3 font-mono text-red-500/80">-{c.deletions}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {c.last_commit_at ? formatDistanceToNow(new Date(c.last_commit_at), { addSuffix: true }) : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Commits */}
        <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/50">
            <h2 className="font-semibold text-gray-200">Recent Commits</h2>
          </div>
          <div className="divide-y divide-gray-800">
            {commits?.map((c: any) => (
              <div key={c.sha} className="p-4 hover:bg-gray-800/50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-blue-400 text-sm">{c.sha.substring(0, 8)}</span>
                  <span className="text-gray-300 text-sm font-medium">{c.author_name}</span>
                  <span className="text-gray-600 text-xs flex-1">
                    {formatDistanceToNow(new Date(c.committed_at), { addSuffix: true })}
                  </span>
                </div>
                <div className="text-sm text-gray-400 truncate">{c.message.split('\n')[0]}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
