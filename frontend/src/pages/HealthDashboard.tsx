import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

interface HealthData {
  repository_id: string;
  snapshot_id: string;
  commit_sha: string;
  health: {
    total_modules: number;
    total_classes: number;
    total_functions: number;
    average_complexity: number;
    maximum_complexity: number;
    circular_dependencies: number;
    high_complexity_functions: number;
    high_coupling_modules: number;
  };
}

export const HealthDashboard: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  const { data, isLoading, error } = useQuery<HealthData>({
    queryKey: ['health', id],
    queryFn: async () => {
      const response = await apiClient.get(`/api/v1/metrics/${id}/health`);
      return response.data;
    },
  });

  if (isLoading) return <div className="p-8 text-white">Loading health data...</div>;
  if (error || !data) return <div className="p-8 text-red-400">Failed to load health metrics or snapshot not found.</div>;

  const { health } = data;

  return (
    <div className="p-8 max-w-7xl mx-auto text-gray-100">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Codebase Health</h1>
          <p className="text-gray-400 text-sm">Commit: {data.commit_sha || 'N/A'}</p>
        </div>
        <Link 
          to={`/repositories/${id}`}
          className="bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded transition"
        >
          Back to Overview
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard title="Total Files" value={health.total_modules} />
        <MetricCard title="Total Classes" value={health.total_classes} />
        <MetricCard title="Total Functions" value={health.total_functions} />
        <MetricCard 
          title="Circular Dependencies" 
          value={health.circular_dependencies} 
          alert={health.circular_dependencies > 0} 
        />
      </div>

      <h2 className="text-xl font-semibold mb-4 text-white">Complexity & Risk</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard title="Average Complexity" value={health.average_complexity} />
        <MetricCard 
          title="Maximum Complexity" 
          value={health.maximum_complexity} 
          alert={health.maximum_complexity > 15}
        />
        <MetricCard 
          title="High Complexity Funcs" 
          value={health.high_complexity_functions} 
          alert={health.high_complexity_functions > 0}
        />
        <MetricCard 
          title="High Coupling Modules" 
          value={health.high_coupling_modules} 
          alert={health.high_coupling_modules > 0}
        />
      </div>
      
      <div className="mt-12 bg-gray-900 p-6 rounded-lg border border-gray-800">
        <h3 className="text-lg font-medium text-white mb-2">Entity Metrics Explorer</h3>
        <p className="text-gray-400 text-sm mb-4">
          Detailed entity-level metrics are computed dynamically for classes and functions in the knowledge graph. 
          Use the Architecture view to select specific entities.
        </p>
      </div>
    </div>
  );
};

const MetricCard: React.FC<{ title: string; value: string | number; alert?: boolean }> = ({ title, value, alert }) => (
  <div className={`p-6 rounded-lg border ${alert ? 'bg-red-900/20 border-red-800/50' : 'bg-gray-800/50 border-gray-700/50'}`}>
    <h3 className="text-gray-400 text-sm font-medium mb-2">{title}</h3>
    <div className={`text-3xl font-bold ${alert ? 'text-red-400' : 'text-white'}`}>
      {value}
    </div>
  </div>
);
