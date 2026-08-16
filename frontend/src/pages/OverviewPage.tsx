import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { useState, useEffect } from 'react'

export default function OverviewPage() {
  const { repoId } = useParams<{ repoId: string }>()
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)

  const { data: repo } = useQuery({
    queryKey: ['repository', repoId],
    queryFn: () => api.getRepositories().then(repos => repos.find((r: any) => r.id === repoId)),
    enabled: !!repoId
  })

  const { data: jobStatus } = useQuery({
    queryKey: ['jobStatus', currentJobId],
    queryFn: () => api.getJobStatus(currentJobId!),
    enabled: !!currentJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'failed') return false;
      return 1000;
    }
  })

  const analyzeMutation = useMutation({
    mutationFn: () => api.analyzeRepository(repoId!),
    onSuccess: (data) => {
      setCurrentJobId(data.id)
    }
  })

  if (!repo) return <div className="p-8">Loading...</div>

  return (
    <div className="container mx-auto p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <Link to="/repositories" className="text-muted-foreground hover:text-foreground mb-2 inline-block">&larr; Back to Repositories</Link>
          <h1 className="text-3xl font-bold">{repo.name}</h1>
          <p className="text-muted-foreground">{repo.source_url}</p>
        </div>
        <button 
          onClick={() => analyzeMutation.mutate()}
          disabled={analyzeMutation.isPending || (jobStatus && jobStatus.status === 'running')}
          className="bg-primary text-primary-foreground px-6 py-2 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          {jobStatus?.status === 'running' ? 'Analyzing...' : 'Trigger Analysis'}
        </button>
      </div>

      {jobStatus && (
        <div className="bg-card border rounded-lg p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">Analysis Status</h2>
          <div className="flex items-center gap-4 mb-2">
            <span className="font-medium capitalize">{jobStatus.status}</span>
            <span className="text-muted-foreground text-sm">{jobStatus.current_stage || 'Initializing'}</span>
          </div>
          <div className="w-full bg-muted rounded-full h-2.5">
            <div 
              className="bg-primary h-2.5 rounded-full transition-all duration-500" 
              style={{ width: `${Math.max(0, jobStatus.progress)}%` }}
            ></div>
          </div>
          {jobStatus.error_message && (
            <p className="text-destructive mt-4 text-sm">{jobStatus.error_message}</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-8">
        <div className="bg-card border rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Repository Details</h2>
          <dl className="space-y-4">
            <div>
              <dt className="text-sm font-medium text-muted-foreground">ID</dt>
              <dd className="mt-1">{repo.id}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Source Type</dt>
              <dd className="mt-1 capitalize">{repo.source_type}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">Last Analyzed</dt>
              <dd className="mt-1">{repo.last_analyzed_at ? new Date(repo.last_analyzed_at).toLocaleString() : 'Never'}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  )
}
