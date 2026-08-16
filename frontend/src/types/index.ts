export interface Repository {
  id: string;
  name: string;
  source_type: string;
  source_url: string;
  created_at: string;
  last_analyzed_at?: string;
  detected_languages?: string[];
  has_snapshot?: boolean;
}

export interface AnalysisJob {
  id: string;
  repository_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  current_stage?: string;
  progress: number;
  error_message?: string;
}

export interface GraphNode {
  id: string;
  labels: string[];
  properties: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  type: string;
  source: string;
  target: string;
  properties: Record<string, any>;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface AnalysisSnapshot {
  id: string;
  repository_id: string;
  commit_sha?: string;
  is_latest: boolean;
  created_at: string;
}
