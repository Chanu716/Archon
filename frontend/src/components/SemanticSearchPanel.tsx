import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

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
    return colors[type] || 'text-gray-400'
  }

  return (
    <div className="w-96 bg-gray-900 border-r border-gray-700 flex flex-col h-full overflow-hidden absolute left-0 z-20 shadow-2xl">
      <div className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-900">
        <h2 className="text-white font-bold text-sm">Semantic Code Search</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-white flex-shrink-0 text-lg leading-none">✕</button>
      </div>

      <div className="p-4 border-b border-gray-800 bg-gray-900">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="e.g. Where is authentication handled?"
            className="flex-1 bg-gray-950 border border-gray-700 text-gray-200 text-sm rounded px-3 py-2 focus:outline-none focus:border-blue-500 placeholder-gray-600"
          />
          <button 
            type="submit" 
            disabled={!query.trim() || isLoading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white px-3 rounded text-sm font-medium transition-colors flex items-center justify-center"
          >
            {isLoading ? '...' : '🔍'}
          </button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto bg-gray-950">
        {!searchTerm && !isLoading && (
          <div className="p-8 text-center text-gray-500 text-sm">
            <p>Enter a natural language query to find relevant code.</p>
            <p className="mt-4 text-xs text-gray-600 italic">"How are payments processed?"</p>
          </div>
        )}
        
        {isLoading && (
          <div className="p-8 text-center text-blue-400 text-sm animate-pulse">
            Embedding query and searching vectors...
          </div>
        )}

        {error && (
          <div className="p-4 text-red-400 text-sm bg-red-900/20 border-b border-red-900/50">
            Search failed. Check if OpenAI API key is configured and pgvector is enabled.
          </div>
        )}

        {results?.length === 0 && (
          <div className="p-8 text-center text-gray-500 text-sm">
            No semantic matches found above the threshold.
          </div>
        )}

        {results && results.length > 0 && (
          <div className="divide-y divide-gray-800">
            {results.map((res: SearchResult, idx: number) => (
              <div 
                key={`${res.entity}-${idx}`} 
                className="p-4 hover:bg-gray-900 cursor-pointer transition-colors group"
                onClick={() => onSelectResult(res.entity, res.name)}
              >
                <div className="flex justify-between items-start mb-1">
                  <div className="overflow-hidden pr-2">
                    <span className={`text-xs font-semibold uppercase tracking-wide mr-2 ${getTypeColor(res.entity_type)}`}>
                      {res.entity_type}
                    </span>
                    <span className="font-mono text-sm text-gray-200 truncate inline-block max-w-[200px] align-bottom">
                      {res.name.split('.').pop()}
                    </span>
                  </div>
                  <span className="text-xs font-mono text-green-400 bg-green-900/30 px-1.5 py-0.5 rounded border border-green-800/50 whitespace-nowrap">
                    {(res.similarity * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="text-xs text-gray-500 font-mono truncate mb-2" title={res.file}>
                  {res.file}
                </div>
                
                {/* Source Preview */}
                <div className="text-xs text-gray-400 bg-gray-950 p-2 rounded border border-gray-800 line-clamp-3 font-mono opacity-80 group-hover:opacity-100 transition-opacity mb-2">
                  {res.source_reference}
                </div>
                
                <div className="flex justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/repositories/${repoId}/investigation?entity_id=${encodeURIComponent(res.entity)}`)
                    }}
                    className="text-[10px] bg-indigo-600 hover:bg-indigo-700 text-white px-2 py-1 rounded"
                  >
                    Open Investigation
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
