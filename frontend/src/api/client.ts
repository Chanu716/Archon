import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

export const api = {
  getRepositories: async () => {
    const res = await apiClient.get('/repositories')
    return res.data
  },
  createRepository: async (sourceUrl: string) => {
    const res = await apiClient.post('/repositories', { source_url: sourceUrl })
    return res.data
  },
  analyzeRepository: async (repoId: string) => {
    const res = await apiClient.post(`/repositories/${repoId}/analyze`, {})
    return res.data
  },
  getJobStatus: async (jobId: string) => {
    const res = await apiClient.get(`/analysis-jobs/${jobId}`)
    return res.data
  },
  getGraphOverview: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/overview`)
    return res.data
  },
  getEvolutionTimeline: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/evolution/timeline`)
    return res.data
  },
  compareSnapshots: async (repoId: string, previousSnapshotId: string, currentSnapshotId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/evolution/compare`, {
      params: { previous_snapshot_id: previousSnapshotId, current_snapshot_id: currentSnapshotId },
    })
    return res.data
  },
  searchGraphNodes: async (repoId: string, q: string, limit = 20) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/search`, { params: { q, limit } })
    return res.data
  },
  expandNode: async (repoId: string, nodeId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/nodes/${nodeId}/expand`)
    return res.data
  },
  getNodeDetails: async (repoId: string, nodeId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/nodes/${nodeId}`)
    return res.data
  },
  getEntityMetrics: async (repoId: string, entityType: string, entityName: string) => {
    const res = await apiClient.get(`/metrics/${repoId}/metrics/${entityType}/${entityName}`)
    return res.data
  },
  getRepositoryHealth: async (repoId: string) => {
    const res = await apiClient.get(`/metrics/${repoId}/health`)
    return res.data
  },
  getImpact: async (
    repoId: string,
    entityId: string,
    direction: 'upstream' | 'downstream' | 'both' = 'both',
    depth = 5,
    limit = 100
  ) => {
    const res = await apiClient.get(`/repositories/${repoId}/impact/${encodeURIComponent(entityId)}`, {
      params: { direction, depth, limit },
    })
    return res.data
  },
  getGitOverview: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/overview`)
    return res.data
  },
  getGitCommits: async (repoId: string, limit = 50) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/commits`, { params: { limit } })
    return res.data
  },
  getGitFiles: async (repoId: string, sortBy: 'churn' | 'recent' = 'churn', limit = 50) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/files`, { params: { sort_by: sortBy, limit } })
    return res.data
  },
  getGitContributors: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/contributors`)
    return res.data
  },
  getGitHotspots: async (repoId: string, limit = 20) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/hotspots`, { params: { limit } })
    return res.data
  },
  searchSemantic: async (repoId: string, query: string, limit = 10) => {
    const res = await apiClient.get(`/repositories/${repoId}/search/semantic`, {
      params: { q: query, limit }
    })
    return res.data
  },
}

export default apiClient
