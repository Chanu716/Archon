import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Search, X, Terminal, ExternalLink } from 'lucide-react'

interface SearchResult {
  entity: string
  entity_type: string
  file: string
  name: string
  similarity: number
  source_reference: string
  snapshot: string
}

interface SemanticSearchPanelProps {
  repoId: string
  onSelectResult: (nodeId: string, nodeName: string) => void
  onClose: () => void
}

export default function SemanticSearchPanel({ repoId, onSelectResult, onClose }: SemanticSearchPanelProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [searchTerm, setSearchTerm] = useState('')

  const { data: results, isLoading, error } = useQuery({
    queryKey: ['semanticSearch', repoId, searchTerm],
    queryFn: () => api.searchSemantic(repoId, searchTerm, 10),
    enabled: !!searchTerm,
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      setSearchTerm(query.trim())
    }
  }

  const getTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      Function: 'text-pink-400',
      Class: 'text-green-400',
      Module: 'text-blue-400',
      Method: 'text-purple-400'
    }
    return colors[type] || 'text-cyan-400'
  }

  return (
    <div className="w-96 bg-black border-r-2 border-white flex flex-col h-full overflow-hidden absolute left-0 z-30 shadow-pixel font-mono text-xs">
      {/* Header */}
      <div className="p-3.5 border-b-2 border-white flex justify-between items-center bg-neutral-950">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <h2 className="font-pixel text-[11px] text-white">[ SEMANTIC_SEARCH ]</h2>
        </div>
        <button
          onClick={onClose}
          className="text-neutral-400 hover:text-white p-1 border border-neutral-800 hover:border-white transition flex-shrink-0 text-xs"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Query Bar */}
      <div className="p-3 border-b border-neutral-800 bg-neutral-950">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="> e.g. where is authentication handled?"
            className="flex-1 pixel-input text-xs px-3 py-1.5 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!query.trim() || isLoading}
            className="pixel-btn-filled-cyan px-3 py-1.5"
          >
            {isLoading ? '…' : <Search className="w-3.5 h-3.5" />}
          </button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto p-3 bg-black space-y-3">
        {!searchTerm && !isLoading && (
          <div className="p-6 text-center text-neutral-500 text-xs space-y-2">
            <p>[ ENTER_NATURAL_LANGUAGE_QUERY ]</p>
            <p className="text-[11px] text-neutral-600 italic">"How are decorators parsed?"</p>
          </div>
        )}

        {isLoading && (
          <div className="p-6 text-center text-cyan-400 font-pixel text-xs animate-pulse">
            [ EMBEDDING_QUERY & SEARCHING VECTORS… ]
          </div>
        )}

        {error && (
          <div className="p-3 border border-red-500 bg-red-950/40 text-red-400 text-xs">
            [ERROR] Semantic search failed. Check embedding provider config.
          </div>
        )}

        {results && results.length === 0 && (
          <div className="p-6 text-center text-neutral-500 text-xs">
            [ NO_SEMANTIC_MATCHES_ABOVE_THRESHOLD ]
          </div>
        )}

        {results && results.length > 0 && (
          <div className="space-y-2.5">
            {results.map((res: SearchResult, idx: number) => (
              <div
                key={`${res.entity}-${idx}`}
                className="border border-neutral-800 hover:border-cyan-400 bg-neutral-950 p-3 cursor-pointer transition-colors group"
                onClick={() => onSelectResult(res.entity, res.name)}
              >
                <div className="flex justify-between items-start mb-1">
                  <div className="overflow-hidden pr-2">
                    <span className={`font-pixel text-[9px] uppercase mr-1.5 ${getTypeColor(res.entity_type)}`}>
                      [{res.entity_type}]
                    </span>
                    <span className="font-mono text-xs text-white font-bold truncate inline-block max-w-[170px] align-bottom">
                      {res.name.split('.').pop()}
                    </span>
                  </div>
                  <span className="pixel-tag-cyan text-[10px] whitespace-nowrap font-mono">
                    {Math.round(res.similarity * 100)}%
                  </span>
                </div>

                <div className="text-[10px] text-neutral-500 font-mono truncate mb-2" title={res.file}>
                  {res.file}
                </div>

                <div className="text-[11px] text-neutral-300 bg-black p-2 border border-neutral-800 line-clamp-3 font-mono opacity-80 group-hover:opacity-100 mb-2">
                  {res.source_reference}
                </div>

                <div className="flex justify-end pt-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/repositories/${repoId}/investigation?entity_id=${encodeURIComponent(res.entity)}`)
                    }}
                    className="pixel-btn text-[10px] px-2 py-0.5 hover:border-cyan-400 hover:text-cyan-400 flex items-center gap-1"
                  >
                    <ExternalLink className="w-3 h-3" />
                    <span>[ INVESTIGATE ]</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
