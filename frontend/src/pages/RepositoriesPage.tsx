import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { Repository } from '@/types'

export default function RepositoriesPage() {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')

  const { data: repos, isLoading } = useQuery<Repository[]>({
    queryKey: ['repositories'],
    queryFn: api.getRepositories
  })

  const createMutation = useMutation<unknown, Error, string>({
    mutationFn: (sourceUrl: string) => api.createRepository(sourceUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      setUrl('')
    }
  })

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (url) {
      createMutation.mutate(url)
    }
  }

  return (
    <div className="container mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8">Archon Repositories</h1>
      
      <div className="bg-card border rounded-lg p-6 mb-8">
        <h2 className="text-xl font-semibold mb-4">Add Repository</h2>
        <form onSubmit={handleAdd} className="flex gap-4">
          <input 
            type="url" 
            placeholder="https://github.com/user/repo"
            className="flex-1 px-4 py-2 border rounded-md"
            value={url}
            onChange={e => setUrl(e.target.value)}
            disabled={createMutation.isPending}
            required
          />
          <button 
            type="submit" 
            className="bg-primary text-primary-foreground px-6 py-2 rounded-md hover:opacity-90"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? 'Adding...' : 'Add Repository'}
          </button>
        </form>
      </div>

      <div className="grid gap-4">
        {isLoading ? (
          <div>Loading repositories...</div>
        ) : repos?.length === 0 ? (
          <div className="text-muted-foreground">No repositories added yet.</div>
        ) : (
          repos?.map(repo => (
            <div key={repo.id} className="bg-card border rounded-lg p-6 flex justify-between items-center hover:border-primary/50 transition-colors">
              <div>
                <h3 className="text-xl font-semibold">{repo.name}</h3>
                <p className="text-muted-foreground text-sm">{repo.source_url}</p>
              </div>
              <div className="flex gap-4">
                <Link 
                  to={`/repositories/${repo.id}/overview`}
                  className="px-4 py-2 border rounded-md hover:bg-muted"
                >
                  Overview
                </Link>
                {(repo.has_snapshot || repo.last_analyzed_at) ? (
                  <Link 
                    to={`/repositories/${repo.id}/architecture`}
                    className="px-4 py-2 border border-primary text-primary hover:bg-primary hover:text-primary-foreground rounded-md"
                  >
                    Architecture Graph
                  </Link>
                ) : (
                  <span
                    className="px-4 py-2 border border-gray-300 text-gray-400 rounded-md cursor-not-allowed opacity-50"
                    title="Run analysis first to view architecture graph"
                  >
                    Architecture Graph
                  </span>
                )}
                {(repo.has_snapshot || repo.last_analyzed_at) && (
                  <Link 
                    to={`/repositories/${repo.id}/evolution`}
                    className="px-4 py-2 border border-purple-500 text-purple-400 hover:bg-purple-900/50 hover:text-purple-300 rounded-md"
                  >
                    Evolution
                  </Link>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
