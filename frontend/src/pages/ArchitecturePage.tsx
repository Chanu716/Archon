import { useState, useRef, useCallback, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import CytoscapeComponent from 'react-cytoscapejs'
import cytoscape from 'cytoscape'
import { api } from '@/api/client'
import EntityDetailsPanel from '@/components/EntityDetailsPanel'
import ImpactPanel from '@/components/ImpactPanel'
import SemanticSearchPanel from '@/components/SemanticSearchPanel'
import AnalystPanel from '@/components/AnalystPanel'

// ── Visual configuration ──────────────────────────────────────────────────────

const NODE_TYPE_STYLES: Record<string, { color: string; shape: cytoscape.Css.NodeShape }> = {
  Repository: { color: '#f59e0b', shape: 'star' },
  Directory:  { color: '#fb923c', shape: 'round-rectangle' },
  File:       { color: '#818cf8', shape: 'hexagon' },
  Module:     { color: '#3b82f6', shape: 'round-rectangle' },
  Class:      { color: '#10b981', shape: 'ellipse' },
  Function:   { color: '#ec4899', shape: 'round-diamond' },
  Method:     { color: '#a78bfa', shape: 'diamond' },
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const STYLESHEET: any[] = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'text-valign': 'bottom',
      'text-halign': 'center',
      'text-margin-y': 4,
      'color': '#e2e8f0',
      'font-size': '9px',
      'font-family': 'Inter, sans-serif',
      'background-color': '#374151',
      'border-width': 2,
      'border-color': '#4b5563',
      'width': 36,
      'height': 36,
      'text-max-width': '80px',
      'text-wrap': 'ellipsis',
    },
  },
  ...Object.entries(NODE_TYPE_STYLES).map(([type, style]) => ({
    selector: `node[type = "${type}"]`,
    style: {
      'background-color': style.color,
      'shape': style.shape,
      'border-color': style.color,
    } as cytoscape.Css.Node,
  })),
  { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#ffffff', 'border-style': 'solid' } },
  { selector: 'node.highlighted', style: { 'border-width': 4, 'border-color': '#fbbf24' } },
  // Impact visual classes
  { selector: 'node.impact-target',   style: { 'border-width': 5, 'border-color': '#f97316', 'border-style': 'solid' } },
  { selector: 'node.impact-direct',   style: { 'border-width': 3, 'border-color': '#f97316', 'border-style': 'solid', 'opacity': 1 } },
  { selector: 'node.impact-indirect', style: { 'border-width': 2, 'border-color': '#fdba74', 'border-style': 'dashed', 'opacity': 0.75 } },
  { selector: 'node.impact-unresolved', style: { 'border-width': 1, 'border-color': '#6b7280', 'border-style': 'dotted', 'opacity': 0.5 } },
  { selector: 'node.impact-dimmed',   style: { 'opacity': 0.2 } },
  // Edges
  {
    selector: 'edge',
    style: {
      'width': 1.5, 'line-color': '#4b5563', 'target-arrow-color': '#4b5563',
      'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
      'label': 'data(label)', 'font-size': '7px', 'color': '#6b7280',
      'text-rotation': 'autorotate', 'text-margin-y': -6,
    },
  },
  { selector: 'edge[resolution = "exact"]',      style: { 'line-style': 'solid',  'line-color': '#60a5fa', 'target-arrow-color': '#60a5fa' } },
  { selector: 'edge[resolution = "inferred"]',   style: { 'line-style': 'dashed', 'line-color': '#a78bfa', 'target-arrow-color': '#a78bfa' } },
  { selector: 'edge[resolution = "unresolved"]', style: { 'line-style': 'dotted', 'line-color': '#6b7280', 'target-arrow-color': '#6b7280' } },
]

function graphDataToElements(data: any): cytoscape.ElementDefinition[] {
  const elements: cytoscape.ElementDefinition[] = []
  if (!data) return elements
  data.nodes?.forEach((n: any) => elements.push({ data: n.data }))
  data.edges?.forEach((e: any) => elements.push({ data: e.data }))
  return elements
}

type RightPanel = 'details' | 'impact' | null
type ActiveFilter = { types: string[]; relationships: string[] }

// ── Component ─────────────────────────────────────────────────────────────────

export default function ArchitecturePage() {
  const { repoId } = useParams<{ repoId: string }>()
  const cyRef = useRef<cytoscape.Core | null>(null)

  const [selectedNode, setSelectedNode] = useState<any | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [rightPanel, setRightPanel] = useState<RightPanel>(null)
  const [impactTarget, setImpactTarget] = useState<{ id: string; name: string } | null>(null)
  const [impactModeActive, setImpactModeActive] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [showSearchDropdown, setShowSearchDropdown] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [analystOpen, setAnalystOpen] = useState(false)
  const [activeFilters, setActiveFilters] = useState<ActiveFilter>({
    types: ['Repository', 'Directory', 'File', 'Module', 'Class', 'Function', 'Method'],
    relationships: ['CONTAINS', 'IMPORTS', 'CALLS', 'INHERITS', 'DEFINED_IN'],
  })
  const [elements, setElements] = useState<cytoscape.ElementDefinition[]>([])

  const { data: repo } = useQuery({
    queryKey: ['repository', repoId],
    queryFn: () => api.getRepositories().then((repos: any[]) => repos.find(r => r.id === repoId)),
    enabled: !!repoId,
  })

  const isAnalyzed = !!(repo?.has_snapshot || repo?.last_analyzed_at)

  const { data: overviewData, isLoading: overviewLoading } = useQuery({
    queryKey: ['graphOverview', repoId],
    queryFn: () => api.getGraphOverview(repoId!),
    enabled: !!repoId && isAnalyzed,
  })

  const { data: healthData } = useQuery({
    queryKey: ['health', repoId],
    queryFn: () => api.getRepositoryHealth(repoId!),
    enabled: !!repoId && isAnalyzed,
    retry: false,
  })

  useEffect(() => {
    if (overviewData) {
      setElements(graphDataToElements(overviewData))
    }
  }, [overviewData])

  // ── Cytoscape ready ────────────────────────────────────────────────────────

  const handleCyReady = useCallback((cy: cytoscape.Core) => {
    cyRef.current = cy
    cy.on('tap', 'node', (evt) => {
      setSelectedNode(evt.target.data())
      if (rightPanel === 'impact') return // keep impact panel open
      setRightPanel('details')
    })
    cy.on('tap', (evt) => {
      if (evt.target === cy) { setSelectedNode(null); setRightPanel(null) }
    })
    cy.on('dblclick', 'node', (evt) => handleExpandNode(evt.target.id()))
  }, [rightPanel])

  // ── Navigation ────────────────────────────────────────────────────────────

  const navigateToEntity = useCallback((entityId: string) => {
    setSelectedNodeId(null)
    setTimeout(() => {
      setSelectedNodeId(entityId)
      setSearchOpen(false)
      handleNavigateToNode(entityId)
    }, 50)
  }, [])

  // ── Expand node ────────────────────────────────────────────────────────────

  const handleExpandNode = useCallback(async (nodeId: string) => {
    if (!repoId) return
    try {
      const data = await api.expandNode(repoId, nodeId)
      const cy = cyRef.current
      if (!cy) return
      const newEls = graphDataToElements(data)
      const existingIds = new Set(cy.elements().map(e => e.id()))
      const toAdd = newEls.filter(el => !existingIds.has(el.data.id!))
      if (toAdd.length > 0) {
        cy.add(toAdd)
        cy.layout({ name: 'cose', animate: true, animationDuration: 400, fit: false } as any).run()
      }
    } catch (err) { console.error('Expand failed', err) }
  }, [repoId])

  // ── Search ─────────────────────────────────────────────────────────────────

  const handleSearch = useCallback(async (q: string) => {
    setSearchQuery(q)
    if (!q.trim() || !repoId) { setSearchResults([]); setShowSearchDropdown(false); return }
    try {
      const results = await api.searchGraphNodes(repoId, q)
      setSearchResults(results)
      setShowSearchDropdown(true)
    } catch { setSearchResults([]) }
  }, [repoId])

  const handleSelectSearchResult = useCallback((result: any) => {
    const cy = cyRef.current
    setShowSearchDropdown(false)
    setSearchQuery(result.data?.label || '')
    if (cy) {
      cy.elements('node.highlighted').removeClass('highlighted')
      const nodeId = result.data?.id
      const existing = cy.getElementById(nodeId)
      if (existing.length) {
        existing.addClass('highlighted')
        cy.animate({ center: { eles: existing }, zoom: 1.8 }, { duration: 400 })
        setSelectedNode(existing.data())
        setRightPanel('details')
      } else {
        handleExpandNode(nodeId)
        setSelectedNode(result.data)
        setRightPanel('details')
      }
    }
  }, [handleExpandNode])

  // ── Impact mode ────────────────────────────────────────────────────────────

  const handleAnalyzeImpact = useCallback((nodeId: string, nodeName: string) => {
    setImpactTarget({ id: nodeId, name: nodeName })
    setRightPanel('impact')
    setImpactModeActive(true)
    // Mark the target visually
    const cy = cyRef.current
    if (cy) {
      cy.elements().removeClass('impact-target impact-direct impact-indirect impact-unresolved impact-dimmed')
      const target = cy.getElementById(nodeId)
      target.addClass('impact-target')
    }
  }, [])

  const handleHighlightNodes = useCallback((nodeIds: string[], mode: 'direct' | 'indirect' | 'unresolved') => {
    const cy = cyRef.current
    if (!cy) return
    const cls = `impact-${mode}`
    nodeIds.forEach(id => {
      const node = cy.getElementById(id)
      if (node.length) node.addClass(cls)
    })
    // Dim everything else
    cy.nodes().forEach(n => {
      if (!n.hasClass('impact-target') && !n.hasClass('impact-direct') &&
          !n.hasClass('impact-indirect') && !n.hasClass('impact-unresolved')) {
        n.addClass('impact-dimmed')
      }
    })
  }, [])

  const handleClearImpact = useCallback(() => {
    setImpactModeActive(false)
    setImpactTarget(null)
    setRightPanel(null)
    const cy = cyRef.current
    if (cy) {
      cy.elements().removeClass('impact-target impact-direct impact-indirect impact-unresolved impact-dimmed')
    }
  }, [])

  const handleNavigateToNode = useCallback((nodeId: string) => {
    const cy = cyRef.current
    if (!cy) return
    const existing = cy.getElementById(nodeId)
    if (existing.length) {
      cy.animate({ center: { eles: existing }, zoom: 1.8 }, { duration: 300 })
    } else {
      handleExpandNode(nodeId)
    }
  }, [handleExpandNode])

  // ── Filter toggles ─────────────────────────────────────────────────────────

  const toggleTypeFilter = (type: string) => {
    const cy = cyRef.current; if (!cy) return
    const selector = `node[type = "${type}"]`
    if (activeFilters.types.includes(type)) {
      (cy.$(selector) as any).hide()
      setActiveFilters(f => ({ ...f, types: f.types.filter(t => t !== type) }))
    } else {
      (cy.$(selector) as any).show()
      setActiveFilters(f => ({ ...f, types: [...f.types, type] }))
    }
  }

  const toggleRelFilter = (rel: string) => {
    const cy = cyRef.current; if (!cy) return
    const selector = `edge[label = "${rel}"]`
    if (activeFilters.relationships.includes(rel)) {
      (cy.$(selector) as any).hide()
      setActiveFilters(f => ({ ...f, relationships: f.relationships.filter(r => r !== rel) }))
    } else {
      (cy.$(selector) as any).show()
      setActiveFilters(f => ({ ...f, relationships: [...f.relationships, rel] }))
    }
  }

  const layout = {
    name: 'cose', idealEdgeLength: 120, nodeOverlap: 24, refresh: 20,
    fit: true, padding: 40, randomize: false, componentSpacing: 120,
    nodeRepulsion: 500000, edgeElasticity: 100, nestingFactor: 5,
    gravity: 80, numIter: 1000, initialTemp: 200, coolingFactor: 0.95, minTemp: 1.0,
  }

  if (overviewLoading)
    return <div className="flex h-screen items-center justify-center bg-gray-950 text-gray-400">Loading architecture graph…</div>

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 overflow-hidden">
      {/* Top bar */}
      <div className="p-3 border-b border-gray-800 flex items-center gap-4 z-20 flex-shrink-0">
        <Link to={`/repositories/${repoId}/overview`} className="text-gray-500 hover:text-white text-sm flex-shrink-0">← Back</Link>
        <div className="font-semibold text-white truncate flex-shrink-0 flex items-center gap-3">
          {repo?.name ?? 'Repository'} <span className="text-gray-500 font-normal">— Architecture</span>
          <button 
            onClick={() => setSearchOpen(!searchOpen)}
            disabled={!isAnalyzed}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors border ${!isAnalyzed ? 'opacity-50 cursor-not-allowed bg-gray-800 text-gray-500 border-gray-700' : searchOpen ? 'bg-blue-900/40 text-blue-400 border-blue-700/50' : 'bg-gray-800 text-gray-300 border-gray-700 hover:bg-gray-700 hover:text-white'}`}
          >
            🔍 Semantic Search
          </button>
          <button 
            onClick={() => setAnalystOpen(!analystOpen)}
            disabled={!isAnalyzed}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors border ${!isAnalyzed ? 'opacity-50 cursor-not-allowed bg-gray-800 text-gray-500 border-gray-700' : analystOpen ? 'bg-purple-900/40 text-purple-400 border-purple-700/50' : 'bg-purple-900/20 text-purple-300 border-purple-800/50 hover:bg-purple-800/40 hover:text-white'}`}
          >
            ⚡ AI Analyst
          </button>
        </div>

        {/* Impact mode banner */}
        {impactModeActive && (
          <div className="flex items-center gap-2 bg-orange-900/30 border border-orange-700/50 rounded px-3 py-1">
            <span className="text-orange-300 text-xs font-medium">⚡ Impact Mode</span>
            <button onClick={handleClearImpact} className="text-orange-500 hover:text-orange-300 text-xs">Clear</button>
          </div>
        )}

        {/* Search */}
        <div className="flex-1 relative max-w-sm">
          <input
            type="text"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            placeholder="Search classes, functions, files…"
            value={searchQuery}
            onChange={e => handleSearch(e.target.value)}
            onFocus={() => searchResults.length > 0 && setShowSearchDropdown(true)}
          />
          {showSearchDropdown && searchResults.length > 0 && (
            <div className="absolute top-full left-0 mt-1 w-full bg-gray-800 border border-gray-700 rounded shadow-xl z-50 max-h-64 overflow-y-auto">
              {searchResults.map((r: any) => (
                <button key={r.data?.id} className="w-full text-left px-3 py-2 hover:bg-gray-700 flex items-center gap-2 text-sm" onClick={() => handleSelectSearchResult(r)}>
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: NODE_TYPE_STYLES[r.data?.type]?.color ?? '#6b7280' }} />
                  <span className="text-gray-300 truncate">{r.data?.label}</span>
                  <span className="text-gray-600 text-xs flex-shrink-0">{r.data?.type}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <Link to={`/repositories/${repoId}/health`} className="text-sm text-blue-400 hover:text-blue-300 flex-shrink-0">Code Health →</Link>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <div className="w-52 border-r border-gray-800 flex flex-col gap-4 p-4 overflow-y-auto flex-shrink-0">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Node Types</div>
            <div className="space-y-1">
              {Object.entries(NODE_TYPE_STYLES).map(([type, style]) => (
                <button key={type} onClick={() => toggleTypeFilter(type)}
                  className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition ${activeFilters.types.includes(type) ? 'text-gray-200 hover:bg-gray-800' : 'text-gray-600 hover:bg-gray-800 line-through'}`}>
                  <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: style.color }} />
                  {type}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Relationships</div>
            <div className="space-y-1">
              {['CONTAINS', 'IMPORTS', 'CALLS', 'INHERITS', 'DEFINED_IN'].map(rel => (
                <button key={rel} onClick={() => toggleRelFilter(rel)}
                  className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition ${activeFilters.relationships.includes(rel) ? 'text-gray-300 hover:bg-gray-800' : 'text-gray-600 hover:bg-gray-800 line-through'}`}>
                  {rel}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Call Confidence</div>
            <div className="space-y-2 text-xs text-gray-400">
              <div className="flex items-center gap-2"><div className="w-6 border-t-2 border-solid border-blue-400" /> Exact</div>
              <div className="flex items-center gap-2"><div className="w-6 border-t-2 border-dashed border-purple-400" /> Inferred</div>
              <div className="flex items-center gap-2"><div className="w-6 border-t-2 border-dotted border-gray-500" /> Unresolved</div>
            </div>
          </div>

          {impactModeActive && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Impact Legend</div>
              <div className="space-y-2 text-xs text-gray-400">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full border-2 border-orange-500" /> Target</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full border-2 border-orange-400" /> Direct</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full border-2 border-dashed border-orange-300/50" /> Indirect</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full border border-dotted border-gray-500" /> Unresolved</div>
              </div>
            </div>
          )}

          {healthData?.health && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Snapshot Stats</div>
              <div className="space-y-1 text-xs">
                {[
                  ['Modules', healthData.health.total_modules],
                  ['Classes', healthData.health.total_classes],
                  ['Functions', healthData.health.total_functions],
                  ['Avg CC', healthData.health.average_complexity],
                  ['Cycles', healthData.health.circular_dependencies],
                ].map(([label, val]) => (
                  <div key={String(label)} className="flex justify-between">
                    <span className="text-gray-500">{label}</span>
                    <span className={`font-mono text-gray-300 ${label === 'Cycles' && Number(val) > 0 ? 'text-red-400' : ''}`}>{val}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-xs text-gray-600 mt-auto pt-4 border-t border-gray-800 leading-relaxed">
            <strong className="text-gray-500">Click</strong> to select<br />
            <strong className="text-gray-500">Dbl-click</strong> to expand<br />
            <strong className="text-gray-500">⚡</strong> in panel to analyze impact
          </div>
        </div>

        {searchOpen && (
          <SemanticSearchPanel
            repoId={repoId!}
            onSelectResult={navigateToEntity}
            onClose={() => setSearchOpen(false)}
          />
        )}

        {analystOpen && (
          <AnalystPanel
            repoId={repoId!}
            onClose={() => setAnalystOpen(false)}
          />
        )}

        {/* Main canvas */}
        <div className="flex-1 relative bg-gray-950" onClick={() => setShowSearchDropdown(false)}>
          {elements.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-600 text-sm">No graph data. Run analysis first.</div>
          ) : (
            <CytoscapeComponent
              elements={elements}
              style={{ width: '100%', height: '100%' }}
              layout={layout as any}
              stylesheet={STYLESHEET}
              cy={handleCyReady}
            />
          )}
        </div>

        {/* Right panel — Details OR Impact */}
        {rightPanel === 'details' && selectedNode && (
          <EntityDetailsPanel
            repoId={repoId!}
            node={selectedNode}
            onClose={() => setRightPanel(null)}
            onAnalyzeImpact={handleAnalyzeImpact}
          />
        )}
        {rightPanel === 'impact' && impactTarget && (
          <ImpactPanel
            repoId={repoId!}
            entityId={impactTarget.id}
            entityName={impactTarget.name}
            onClose={handleClearImpact}
            onHighlightNodes={handleHighlightNodes}
            onNavigateToNode={handleNavigateToNode}
          />
        )}
      </div>
    </div>
  )
}
