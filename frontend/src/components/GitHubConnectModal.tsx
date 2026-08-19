import { useState, useEffect, useCallback } from 'react'
import { Github, Lock, Globe, Star, Search, X, RefreshCw, Zap, AlertTriangle } from 'lucide-react'

interface GitHubRepo {
  id: number
  name: string
  full_name: string
  description: string
  private: boolean
  language: string
  clone_url: string
  html_url: string
  updated_at: string
  stargazers_count: number
}

interface GitHubConnectModalProps {
  onClose: () => void
  onImport: (cloneUrl: string, githubToken: string) => void
  githubToken: string | null
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export default function GitHubConnectModal({ onClose, onImport, githubToken }: GitHubConnectModalProps) {
  const [repos, setRepos] = useState<GitHubRepo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [importing, setImporting] = useState<number | null>(null)
  const [filter, setFilter] = useState<'all' | 'public' | 'private'>('all')

  const fetchRepos = useCallback(async (token: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/github/repos?token=${encodeURIComponent(token)}&per_page=100`)
      if (res.status === 401) {
        setError('GitHub token expired. Please reconnect.')
        return
      }
      if (!res.ok) throw new Error(`Failed to fetch repos: ${res.status}`)
      const data = await res.json()
      setRepos(Array.isArray(data) ? data : [])
    } catch (e: any) {
      setError(e.message || 'Failed to load GitHub repositories')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (githubToken) {
      fetchRepos(githubToken)
    }
  }, [githubToken, fetchRepos])

  const handleConnect = () => {
    window.location.href = `${API_BASE}/auth/github`
  }

  const handleImport = async (repo: GitHubRepo) => {
    if (!githubToken) return
    setImporting(repo.id)
    try {
      await onImport(repo.clone_url, githubToken)
    } finally {
      setImporting(null)
    }
  }

  const filtered = repos.filter(r => {
    const matchSearch = r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.full_name.toLowerCase().includes(search.toLowerCase()) ||
      (r.description || '').toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === 'all' || (filter === 'private' ? r.private : !r.private)
    return matchSearch && matchFilter
  })

  const LANG_COLORS: Record<string, string> = {
    TypeScript: '#3178c6', JavaScript: '#f1e05a', Python: '#3572A5',
    Go: '#00ADD8', Rust: '#dea584', Java: '#b07219', 'C++': '#f34b7d',
    Ruby: '#701516', PHP: '#4F5D95', Swift: '#ffac45',
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="w-full max-w-2xl bg-black border-2 border-white shadow-pixel font-mono text-xs flex flex-col max-h-[85vh]">

        {/* Header */}
        <div className="p-4 border-b-2 border-white flex items-center justify-between bg-neutral-950">
          <div className="flex items-center gap-2">
            <Github className="w-4 h-4 text-cyan-400" />
            <span className="font-pixel text-[11px] text-white">[ GITHUB_CONNECT ]</span>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-white border border-neutral-700 hover:border-white p-1 transition">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {!githubToken ? (
          /* Not connected state */
          <div className="flex-1 flex flex-col items-center justify-center gap-6 p-10">
            <Github className="w-12 h-12 text-neutral-600" />
            <div className="text-center space-y-2">
              <p className="font-pixel text-[11px] text-white">CONNECT YOUR GITHUB ACCOUNT</p>
              <p className="text-neutral-500 text-[11px] leading-relaxed">
                Import public and private repositories directly.<br />
                We only request <span className="text-cyan-400">repo</span> and <span className="text-cyan-400">read:user</span> scopes.
              </p>
            </div>
            <button
              onClick={handleConnect}
              className="flex items-center gap-2 bg-white text-black px-6 py-2.5 font-pixel text-[11px] hover:bg-cyan-400 transition border-2 border-white shadow-pixel-sm"
            >
              <Github className="w-4 h-4" />
              AUTHORIZE WITH GITHUB
            </button>
            <p className="text-neutral-600 text-[10px]">
              Token stored locally in your browser only. Never sent to Archon servers.
            </p>
          </div>
        ) : (
          /* Connected — repo picker */
          <>
            {/* Search + filter bar */}
            <div className="p-3 border-b border-neutral-800 bg-neutral-950 flex gap-2">
              <div className="flex-1 flex items-center gap-2 border border-neutral-700 bg-black px-2 py-1.5">
                <Search className="w-3 h-3 text-neutral-500 flex-shrink-0" />
                <input
                  type="text"
                  placeholder="Search repositories..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="bg-transparent outline-none text-white text-[11px] font-mono placeholder-neutral-600 w-full"
                  autoFocus
                />
              </div>
              <div className="flex border border-neutral-700">
                {(['all', 'public', 'private'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`px-2.5 py-1.5 text-[10px] font-pixel uppercase transition ${
                      filter === f ? 'bg-white text-black' : 'text-neutral-500 hover:text-white'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <button
                onClick={() => fetchRepos(githubToken)}
                disabled={loading}
                className="border border-neutral-700 px-2 hover:border-cyan-400 hover:text-cyan-400 text-neutral-500 transition"
                title="Refresh"
              >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Stats bar */}
            <div className="px-3 py-1.5 bg-neutral-950 border-b border-neutral-800 flex gap-4 text-[10px] text-neutral-500">
              <span>{repos.length} total</span>
              <span className="text-cyan-400">{repos.filter(r => !r.private).length} public</span>
              <span className="text-yellow-400">{repos.filter(r => r.private).length} private</span>
              {search && <span className="text-white">{filtered.length} matching</span>}
            </div>

            {/* Repo list */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center p-12 gap-2 text-neutral-500">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span className="font-pixel text-[10px]">FETCHING REPOSITORIES...</span>
                </div>
              ) : error ? (
                <div className="flex items-center justify-center p-12 gap-2 text-red-400">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="text-[11px]">{error}</span>
                </div>
              ) : filtered.length === 0 ? (
                <div className="flex items-center justify-center p-12 text-neutral-600 font-pixel text-[10px]">
                  NO_REPOS_FOUND
                </div>
              ) : (
                <div className="divide-y divide-neutral-900">
                  {filtered.map(repo => (
                    <div
                      key={repo.id}
                      className="flex items-center gap-3 px-4 py-3 hover:bg-neutral-950 transition group"
                    >
                      {/* Lock / Globe icon */}
                      <div className="flex-shrink-0">
                        {repo.private
                          ? <Lock className="w-3 h-3 text-yellow-400" />
                          : <Globe className="w-3 h-3 text-neutral-500" />
                        }
                      </div>

                      {/* Repo info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-white font-mono text-[12px] font-semibold truncate">{repo.name}</span>
                          {repo.private && (
                            <span className="text-[9px] font-pixel px-1 py-0.5 border border-yellow-400/50 text-yellow-400">PRIVATE</span>
                          )}
                        </div>
                        {repo.description && (
                          <p className="text-neutral-500 text-[10px] truncate mt-0.5">{repo.description}</p>
                        )}
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-neutral-600">
                          {repo.language && (
                            <span className="flex items-center gap-1">
                              <span
                                className="w-2 h-2 rounded-full inline-block"
                                style={{ background: LANG_COLORS[repo.language] || '#888' }}
                              />
                              {repo.language}
                            </span>
                          )}
                          {repo.stargazers_count > 0 && (
                            <span className="flex items-center gap-1">
                              <Star className="w-2.5 h-2.5" />
                              {repo.stargazers_count}
                            </span>
                          )}
                          <span>{new Date(repo.updated_at).toLocaleDateString()}</span>
                        </div>
                      </div>

                      {/* Import button */}
                      <button
                        onClick={() => handleImport(repo)}
                        disabled={importing === repo.id}
                        className="flex-shrink-0 flex items-center gap-1.5 border border-cyan-400/50 text-cyan-400 px-3 py-1.5 text-[10px] font-pixel hover:bg-cyan-400 hover:text-black transition opacity-0 group-hover:opacity-100 disabled:opacity-50"
                      >
                        {importing === repo.id ? (
                          <RefreshCw className="w-3 h-3 animate-spin" />
                        ) : (
                          <Zap className="w-3 h-3" />
                        )}
                        {importing === repo.id ? 'IMPORTING' : 'IMPORT'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-3 border-t border-neutral-800 bg-neutral-950 flex justify-between items-center text-[10px] text-neutral-600">
              <span>Showing {filtered.length} of {repos.length} repos</span>
              <button
                onClick={() => {
                  localStorage.removeItem('github_token')
                  window.location.reload()
                }}
                className="text-red-400/60 hover:text-red-400 transition"
              >
                Disconnect GitHub
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
