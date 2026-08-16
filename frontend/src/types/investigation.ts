export interface InvestigationContext {
  repository_id: string;
  snapshot_id: string;
  entity_id: string;
  entity_name: string;
  qualified_name?: string;
  entity_type: string;
  file_path?: string;
}

export interface EntityOverview {
  complexity?: number;
  coupling?: number;
  risk?: number;
  churn?: number;
  callers?: number;
  callees?: number;
}

export interface CodeContext {
  source_code: string;
  truncated: boolean;
}

export interface GraphContext {
  nodes: any[];
  edges: any[];
}

export interface HealthContext {
  metrics: Record<string, number>;
  sources: Record<string, string>;
}

export interface GitContext {
  commit_count: number;
  churn: number;
  first_changed_at?: string;
  last_changed_at?: string;
  recent_commits: any[];
}

export interface ImpactContext {
  direct_callers: number;
  indirect_callers: number;
  direct_callees: number;
  indirect_callees: number;
  affected_entities: number;
  graph: {
    nodes: any[];
    edges: any[];
  };
}

export interface EvolutionContext {
  lifecycle?: any;
  relationship_changes: any[];
  drift_findings: any[];
}

export interface SemanticContext {
  related_entities: any[];
}

export interface InvestigationBaseResponse {
  context: InvestigationContext;
  overview: EntityOverview;
  code?: CodeContext;
  graph?: GraphContext;
  health?: HealthContext;
}
