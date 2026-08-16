import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '@/api/client'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts'
import AnalystPanel from '@/components/AnalystPanel'

export default function EvolutionDashboard() {
  const { repoId } = useParams<{ repoId: string }>()
  const [timeline, setTimeline] = useState<any[]>([])
  const [compareData, setCompareData] = useState<any>(null)
  const [prevSnap, setPrevSnap] = useState<string>('')
  const [currSnap, setCurrSnap] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [analystOpen, setAnalystOpen] = useState(false)

  useEffect(() => {
    if (repoId) {
      api.getEvolutionTimeline(repoId).then((data) => {
        setTimeline(data)
        if (data.length >= 2) {
          setPrevSnap(data[data.length - 2].snapshot_id)
          setCurrSnap(data[data.length - 1].snapshot_id)
        }
      })
    }
  }, [repoId])

  useEffect(() => {
    if (repoId && prevSnap && currSnap) {
      setLoading(true)
      api.compareSnapshots(repoId, prevSnap, currSnap)
        .then(setCompareData)
        .catch(console.error)
        .finally(() => setLoading(false))
    }
  }, [repoId, prevSnap, currSnap])

  const chartData = timeline.map((t, idx) => ({
    name: `S${idx + 1}`,
    date: new Date(t.analyzed_at).toLocaleDateString(),
    complexity: t.average_complexity,
    coupling: t.average_coupling,
    risk: t.repository_risk
  }))

  return (
    <div className="p-6 text-gray-200">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Architecture Evolution</h1>
        <button
          onClick={() => setAnalystOpen(!analystOpen)}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors border ${
            analystOpen 
              ? 'bg-purple-900/40 text-purple-400 border-purple-700/50' 
              : 'bg-purple-900/20 text-purple-300 border-purple-800/50 hover:bg-purple-800/40 hover:text-white'
          }`}
        >
          ⚡ AI Analyst
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-gray-800 rounded p-4 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4 text-gray-300">Complexity & Coupling Trend</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" />
                <Tooltip contentStyle={{ backgroundColor: '#1F2937', borderColor: '#374151' }} />
                <Legend />
                <Line type="monotone" dataKey="complexity" stroke="#8B5CF6" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="coupling" stroke="#10B981" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-gray-800 rounded p-4 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4 text-gray-300">Risk Evolution</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" />
                <Tooltip contentStyle={{ backgroundColor: '#1F2937', borderColor: '#374151' }} />
                <Legend />
                <Line type="monotone" dataKey="risk" stroke="#EF4444" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {timeline.length > 1 && (
        <div className="mb-6 flex space-x-4 items-center bg-gray-800 p-4 rounded border border-gray-700">
          <span className="text-gray-400">Compare:</span>
          <select 
            value={prevSnap} 
            onChange={(e) => setPrevSnap(e.target.value)}
            className="bg-gray-900 border border-gray-700 text-white rounded p-2"
          >
            {timeline.map((t, idx) => (
              <option key={t.snapshot_id} value={t.snapshot_id}>S{idx + 1} - {new Date(t.analyzed_at).toLocaleString()}</option>
            ))}
          </select>
          <span className="text-gray-400">→</span>
          <select 
            value={currSnap} 
            onChange={(e) => setCurrSnap(e.target.value)}
            className="bg-gray-900 border border-gray-700 text-white rounded p-2"
          >
            {timeline.map((t, idx) => (
              <option key={t.snapshot_id} value={t.snapshot_id}>S{idx + 1} - {new Date(t.analyzed_at).toLocaleString()}</option>
            ))}
          </select>
        </div>
      )}

      {loading && <div className="text-gray-400">Comparing snapshots...</div>}

      {compareData && !loading && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="col-span-2">
            <h2 className="text-xl font-bold mb-4">Structural Changes</h2>
            
            <div className="bg-gray-800 rounded border border-gray-700 overflow-hidden mb-6">
              <div className="px-4 py-3 bg-gray-900 border-b border-gray-700 font-medium">Entities Lifecycle</div>
              <ul className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
                {compareData.entities.filter((e: any) => e.state !== 'UNCHANGED').map((e: any, idx: number) => (
                  <li key={idx} className="p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <span className="text-xs text-gray-500 uppercase">{e.entity_type}</span>
                        <div className="font-mono text-sm text-blue-400 mt-1">{e.qualified_name}</div>
                      </div>
                      <span className={`px-2 py-1 text-xs rounded font-bold ${
                        e.state === 'ADDED' ? 'bg-green-900/50 text-green-400' :
                        e.state === 'REMOVED' ? 'bg-red-900/50 text-red-400' :
                        'bg-yellow-900/50 text-yellow-400'
                      }`}>
                        {e.state}
                      </span>
                    </div>
                  </li>
                ))}
                {compareData.entities.filter((e: any) => e.state !== 'UNCHANGED').length === 0 && (
                  <li className="p-4 text-gray-500 italic">No structural entity changes</li>
                )}
              </ul>
            </div>

            <div className="bg-gray-800 rounded border border-gray-700 overflow-hidden">
              <div className="px-4 py-3 bg-gray-900 border-b border-gray-700 font-medium">Dependency Changes</div>
              <ul className="divide-y divide-gray-700 max-h-96 overflow-y-auto">
                {compareData.relationships.map((r: any, idx: number) => (
                  <li key={idx} className="p-4">
                    <div className="flex justify-between">
                      <div className="text-sm font-mono text-gray-300">
                        {r.source_qname} <span className="text-gray-500 mx-2">{r.relationship_type}</span> {r.target_qname}
                      </div>
                      <span className={`px-2 py-1 text-xs rounded font-bold ${
                        r.state === 'ADDED' ? 'bg-green-900/50 text-green-400' :
                        r.state === 'REMOVED' ? 'bg-red-900/50 text-red-400' :
                        'bg-yellow-900/50 text-yellow-400'
                      }`}>
                        {r.state}
                      </span>
                    </div>
                  </li>
                ))}
                {compareData.relationships.length === 0 && (
                  <li className="p-4 text-gray-500 italic">No dependency changes</li>
                )}
              </ul>
            </div>
          </div>

          <div>
            <h2 className="text-xl font-bold mb-4 text-red-400">Architecture Drift</h2>
            {compareData.drift_findings.length > 0 ? (
              <div className="space-y-4">
                {compareData.drift_findings.map((drift: any, idx: number) => (
                  <div key={idx} className="bg-red-900/10 border border-red-900 rounded p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-bold text-red-400 uppercase text-xs">{drift.severity} DRIFT</span>
                      <span className="text-xs text-gray-400">{drift.entity_type}</span>
                    </div>
                    <div className="font-mono text-sm text-gray-200 mb-3 break-all">{drift.entity_name}</div>
                    <p className="text-sm text-red-300/80">{drift.reason}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-gray-800 rounded p-6 text-center border border-gray-700">
                <span className="text-green-400 block mb-2 text-2xl">✓</span>
                <span className="text-gray-400">No architectural drift detected between these snapshots.</span>
              </div>
            )}
          </div>
        </div>
      )}

      {analystOpen && repoId && (
        <AnalystPanel
          repoId={repoId}
          snapshotId={currSnap}
          onClose={() => setAnalystOpen(false)}
        />
      )}
    </div>
  )
}
