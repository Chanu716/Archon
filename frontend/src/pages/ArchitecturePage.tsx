import { useState, useCallback, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import EntityDetailsPanel from '@/components/EntityDetailsPanel'
import ImpactPanel from '@/components/ImpactPanel'
import SemanticSearchPanel from '@/components/SemanticSearchPanel'
import AnalystPanel from '@/components/AnalystPanel'
import ThreeDArchitectureGraph from '@/components/ThreeDArchitectureGraph'
import TwoDArchitectureGraph from '@/components/TwoDArchitectureGraph'
import { Box, Layers, Info, Sparkles, Terminal, Search, Zap } from 'lucide-react'

const NODE_TYPE_STYLES: Record<string, { color: string }> = {
  Repository: { color: '#f59e0b' },
  Directory:  { color: '#fb923c' },
  File:       { color: '#818cf8' },
  Module:     { color: '#3b82f6' },
  Class:      { color: '#10b981' },
  Function:   { color: '#ec4899' },
  Method:     { color: '#a78bfa' },
}

type RightPanel = 'details' | 'impact' | null
type ActiveFilter = { types: string[]; relationships: string[] }

export default function ArchitecturePage() {
  const { repoId } = useParams<{ repoId: string }>()

  const [viewMode, setViewMode] = useState<'3d' | '2d'>('3d')
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] })
  const [selectedNode, setSelectedNode] = useState<any | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [rightPanel, setRightPanel] = useState<RightPanel>(null)
  const [impactTarget, setImpactTarget] = useState<{ id: string; name: string } | null>(null)
  const [impactModeActive, setImpactModeActive] = useState(false)
  const [impactedNodeIds, setImpactedNodeIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [showSearchDropdown, setShowSearchDropdown] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [analystOpen, setAnalystOpen] = useState(false)
  const [isExpanding, setIsExpanding] = useState(false)

  const [activeFilters, setActiveFilters] = useState<ActiveFilter>({
    types: ['Repository', 'Directory', 'File', 'Module', 'Class', 'Function', 'Method'],
    relationships: ['CONTAINS', 'DEFINES', 'IMPORTS', 'CALLS', 'INHERITS', 'CHANGED', 'AUTHORED'],
  })

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
      setGraphData(overviewData)
    }
  }, [overviewData])

  const handleExpandNode = useCallback(async (nodeId: string) => {
    if (!repoId) return
    setIsExpanding(true)
    try {
      const result = await api.expandNode(repoId, nodeId)
      if (result && ((result.nodes && result.nodes.length > 0) || (result.edges && result.edges.length > 0))) {
        setGraphData(prev => {
          const existingNodeIds = new Set((prev.nodes || []).map((n: any) => n.data.id))
          const existingEdgeIds = new Set((prev.edges || []).map((e: any) => e.data.id))

          const newNodes = (result.nodes || []).filter((n: any) => !existingNodeIds.has(n.data.id))
          const newEdges = (result.edges || []).filter((e: any) => !existingEdgeIds.has(e.data.id))

          if (newNodes.length === 0 && newEdges.length === 0) return prev

          return {
            nodes: [...(prev.nodes || []), ...newNodes],
            edges: [...(prev.edges || []), ...newEdges],
          }
        })
      }
    } catch (err) {
      console.error('Expand failed', err)
    } finally {
      setIsExpanding(false)
    }
  }, [repoId])

  const handleNodeSelect = useCallback((nodeData: any) => {
    setSelectedNode(nodeData)
    setSelectedNodeId(nodeData.id)
    if (rightPanel !== 'impact') {
      setRightPanel('details')
    }
    handleExpandNode(nodeData.id)
  }, [rightPanel, handleExpandNode])

  const handleSearch = useCallback(async (q: string) => {
    setSearchQuery(q)
    const trimmed = q.trim().toLowerCase()
    if (!trimmed) {
      setSearchResults([])
      setShowSearchDropdown(false)
      return
    }

    // 1. Instant local in-memory search across currently loaded graphData nodes
    const localMatches = (graphData.nodes || [])
      .filter((n: any) => {
        const label = String(n.data?.label || '').toLowerCase()
        const name = String(n.data?.name || '').toLowerCase()
        const path = String(n.data?.path || '').toLowerCase()
        const qname = String(n.data?.qualified_name || '').toLowerCase()
        return label.includes(trimmed) || name.includes(trimmed) || path.includes(trimmed) || qname.includes(trimmed)
      })
      .map((n: any) => ({ data: n.data }))

    setSearchResults(localMatches)
    setShowSearchDropdown(true)

    // 2. Fetch all matching nodes from backend Neo4j graph database in parallel
    if (repoId) {
      try {
        const remoteResults = await api.searchGraphNodes(repoId, q)
        if (remoteResults && Array.isArray(remoteResults)) {
          setSearchResults(prev => {
            const seenIds = new Set(prev.map(p => p.data?.id))
            const newMatches = remoteResults.filter((r: any) => r.data?.id && !seenIds.has(r.data.id))
            return [...prev, ...newMatches]
          })
        }
      } catch (err) {
        console.error('Remote search error:', err)
      }
    }
  }, [graphData.nodes, repoId])

  const handleSelectSearchResult = useCallback((result: any) => {
    setShowSearchDropdown(false)
    const label = result.data?.label || result.data?.name || ''
    setSearchQuery(label)
    const nodeId = result.data?.id
    if (!nodeId) return

    setSelectedNodeId(nodeId)
    setSelectedNode(result.data)
    if (rightPanel !== 'impact') {
      setRightPanel('details')
    }

    // Immediately inject the node into local graphData if not already present
    setGraphData(prev => {
      const exists = (prev.nodes || []).some((n: any) => n.data.id === nodeId)
      if (!exists && result) {
        return {
          nodes: [...(prev.nodes || []), result],
          edges: prev.edges || [],
        }
      }
      return prev
    })

    handleExpandNode(nodeId)
  }, [rightPanel, handleExpandNode])

  const handleSearchKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (searchResults.length > 0) {
        handleSelectSearchResult(searchResults[0])
      }
    } else if (e.key === 'Escape') {
      setShowSearchDropdown(false)
    }
  }, [searchResults, handleSelectSearchResult])

  const navigateToEntity = useCallback(async (entityId: string) => {
    setSearchOpen(false)
    setSelectedNodeId(entityId)
    setRightPanel('details')

    if (repoId) {
      try {
        const nodeDetails = await api.getNodeDetails(repoId, entityId)
        if (nodeDetails && nodeDetails.data) {
          setSelectedNode(nodeDetails.data)
          setGraphData(prev => {
            const exists = (prev.nodes || []).some((n: any) => n.data.id === entityId)
            if (!exists) {
              return {
                nodes: [...(prev.nodes || []), nodeDetails],
                edges: prev.edges || [],
              }
            }
            return prev
          })
        }
      } catch (err) {
        console.error('Failed to load node details for navigation:', err)
      }
    }

    handleExpandNode(entityId)
  }, [repoId, handleExpandNode])

  const handleAnalyzeImpact = useCallback((nodeId: string, nodeName: string) => {
    setImpactTarget({ id: nodeId, name: nodeName })
    setRightPanel('impact')
    setImpactModeActive(true)
  }, [])

  const handleHighlightNodes = useCallback((nodeIds: string[], _mode: 'direct' | 'indirect' | 'unresolved') => {
    setImpactedNodeIds(new Set(nodeIds))
  }, [])

  const handleClearImpact = useCallback(() => {
    setImpactModeActive(false)
    setImpactTarget(null)
    setRightPanel(selectedNode ? 'details' : null)
    setImpactedNodeIds(new Set())
  }, [selectedNode])

  const handleNavigateToNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId)
    handleExpandNode(nodeId)
  }, [handleExpandNode])

  const toggleTypeFilter = (type: string) => {
    setActiveFilters(f => ({
      ...f,
      types: f.types.includes(type) ? f.types.filter(t => t !== type) : [...f.types, type],
    }))
  }

  const toggleRelFilter = (rel: string) => {
    setActiveFilters(f => ({
      ...f,
      relationships: f.relationships.includes(rel)
        ? f.relationships.filter(r => r !== rel)
        : [...f.relationships, rel],
    }))
  }

  if (overviewLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-black text-cyan-400 font-pixel">
        <div className="flex flex-col items-center gap-3 pixel-box p-8">
          <Terminal className="w-6 h-6 animate-spin text-cyan-400" />
          <span className="text-xs">[ INITIALIZING GRAPH TOPOLOGY… ]</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-black text-white overflow-hidden select-none font-mono">
      {/* Top Retro Terminal Header */}
      <div className="px-4 py-2.5 border-b-2 border-white bg-black flex items-center justify-between gap-4 z-20 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Link
            to={`/repositories/${repoId}/overview`}
            className="pixel-btn text-[11px] px-2 py-1 hover:border-cyan-400 hover:text-cyan-400"
          >
            ← [ ESC ]
          </Link>
          <div className="flex items-center gap-2">
            <span className="font-pixel text-xs text-white">
              {repo?.name ?? 'ARCHON'}
            </span>
            <span className="text-neutral-500 text-xs font-mono">:: ARCHITECTURE_GRAPH</span>
          </div>

          {/* Action Modals */}
          <div className="flex items-center gap-2 ml-2">
            <button
              onClick={() => setSearchOpen(!searchOpen)}
              disabled={!isAnalyzed}
              className={`pixel-btn text-[10px] py-1 ${searchOpen ? 'pixel-btn-cyan' : ''}`}
            >
              <Search className="w-3 h-3 mr-1 inline" />
              [ SEARCH ]
            </button>

            <button
              onClick={() => setAnalystOpen(!analystOpen)}
              disabled={!isAnalyzed}
              className={`pixel-btn text-[10px] py-1 ${analystOpen ? 'pixel-btn-cyan' : ''}`}
            >
              <Zap className="w-3 h-3 mr-1 inline text-cyan-400" />
              [ AI_ANALYST ]
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Active Node Inspector Tag */}
          {selectedNode && (
            <button
              onClick={() => setRightPanel(rightPanel ? null : 'details')}
              className={`pixel-btn text-[10px] py-1 ${rightPanel === 'details' ? 'pixel-btn-cyan' : ''}`}
            >
              <Info className="w-3 h-3 mr-1 inline" />
              [ INSPECTOR: <span className="text-cyan-300 font-bold truncate max-w-[80px] inline-block align-bottom">{selectedNode.label}</span> ]
            </button>
          )}

          {/* Subtree Expand Ticker */}
          {isExpanding && (
            <span className="pixel-tag-cyan text-[10px] flex items-center gap-1">
              <Sparkles className="w-3 h-3 animate-spin" />
              EXPANDING_AST…
            </span>
          )}

          {/* 3D / 2D View Switcher */}
          <div className="flex items-center border-2 border-white bg-black p-0.5 shadow-pixel-sm">
            <button
              onClick={() => setViewMode('3d')}
              className={`flex items-center gap-1 font-pixel text-[10px] px-2.5 py-1 transition-all ${
                viewMode === '3d'
                  ? 'bg-cyan-400 text-black font-bold shadow-sm'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Box className="w-3 h-3" />
              3D_GALAXY
            </button>
            <button
              onClick={() => setViewMode('2d')}
              className={`flex items-center gap-1 font-pixel text-[10px] px-2.5 py-1 transition-all ${
                viewMode === '2d'
                  ? 'bg-cyan-400 text-black font-bold shadow-sm'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Layers className="w-3 h-3" />
              2D_PLANAR
            </button>
          </div>

          {/* Search Query Input */}
          <div className="relative w-64 hidden md:block">
            <div className="relative flex items-center">
              <input
                type="text"
                className="w-full pixel-input pl-3 pr-7 py-1 text-xs text-white placeholder-neutral-600 focus:outline-none"
                placeholder="> query_symbol…"
                value={searchQuery}
                onChange={e => handleSearch(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                onFocus={() => {
                  if (searchQuery.trim().length > 0) {
                    handleSearch(searchQuery)
                  }
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => {
                    setSearchQuery('')
                    setSearchResults([])
                    setShowSearchDropdown(false)
                  }}
                  className="absolute right-2 text-neutral-500 hover:text-white text-xs font-mono"
                  title="Clear search"
                >
                  ✕
                </button>
              )}
            </div>

            {showSearchDropdown && searchQuery.trim().length > 0 && (
              <div className="absolute top-full right-0 mt-1 w-80 pixel-box bg-black shadow-pixel z-50 max-h-72 overflow-y-auto">
                {searchResults.length === 0 ? (
                  <div className="p-3 text-neutral-500 font-pixel text-[10px] text-center">
                    [ NO_MATCHING_SYMBOLS ]
                  </div>
                ) : (
                  searchResults.map((r: any) => (
                    <button
                      key={r.data?.id}
                      className="w-full text-left px-3 py-2 hover:bg-neutral-900 border-b border-neutral-800 flex items-center gap-2 text-xs transition-colors group"
                      onClick={() => handleSelectSearchResult(r)}
                    >
                      <span
                        className="w-2.5 h-2.5 flex-shrink-0"
                        style={{ backgroundColor: NODE_TYPE_STYLES[r.data?.type]?.color ?? '#00f3ff' }}
                      />
                      <div className="overflow-hidden flex-1">
                        <div className="text-white truncate font-mono font-bold group-hover:text-cyan-400">
                          {r.data?.label || r.data?.name}
                        </div>
                        {r.data?.path && (
                          <div className="text-neutral-500 text-[10px] truncate font-mono">
                            {r.data.path}
                          </div>
                        )}
                      </div>
                      <span className="pixel-tag text-[9px] ml-auto flex-shrink-0">
                        {r.data?.type || 'Node'}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden relative">
        {/* Left Retro Terminal Sidebar */}
        <div className="w-60 border-r-2 border-white bg-black flex flex-col gap-4 p-3.5 overflow-y-auto flex-shrink-0 text-xs">
          <div>
            <div className="font-pixel text-[10px] text-cyan-400 uppercase tracking-wider mb-2">
              [ NODE_TYPES ]
            </div>
            <div className="space-y-1">
              {Object.entries(NODE_TYPE_STYLES).map(([type, style]) => {
                const isActive = activeFilters.types.includes(type)
                return (
                  <button
                    key={type}
                    onClick={() => toggleTypeFilter(type)}
                    className={`w-full flex items-center gap-2 px-2 py-1 text-left font-mono text-[11px] transition border ${
                      isActive
                        ? 'border-neutral-700 bg-neutral-950 text-white hover:border-cyan-400'
                        : 'border-transparent text-neutral-600 line-through opacity-50'
                    }`}
                  >
                    <span
                      className="w-2.5 h-2.5 flex-shrink-0"
                      style={{ backgroundColor: style.color }}
                    />
                    <span>{type}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <div className="font-pixel text-[10px] text-cyan-400 uppercase tracking-wider mb-2">
              [ RELATIONSHIPS ]
            </div>
            <div className="space-y-1">
              {['CONTAINS', 'DEFINES', 'IMPORTS', 'CALLS', 'INHERITS'].map(rel => {
                const isActive = activeFilters.relationships.includes(rel)
                return (
                  <button
                    key={rel}
                    onClick={() => toggleRelFilter(rel)}
                    className={`w-full flex items-center gap-2 px-2 py-1 text-left font-mono text-[11px] transition border ${
                      isActive
                        ? 'border-neutral-700 bg-neutral-950 text-neutral-300 hover:border-cyan-400'
                        : 'border-transparent text-neutral-600 line-through opacity-50'
                    }`}
                  >
                    <span>{rel}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {healthData?.health && (
            <div className="border border-neutral-800 bg-neutral-950 p-2.5">
              <div className="font-pixel text-[9px] text-neutral-400 uppercase mb-2">
                [ AST_SNAPSHOT ]
              </div>
              <div className="space-y-1 text-[11px] font-mono">
                {[
                  ['MODULES', healthData.health.total_modules],
                  ['CLASSES', healthData.health.total_classes],
                  ['FUNCTIONS', healthData.health.total_functions],
                  ['AVG_CC', healthData.health.average_complexity],
                  ['CYCLES', healthData.health.circular_dependencies],
                ].map(([label, val]) => (
                  <div key={String(label)} className="flex justify-between items-center text-neutral-400">
                    <span>{label}:</span>
                    <span className={`font-mono font-bold text-white ${label === 'CYCLES' && Number(val) > 0 ? 'text-red-400' : ''}`}>
                      {val}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-[10px] text-neutral-500 mt-auto pt-3 border-t border-neutral-800 font-mono leading-relaxed">
            <strong className="text-neutral-300">CLICK_NODE</strong>: Expand sub-tree<br />
            <strong className="text-neutral-300">HOVER_NODE</strong>: Trace dependencies<br />
            <strong className="text-neutral-300">INSPECTOR</strong>: Metric analysis
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

        {/* Main Canvas */}
        <div className="flex-1 min-w-0 relative bg-black" onClick={() => setShowSearchDropdown(false)}>
          {!graphData || (!graphData.nodes?.length && !graphData.edges?.length) ? (
            <div className="flex items-center justify-center h-full text-neutral-600 font-pixel text-xs">
              [ NO_AST_DATA :: RUN_ANALYSIS_FIRST ]
            </div>
          ) : viewMode === '3d' ? (
            <ThreeDArchitectureGraph
              data={graphData}
              activeFilters={activeFilters}
              selectedNodeId={selectedNode?.id || selectedNodeId}
              focusedNodeId={selectedNodeId}
              impactModeActive={impactModeActive}
              impactTargetId={impactTarget?.id}
              impactedNodeIds={impactedNodeIds}
              onNodeClick={handleNodeSelect}
              onNodeDoubleClick={(nodeId) => handleExpandNode(nodeId)}
            />
          ) : (
            <TwoDArchitectureGraph
              data={graphData}
              activeFilters={activeFilters}
              selectedNodeId={selectedNode?.id || selectedNodeId}
              focusedNodeId={selectedNodeId}
              impactModeActive={impactModeActive}
              impactTargetId={impactTarget?.id}
              impactedNodeIds={impactedNodeIds}
              onNodeClick={handleNodeSelect}
              onNodeDoubleClick={(nodeId) => handleExpandNode(nodeId)}
            />
          )}
        </div>

        {/* Right Panel — Details OR Impact */}
        {rightPanel === 'details' && selectedNode && (
          <EntityDetailsPanel
            repoId={repoId!}
            node={selectedNode}
            onClose={() => setRightPanel(null)}
            onAnalyzeImpact={handleAnalyzeImpact}
            onExpandNode={handleExpandNode}
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
