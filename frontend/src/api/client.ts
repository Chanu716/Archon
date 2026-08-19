import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

function toArray<T = any>(data: any): T[] {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.data)) return data.data
  return []
}

function toGraphData(data: any): { nodes: any[]; edges: any[] } {
  const d = data?.data || data
  return {
    nodes: Array.isArray(d?.nodes) ? d.nodes : [],
    edges: Array.isArray(d?.edges) ? d.edges : [],
  }
}

export const api = {
  getRepositories: async () => {
    const res = await apiClient.get('/repositories')
    return toArray(res.data)
  },
  createRepository: async (sourceUrl: string) => {
    const res = await apiClient.post('/repositories', { source_url: sourceUrl })
    return res.data?.data || res.data
  },
  analyzeRepository: async (repoId: string) => {
    const res = await apiClient.post(`/repositories/${repoId}/analyze`, {})
    return res.data?.data || res.data
  },
  getJobStatus: async (jobId: string) => {
    const res = await apiClient.get(`/analysis-jobs/${jobId}`)
    return res.data?.data || res.data
  },
  getGraphOverview: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/overview`)
    return toGraphData(res.data)
  },
  getEvolutionTimeline: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/evolution/timeline`)
    return toArray(res.data)
  },
  compareSnapshots: async (repoId: string, previousSnapshotId: string, currentSnapshotId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/evolution/compare`, {
      params: { previous_snapshot_id: previousSnapshotId, current_snapshot_id: currentSnapshotId },
    })
    const d = res.data?.data || res.data
    return {
      entities: toArray(d?.entities),
      relationships: toArray(d?.relationships),
      drift_findings: toArray(d?.drift_findings),
    }
  },
  searchGraphNodes: async (repoId: string, q: string, limit = 20) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/search`, { params: { q, limit } })
    return toArray(res.data)
  },
  expandNode: async (repoId: string, nodeId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/nodes/${nodeId}/expand`)
    return toGraphData(res.data)
  },
  getNodeDetails: async (repoId: string, nodeId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/graph/nodes/${nodeId}`)
    return res.data
  },
  getEntityMetrics: async (repoId: string, entityType: string, entityName: string) => {
    const res = await apiClient.get(`/metrics/${repoId}/metrics/${entityType}/${entityName}`)
    return res.data?.data || res.data
  },
  getRepositoryHealth: async (repoId: string) => {
    const res = await apiClient.get(`/metrics/${repoId}/health`)
    return res.data?.data || res.data
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
    const d = res.data?.data || res.data
    if (!d) return null
    return {
      ...d,
      direct_callers: toArray(d.direct_callers),
      indirect_callers: toArray(d.indirect_callers),
      direct_callees: toArray(d.direct_callees),
      indirect_callees: toArray(d.indirect_callees),
      affected_files: toArray(d.affected_files),
      affected_modules: toArray(d.affected_modules),
      affected_classes: toArray(d.affected_classes),
      unresolved_references: toArray(d.unresolved_references),
      summary: d.summary || {
        direct_callers: 0,
        indirect_callers: 0,
        direct_callees: 0,
        indirect_callees: 0,
        affected_files: 0,
        affected_modules: 0,
        affected_classes: 0,
        unresolved_references: 0,
      },
      traversal: d.traversal || {
        max_depth: depth,
        max_nodes: limit,
        actual_depth_reached: 0,
        nodes_visited: 0,
        truncated: false,
      },
    }
  },
  getGitOverview: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/overview`)
    return res.data?.data || res.data
  },
  getGitCommits: async (repoId: string, limit = 50) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/commits`, { params: { limit } })
    return toArray(res.data)
  },
  getGitFiles: async (repoId: string, sortBy: 'churn' | 'recent' = 'churn', limit = 50) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/files`, { params: { sort_by: sortBy, limit } })
    return toArray(res.data)
  },
  getGitContributors: async (repoId: string) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/contributors`)
    return toArray(res.data)
  },
  getGitHotspots: async (repoId: string, limit = 20) => {
    const res = await apiClient.get(`/repositories/${repoId}/git/hotspots`, { params: { limit } })
    return toArray(res.data)
  },
  searchSemantic: async (repoId: string, query: string, limit = 10) => {
    const res = await apiClient.get(`/repositories/${repoId}/search/semantic`, {
      params: { q: query, limit }
    })
    return toArray(res.data)
  },
}

export default apiClient
