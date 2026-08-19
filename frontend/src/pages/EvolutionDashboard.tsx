import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '@/api/client'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import AnalystPanel from '@/components/AnalystPanel'
import { Zap, TrendingUp, GitCompare, AlertTriangle, CheckCircle2 } from 'lucide-react'

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
    risk: t.repository_risk,
  }))

  return (
    <div className="min-h-screen bg-black text-white p-6 md:p-10 font-mono crt-grid">
      {/* Top Header */}
      <div className="max-w-6xl mx-auto mb-8 border-b-2 border-white pb-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <Link
            to={`/repositories/${repoId}/overview`}
            className="text-xs text-neutral-400 hover:text-cyan-400 transition-colors inline-flex items-center gap-1 mb-2"
          >
            ← [ BACK_TO_OVERVIEW ]
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="font-pixel text-xl text-white tracking-wide">
              ARCHITECTURE_EVOLUTION_TIMELINE
            </h1>
            <span className="pixel-tag-cyan text-[10px]">SNAPSHOTS: {timeline.length}</span>
          </div>
        </div>

        <button
          onClick={() => setAnalystOpen(!analystOpen)}
          className={`pixel-btn text-xs ${analystOpen ? 'pixel-btn-cyan' : ''}`}
        >
          <Zap className="w-3.5 h-3.5 mr-1 inline text-cyan-400" />
          [ AI_ANALYST ]
        </button>
      </div>

      <div className="max-w-6xl mx-auto space-y-6">
        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="pixel-box p-5">
            <div className="font-pixel text-xs text-cyan-400 mb-4 uppercase">
              [ COMPLEXITY_&_COUPLING_TREND ]
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#262626" />
                  <XAxis dataKey="name" stroke="#737373" tick={{ fill: '#a3a3a3', fontSize: 11, fontFamily: 'monospace' }} />
                  <YAxis stroke="#737373" tick={{ fill: '#a3a3a3', fontSize: 11, fontFamily: 'monospace' }} />
                  <Tooltip contentStyle={{ backgroundColor: '#000000', borderColor: '#ffffff', fontFamily: 'monospace', fontSize: '11px' }} />
                  <Legend />
                  <Line type="monotone" dataKey="complexity" stroke="#00f3ff" strokeWidth={2} dot={{ r: 4, fill: '#00f3ff' }} />
                  <Line type="monotone" dataKey="coupling" stroke="#10b981" strokeWidth={2} dot={{ r: 4, fill: '#10b981' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="pixel-box p-5">
            <div className="font-pixel text-xs text-amber-400 mb-4 uppercase">
              [ REPOSITORY_RISK_EVOLUTION ]
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="2 2" stroke="#262626" />
                  <XAxis dataKey="name" stroke="#737373" tick={{ fill: '#a3a3a3', fontSize: 11, fontFamily: 'monospace' }} />
                  <YAxis stroke="#737373" tick={{ fill: '#a3a3a3', fontSize: 11, fontFamily: 'monospace' }} />
                  <Tooltip contentStyle={{ backgroundColor: '#000000', borderColor: '#ffffff', fontFamily: 'monospace', fontSize: '11px' }} />
                  <Legend />
                  <Line type="monotone" dataKey="risk" stroke="#ef4444" strokeWidth={2} dot={{ r: 4, fill: '#ef4444' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Compare Bar */}
        {timeline.length > 1 && (
          <div className="pixel-box p-4 flex flex-wrap items-center gap-3">
            <span className="font-pixel text-xs text-neutral-400">[ COMPARE_SNAPSHOTS ]:</span>
            <select
              value={prevSnap}
              onChange={(e) => setPrevSnap(e.target.value)}
              className="pixel-input text-xs px-3 py-1.5 focus:outline-none"
            >
              {timeline.map((t, idx) => (
                <option key={t.snapshot_id} value={t.snapshot_id} className="bg-black">
                  S{idx + 1} - {new Date(t.analyzed_at).toLocaleDateString()}
                </option>
              ))}
            </select>
            <span className="text-cyan-400 font-pixel">→</span>
            <select
              value={currSnap}
              onChange={(e) => setCurrSnap(e.target.value)}
              className="pixel-input text-xs px-3 py-1.5 focus:outline-none"
            >
              {timeline.map((t, idx) => (
                <option key={t.snapshot_id} value={t.snapshot_id} className="bg-black">
                  S{idx + 1} - {new Date(t.analyzed_at).toLocaleDateString()}
                </option>
              ))}
            </select>
          </div>
        )}

        {loading && (
          <div className="pixel-box p-8 text-center text-cyan-400 font-pixel text-xs animate-pulse">
            [ COMPARING_AST_SNAPSHOT_TREES… ]
          </div>
        )}

        {compareData && !loading && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="col-span-2 space-y-6">
              {/* Entity lifecycle */}
              <div className="pixel-box overflow-hidden">
                <div className="px-4 py-3 border-b border-neutral-800 font-pixel text-xs text-white">
                  [ ENTITY_LIFECYCLE_CHANGES ]
                </div>
                <ul className="divide-y divide-neutral-900 max-h-96 overflow-y-auto">
                  {compareData.entities.filter((e: any) => e.state !== 'UNCHANGED').map((e: any, idx: number) => (
                    <li key={idx} className="p-3 hover:bg-neutral-950 flex justify-between items-center text-xs">
                      <div>
                        <span className="font-pixel text-[9px] text-neutral-500 uppercase mr-2">[{e.entity_type}]</span>
                        <span className="font-mono text-cyan-400 font-bold">{e.qualified_name}</span>
                      </div>
                      <span className={`px-1.5 py-0.5 text-[10px] font-pixel border ${
                        e.state === 'ADDED' ? 'border-green-500 text-green-400 bg-green-950/40' :
                        e.state === 'REMOVED' ? 'border-red-500 text-red-400 bg-red-950/40' :
                        'border-amber-500 text-amber-400 bg-amber-950/40'
                      }`}>
                        {e.state}
                      </span>
                    </li>
                  ))}
                  {compareData.entities.filter((e: any) => e.state !== 'UNCHANGED').length === 0 && (
                    <li className="p-4 text-neutral-500 text-xs italic">No structural entity changes detected.</li>
                  )}
                </ul>
              </div>

              {/* Dependency changes */}
              <div className="pixel-box overflow-hidden">
                <div className="px-4 py-3 border-b border-neutral-800 font-pixel text-xs text-white">
                  [ DEPENDENCY_GRAPH_CHANGES ]
                </div>
                <ul className="divide-y divide-neutral-900 max-h-96 overflow-y-auto">
                  {compareData.relationships.map((r: any, idx: number) => (
                    <li key={idx} className="p-3 hover:bg-neutral-950 flex justify-between items-center text-xs">
                      <div className="font-mono text-neutral-300">
                        {r.source_qname} <span className="text-cyan-400 mx-1.5">[{r.relationship_type}]</span> {r.target_qname}
                      </div>
                      <span className={`px-1.5 py-0.5 text-[10px] font-pixel border ${
                        r.state === 'ADDED' ? 'border-green-500 text-green-400 bg-green-950/40' :
                        r.state === 'REMOVED' ? 'border-red-500 text-red-400 bg-red-950/40' :
                        'border-amber-500 text-amber-400 bg-amber-950/40'
                      }`}>
                        {r.state}
                      </span>
                    </li>
                  ))}
                  {compareData.relationships.length === 0 && (
                    <li className="p-4 text-neutral-500 text-xs italic">No dependency edge delta found.</li>
                  )}
                </ul>
              </div>
            </div>

            {/* Drift findings */}
            <div>
              <div className="pixel-box p-5">
                <div className="font-pixel text-xs text-red-400 mb-4 uppercase">
                  [ ARCHITECTURE_DRIFT ]
                </div>
                {compareData.drift_findings.length > 0 ? (
                  <div className="space-y-3">
                    {compareData.drift_findings.map((drift: any, idx: number) => (
                      <div key={idx} className="border border-red-500 bg-red-950/20 p-3 text-xs">
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-pixel text-[9px] text-red-400 uppercase">{drift.severity} DRIFT</span>
                          <span className="text-neutral-500 text-[10px]">{drift.entity_type}</span>
                        </div>
                        <div className="font-mono text-xs text-white mb-2 break-all">{drift.entity_name}</div>
                        <p className="text-red-300 text-[11px] leading-relaxed">{drift.reason}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center p-6 space-y-2">
                    <CheckCircle2 className="w-8 h-8 text-green-400 mx-auto" />
                    <span className="text-xs text-neutral-400 block font-mono">
                      No architectural drift detected between these snapshots.
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

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
