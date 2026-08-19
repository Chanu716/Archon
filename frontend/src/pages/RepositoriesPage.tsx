import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { api } from '@/api/client'
import type { Repository } from '@/types'
import { Terminal, Plus, GitBranch, Box, Activity, CheckCircle, Clock, Github, CheckCheck } from 'lucide-react'
import GitHubConnectModal from '@/components/GitHubConnectModal'

export default function RepositoriesPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [url, setUrl] = useState('')
  const [showGitHubModal, setShowGitHubModal] = useState(false)
  const [githubToken, setGithubToken] = useState<string | null>(
    () => localStorage.getItem('github_token')
  )

  // On mount: extract github_token or github_error from URL query params
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const token = params.get('github_token')
    const error = params.get('github_error')

    if (token) {
      localStorage.setItem('github_token', token)
      setGithubToken(token)
      setShowGitHubModal(true)
      // Clean URL
      navigate('/repositories', { replace: true })
    } else if (error) {
      console.error('GitHub OAuth error:', error)
      navigate('/repositories', { replace: true })
    }
  }, [location.search, navigate])

  const { data: repos, isLoading } = useQuery<Repository[]>({
    queryKey: ['repositories'],
    queryFn: api.getRepositories,
  })

  const createMutation = useMutation<unknown, Error, { sourceUrl: string; githubToken?: string }>({
    mutationFn: ({ sourceUrl, githubToken }) => api.createRepository(sourceUrl, githubToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      setUrl('')
    },
  })

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (url) {
      createMutation.mutate({ sourceUrl: url })
    }
  }

  const handleGitHubImport = async (cloneUrl: string, token: string) => {
    await createMutation.mutateAsync({ sourceUrl: cloneUrl, githubToken: token })
    queryClient.invalidateQueries({ queryKey: ['repositories'] })
    setShowGitHubModal(false)
  }

  const repoList = Array.isArray(repos) ? repos : []

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-10 font-mono crt-grid">
      {/* Top Retro Terminal Header */}
      <div className="max-w-6xl mx-auto mb-8 border-b-2 border-white pb-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-cyan-400 text-black font-pixel font-bold flex items-center justify-center text-sm shadow-pixel-sm">
            A
          </div>
          <div>
            <h1 className="font-pixel text-lg md:text-xl text-white tracking-wider">
              ARCHON :: REPOSITORY_VAULT
            </h1>
            <p className="text-xs text-neutral-400 font-mono mt-0.5">
              root://archon/system_registry • codebase graph intelligence
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-2 border border-neutral-800 bg-neutral-950 px-3 py-1.5 rounded-none">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-glow-cyan" />
            <span className="font-pixel text-cyan-400 text-[10px]">CORE: ONLINE</span>
          </div>
          <div className="border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-neutral-400">
            TOTAL_REPOS: <strong className="text-white font-mono">{repoList.length}</strong>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto space-y-8">
        {/* Ingest Repository Terminal Card */}
        <div className="pixel-box p-6 relative">
          <div className="flex items-center justify-between border-b border-neutral-800 pb-3 mb-5">
            <div className="flex items-center gap-2 font-pixel text-xs text-cyan-400">
              <Terminal className="w-4 h-4" />
              <span>[ INGEST_NEW_REPOSITORY ]</span>
            </div>
            <span className="text-[10px] text-neutral-500 font-pixel">[ PROTOCOL: GIT_HTTPS ]</span>
          </div>

          <form onSubmit={handleAdd} className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <span className="absolute left-3 top-2.5 text-neutral-500 text-xs select-none">$ git clone</span>
              <input
                type="url"
                placeholder="https://github.com/org/repo"
                className="w-full pixel-input pl-28 pr-4 py-2 text-xs text-white placeholder-neutral-600 focus:outline-none"
                value={url}
                onChange={e => setUrl(e.target.value)}
                disabled={createMutation.isPending}
                required
              />
            </div>
            <button
              type="submit"
              className="pixel-btn-filled-cyan flex items-center gap-2"
              disabled={createMutation.isPending}
            >
              <Plus className="w-4 h-4" />
              {createMutation.isPending ? 'INGESTING…' : 'INGEST_REPO'}
            </button>
          </form>

          {/* GitHub Connect button */}
          <div className="mt-4 pt-4 border-t border-neutral-800 flex items-center justify-between">
            <div className="text-[10px] text-neutral-500 font-pixel">
              OR BROWSE YOUR GITHUB REPOSITORIES (INCL. PRIVATE)
            </div>
            <button
              onClick={() => setShowGitHubModal(true)}
              className={`flex items-center gap-2 border px-3 py-1.5 text-[10px] font-pixel transition ${
                githubToken
                  ? 'border-cyan-400/50 text-cyan-400 hover:bg-cyan-400 hover:text-black'
                  : 'border-neutral-600 text-neutral-400 hover:border-white hover:text-white'
              }`}
            >
              {githubToken ? <CheckCheck className="w-3 h-3" /> : <Github className="w-3 h-3" />}
              {githubToken ? 'GITHUB_CONNECTED' : 'CONNECT_GITHUB'}
            </button>
          </div>

          {createMutation.isError && (
            <div className="mt-3 p-2 bg-red-950/60 border border-red-500 text-red-400 text-xs font-mono">
              [ERROR] Failed to ingest repository: {createMutation.error.message}
            </div>
          )}
        </div>

        {/* Repository Grid */}
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs font-pixel text-neutral-400 px-1">
            <span>REGISTERED_TARGETS</span>
            <span>COUNT: {repoList.length}</span>
          </div>

          {isLoading ? (
            <div className="pixel-box p-12 text-center text-cyan-400 font-pixel text-xs animate-pulse">
              [ SCANNING REPOSITORY VAULT… ]
            </div>
          ) : repoList.length === 0 ? (
            <div className="pixel-box p-12 text-center text-neutral-500 font-mono text-xs">
              No repositories registered yet. Ingest a GitHub URL above to begin code graph analysis.
            </div>
          ) : (
            <div className="grid gap-4">
              {repoList.map(repo => {
                const isAnalyzed = !!(repo.has_snapshot || repo.last_analyzed_at)
                return (
                  <div
                    key={repo.id}
                    className="pixel-box p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-5 hover:border-cyan-400 transition-colors group"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center gap-3">
                        <h3 className="font-pixel text-sm md:text-base text-white group-hover:text-cyan-400 transition-colors">
                          {repo.name}
                        </h3>
                        {isAnalyzed ? (
                          <span className="pixel-tag-cyan flex items-center gap-1">
                            <CheckCircle className="w-3 h-3 text-cyan-400" />
                            ANALYZED
                          </span>
                        ) : (
                          <span className="pixel-tag flex items-center gap-1 text-neutral-400">
                            <Clock className="w-3 h-3" />
                            PENDING_ANALYSIS
                          </span>
                        )}
                      </div>

                      <p className="text-xs text-neutral-400 font-mono truncate max-w-xl">
                        {repo.source_url}
                      </p>

                      <div className="flex items-center gap-4 text-[11px] text-neutral-500 font-mono pt-1">
                        <span>ID: <code className="text-neutral-300">{repo.id.slice(0, 8)}…</code></span>
                        {repo.last_analyzed_at && (
                          <span>LAST_SCAN: {new Date(repo.last_analyzed_at).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex flex-wrap items-center gap-2.5">
                      <Link
                        to={`/repositories/${repo.id}/overview`}
                        className="pixel-btn text-xs hover:border-cyan-400"
                      >
                        [ OVERVIEW ]
                      </Link>

                      {isAnalyzed ? (
                        <Link
                          to={`/repositories/${repo.id}/architecture`}
                          className="pixel-btn-cyan text-xs flex items-center gap-1.5"
                        >
                          <Box className="w-3.5 h-3.5" />
                          [ 3D GALAXY ]
                        </Link>
                      ) : (
                        <span
                          className="pixel-btn opacity-40 cursor-not-allowed border-neutral-700 text-neutral-600"
                          title="Run snapshot analysis first"
                        >
                          [ 3D GALAXY ]
                        </span>
                      )}

                      {isAnalyzed && (
                        <Link
                          to={`/repositories/${repo.id}/evolution`}
                          className="pixel-btn text-xs text-neutral-300 hover:text-white"
                        >
                          [ EVOLUTION ]
                        </Link>
                      )}

                      <Link
                        to={`/repositories/${repo.id}/investigation`}
                        className="pixel-btn text-xs text-neutral-300 hover:text-cyan-400"
                      >
                        [ WORKBENCH ]
                      </Link>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* GitHub Connect Modal */}
      {showGitHubModal && (
        <GitHubConnectModal
          onClose={() => setShowGitHubModal(false)}
          onImport={handleGitHubImport}
          githubToken={githubToken}
        />
      )}
    </div>
  )
}
