import { useEffect, useRef, useState, useCallback } from 'react'
import cytoscape from 'cytoscape'
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  LayoutGrid,
  Eye,
  EyeOff,
  Sparkles,
} from 'lucide-react'

const NODE_TYPE_COLORS: Record<string, string> = {
  Repository: '#f59e0b', // Amber
  Directory: '#fb923c',  // Orange
  File: '#818cf8',       // Indigo
  Module: '#3b82f6',     // Sky Blue
  Class: '#10b981',      // Emerald Green
  Function: '#ec4899',   // Pink
  Method: '#a78bfa',     // Violet
  Unknown: '#9ca3af',    // Gray
}

const NODE_TYPE_SHAPES: Record<string, cytoscape.Css.NodeShape> = {
  Repository: 'star',
  Directory: 'round-rectangle',
  File: 'hexagon',
  Module: 'round-rectangle',
  Class: 'ellipse',
  Function: 'round-diamond',
  Method: 'diamond',
  Unknown: 'ellipse',
}

const LINK_TYPE_COLORS: Record<string, string> = {
  CONTAINS: '#4b5563',
  DEFINES: '#818cf8',
  IMPORTS: '#60a5fa',
  CALLS: '#ec4899',
  INHERITS: '#10b981',
  CHANGED: '#f97316',
  AUTHORED: '#fbbf24',
}

export interface TwoDGraphProps {
  data: {
    nodes?: Array<{ data: any }>
    edges?: Array<{ data: any }>
  } | null
  activeFilters: {
    types: string[]
    relationships: string[]
  }
  selectedNodeId?: string | null
  focusedNodeId?: string | null
  impactModeActive?: boolean
  impactTargetId?: string | null
  impactedNodeIds?: Set<string>
  onNodeClick?: (nodeData: any) => void
  onNodeDoubleClick?: (nodeId: string) => void
  onBackgroundClick?: () => void
}

export default function TwoDArchitectureGraph({
  data,
  activeFilters,
  selectedNodeId,
  focusedNodeId,
  impactModeActive = false,
  impactTargetId = null,
  impactedNodeIds = new Set(),
  onNodeClick,
  onNodeDoubleClick,
  onBackgroundClick,
}: TwoDGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const layoutRef = useRef<cytoscape.Layouts | null>(null)
  const [layoutName, setLayoutName] = useState<'cose' | 'breadthfirst' | 'concentric' | 'circle'>('cose')
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)
  const [, setHoveredNodeId] = useState<string | null>(null)

  const propsRef = useRef({
    onNodeClick,
    onNodeDoubleClick,
    onBackgroundClick,
  })

  useEffect(() => {
    propsRef.current = {
      onNodeClick,
      onNodeDoubleClick,
      onBackgroundClick,
    }
  }, [onNodeClick, onNodeDoubleClick, onBackgroundClick])

  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      boxSelectionEnabled: false,
      autounselectify: false,
      wheelSensitivity: 0.25,
      minZoom: 0.15,
      maxZoom: 3.5,
      style: [
        // Base Node Style
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 6,
            'color': '#ffffff',
            'font-size': '10px',
            'font-family': '"JetBrains Mono", monospace',
            'font-weight': 600,
            'background-color': '#0a0a0a',
            'border-width': 2,
            'border-color': '#ffffff',
            'width': 34,
            'height': 34,
            'text-max-width': '100px',
            'text-wrap': 'ellipsis',
            'text-background-color': '#000000',
            'text-background-opacity': 0.9,
            'text-background-padding': '2px',
            'text-background-shape': 'roundrectangle',
            'transition-property': 'background-color, border-color, border-width, opacity, width, height',
            'transition-duration': 150,
          },
        },
        // Shape & Type styles (vibrant color bodies with sharp pixel borders)
        ...Object.entries(NODE_TYPE_COLORS).map(([type, color]) => ({
          selector: `node[type = "${type}"]`,
          style: {
            'background-color': color,
            'shape': NODE_TYPE_SHAPES[type] || 'ellipse',
            'border-color': '#ffffff',
            'border-width': 2,
          } as cytoscape.Css.Node,
        })),
        {
          selector: 'node[type = "Repository"]',
          style: { 'width': 48, 'height': 48, 'font-size': '11px', 'font-weight': 700, 'border-width': 3 },
        },
        {
          selector: 'node[type = "Module"], node[type = "Directory"]',
          style: { 'width': 40, 'height': 40, 'font-size': '10px' },
        },
        // Selected Node
        {
          selector: 'node:selected, node.selected-node',
          style: {
            'border-width': 4,
            'border-color': '#00f3ff',
            'overlay-color': '#00f3ff',
            'overlay-padding': 6,
            'overlay-opacity': 0.4,
            'z-index': 999,
          },
        },
        // Focused / Highlighted
        {
          selector: 'node.highlighted',
          style: {
            'border-width': 4,
            'border-color': '#00f3ff',
            'overlay-color': '#00f3ff',
            'overlay-padding': 8,
            'overlay-opacity': 0.45,
            'z-index': 1000,
          },
        },
        // Hover Neighborhood
        {
          selector: 'node.hover-neighbor',
          style: {
            'border-width': 3,
            'border-color': '#00ffcc',
            'opacity': 1,
            'z-index': 900,
          },
        },
        // Dimmed nodes
        {
          selector: 'node.dimmed',
          style: {
            'opacity': 0.15,
            'text-opacity': 0.1,
          },
        },
        // Impact States
        {
          selector: 'node.impact-target',
          style: {
            'border-width': 5,
            'border-color': '#f97316',
            'overlay-color': '#f97316',
            'overlay-padding': 10,
            'overlay-opacity': 0.5,
            'z-index': 1000,
          },
        },
        {
          selector: 'node.impact-direct',
          style: {
            'border-width': 3.5,
            'border-color': '#fb923c',
            'opacity': 1,
            'z-index': 950,
          },
        },
        {
          selector: 'node.impact-indirect',
          style: {
            'border-width': 2.5,
            'border-color': '#fdba74',
            'border-style': 'dashed',
            'opacity': 0.85,
            'z-index': 900,
          },
        },
        // Base Edges
        {
          selector: 'edge',
          style: {
            'width': 1.6,
            'line-color': '#404040',
            'target-arrow-color': '#404040',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.85,
            'curve-style': 'bezier',
            'opacity': 0.7,
            'label': '',
            'font-size': '8px',
            'color': '#a3a3a3',
            'text-rotation': 'autorotate',
            'text-margin-y': -6,
            'text-background-color': '#000000',
            'text-background-opacity': 0.9,
            'text-background-padding': '1px',
            'text-background-shape': 'roundrectangle',
            'transition-property': 'line-color, width, opacity',
            'transition-duration': 150,
          },
        },
        // Relationship edge colors
        ...Object.entries(LINK_TYPE_COLORS).map(([label, color]) => ({
          selector: `edge[label = "${label}"]`,
          style: {
            'line-color': color,
            'target-arrow-color': color,
          } as cytoscape.Css.Edge,
        })),
        {
          selector: 'edge.active-edge',
          style: {
            'width': 3.0,
            'line-color': '#00f3ff',
            'target-arrow-color': '#00f3ff',
            'opacity': 1,
            'z-index': 800,
          },
        },
        {
          selector: 'edge.dimmed',
          style: {
            'opacity': 0.08,
          },
        },
        {
          selector: 'edge.show-label',
          style: {
            'label': 'data(label)',
          },
        },
      ],
    })

    // Handlers
    cy.on('tap', 'node', (evt) => {
      const nodeData = evt.target.data()
      propsRef.current.onNodeClick?.(nodeData)
    })

    cy.on('dbltap', 'node', (evt) => {
      const nodeId = evt.target.id()
      propsRef.current.onNodeDoubleClick?.(nodeId)
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        propsRef.current.onBackgroundClick?.()
      }
    })

    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target
      setHoveredNodeId(node.id())
      const neighborhood = node.closedNeighborhood()
      cy.elements().addClass('dimmed')
      neighborhood.removeClass('dimmed')
      node.addClass('highlighted')
      neighborhood.nodes().addClass('hover-neighbor')
      neighborhood.edges().addClass('active-edge')
    })

    cy.on('mouseout', 'node', () => {
      setHoveredNodeId(null)
      cy.elements().removeClass('dimmed highlighted hover-neighbor active-edge')
    })

    cyRef.current = cy

    return () => {
      if (layoutRef.current) {
        layoutRef.current.stop()
      }
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  // Sync data & activeFilters
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !data) return

    const rawNodes = data.nodes || []
    const rawEdges = data.edges || []

    const filteredNodes = rawNodes
      .filter(n => activeFilters.types.includes(n.data.type || 'Unknown'))
      .map(n => ({
        group: 'nodes' as const,
        data: {
          ...n.data,
          id: n.data.id,
          label: n.data.label || n.data.name || n.data.path || 'Unnamed',
          type: n.data.type || 'Unknown',
        },
      }))

    const validIdSet = new Set(filteredNodes.map(n => n.data.id))

    const filteredEdges = rawEdges
      .filter(e => {
        const sId = e.data.source
        const tId = e.data.target
        const label = e.data.label || 'CONTAINS'
        return validIdSet.has(sId) && validIdSet.has(tId) && activeFilters.relationships.includes(label)
      })
      .map(e => ({
        group: 'edges' as const,
        data: {
          ...e.data,
          id: e.data.id,
          source: e.data.source,
          target: e.data.target,
          label: e.data.label || 'CONTAINS',
        },
      }))

    try {
      if (layoutRef.current) {
        layoutRef.current.stop()
      }

      cy.elements().remove()
      if (filteredNodes.length > 0) {
        cy.add([...filteredNodes, ...filteredEdges])

        const layoutOptions: any = {
          name: layoutName,
          animate: true,
          animationDuration: 500,
          fit: true,
          padding: 50,
        }

        if (layoutName === 'cose') {
          layoutOptions.idealEdgeLength = 100
          layoutOptions.nodeOverlap = 30
          layoutOptions.refresh = 20
          layoutOptions.componentSpacing = 110
          layoutOptions.nodeRepulsion = 400000
          layoutOptions.edgeElasticity = 100
          layoutOptions.nestingFactor = 5
          layoutOptions.gravity = 60
          layoutOptions.numIter = 800
        } else if (layoutName === 'breadthfirst') {
          layoutOptions.directed = true
          layoutOptions.spacingFactor = 1.3
          layoutOptions.circle = false
        } else if (layoutName === 'concentric') {
          layoutOptions.spacingFactor = 1.4
          layoutOptions.concentric = (node: any) => {
            const type = node.data('type')
            if (type === 'Repository') return 10
            if (type === 'Directory' || type === 'Module') return 7
            if (type === 'File') return 5
            if (type === 'Class') return 3
            return 1
          }
          layoutOptions.levelWidth = () => 2
        }

        const layout = cy.layout(layoutOptions)
        layoutRef.current = layout
        layout.run()
      }
    } catch (err) {
      console.error('Failed to update cytoscape graph:', err)
    }
  }, [data, activeFilters, layoutName])

  // Sync edge label visibility
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    if (showEdgeLabels) {
      cy.edges().addClass('show-label')
    } else {
      cy.edges().removeClass('show-label')
    }
  }, [showEdgeLabels])

  // Sync Selection & Impact Modes
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.elements().removeClass('selected-node impact-target impact-direct impact-indirect impact-dimmed')

    if (impactModeActive && impactTargetId) {
      const target = cy.getElementById(impactTargetId)
      if (target.length) target.addClass('impact-target')

      impactedNodeIds.forEach(id => {
        const node = cy.getElementById(id)
        if (node.length) node.addClass('impact-direct')
      })

      cy.nodes().forEach(n => {
        if (n.id() !== impactTargetId && !impactedNodeIds.has(n.id())) {
          n.addClass('impact-dimmed')
        }
      })
    } else if (selectedNodeId) {
      const selected = cy.getElementById(selectedNodeId)
      if (selected.length) {
        selected.addClass('selected-node')
      }
    }
  }, [selectedNodeId, impactModeActive, impactTargetId, impactedNodeIds])

  // Camera focus
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !focusedNodeId) return

    const node = cy.getElementById(focusedNodeId)
    if (node.length) {
      cy.animate(
        {
          center: { eles: node },
          zoom: 1.6,
        },
        { duration: 400 }
      )
    }
  }, [focusedNodeId])

  const handleZoomIn = useCallback(() => {
    const cy = cyRef.current
    if (cy) cy.zoom({ level: cy.zoom() * 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }, [])

  const handleZoomOut = useCallback(() => {
    const cy = cyRef.current
    if (cy) cy.zoom({ level: cy.zoom() * 0.75, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }, [])

  const handleFit = useCallback(() => {
    const cy = cyRef.current
    if (cy) cy.animate({ fit: { eles: cy.elements(), padding: 40 } }, { duration: 400 })
  }, [])

  const handleResetLayout = useCallback(() => {
    const cy = cyRef.current
    if (!cy) return
    if (layoutRef.current) layoutRef.current.stop()
    const layout = cy.layout({
      name: layoutName,
      animate: true,
      animationDuration: 500,
      fit: true,
      padding: 50,
    } as any)
    layoutRef.current = layout
    layout.run()
  }, [layoutName])

  return (
    <div className="relative w-full h-full bg-black overflow-hidden select-none">
      <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Cyber-Pixel 2D Toolbar */}
      <div className="absolute bottom-5 right-5 z-20 flex items-center gap-1.5 pixel-box p-1.5 shadow-pixel">
        <div className="flex items-center gap-1 bg-neutral-900 px-2 py-1 border border-neutral-700 text-xs text-neutral-300">
          <LayoutGrid className="w-3.5 h-3.5 text-cyan-400" />
          <select
            value={layoutName}
            onChange={(e) => setLayoutName(e.target.value as any)}
            className="bg-transparent text-[11px] text-white focus:outline-none cursor-pointer font-mono"
            title="Select 2D Layout Engine"
          >
            <option value="cose" className="bg-black text-white">FORCE (CoSE)</option>
            <option value="breadthfirst" className="bg-black text-white">TREE (DAG)</option>
            <option value="concentric" className="bg-black text-white">CONCENTRIC</option>
            <option value="circle" className="bg-black text-white">CIRCLE RING</option>
          </select>
        </div>

        <button
          onClick={() => setShowEdgeLabels(!showEdgeLabels)}
          className={`p-1.5 border border-neutral-700 hover:border-cyan-400 transition-colors ${
            showEdgeLabels ? 'bg-cyan-400 text-black border-cyan-400' : 'text-neutral-300 hover:text-white'
          }`}
          title={showEdgeLabels ? 'Hide Edge Labels' : 'Show Edge Labels'}
        >
          {showEdgeLabels ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
        </button>

        <div className="h-4 w-px bg-neutral-800 my-auto" />

        <button
          onClick={handleZoomIn}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>

        <button
          onClick={handleZoomOut}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <button
          onClick={handleFit}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Fit to Screen"
        >
          <Maximize2 className="w-4 h-4" />
        </button>

        <button
          onClick={handleResetLayout}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Re-run Layout"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Cyber-Pixel Hint Banner */}
      <div className="absolute top-3 left-3 z-10 pointer-events-none flex items-center gap-2 border border-neutral-800 bg-black/90 px-3 py-1 text-[11px] text-neutral-400 font-mono shadow-pixel-sm">
        <Sparkles className="w-3 h-3 text-cyan-400" />
        <span>2D_PLANAR :: Drag: Pan • Scroll: Zoom • Hover: Trace neighbors • Click: Inspect</span>
      </div>
    </div>
  )
}
