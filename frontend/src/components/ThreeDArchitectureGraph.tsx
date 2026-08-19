import { useEffect, useRef, useCallback, useState } from 'react'
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph'
import * as THREE from 'three'
import {
  Play,
  Pause,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Compass,
  Sparkles,
} from 'lucide-react'

// Ensure Matrix4 determinantAffine compatibility across all Three.js versions
if (THREE && THREE.Matrix4 && !(THREE.Matrix4.prototype as any).determinantAffine) {
  ;(THREE.Matrix4.prototype as any).determinantAffine = function () {
    const te = this.elements
    return (
      te[0] * (te[5] * te[10] - te[9] * te[6]) -
      te[4] * (te[1] * te[10] - te[9] * te[2]) +
      te[8] * (te[1] * te[6] - te[5] * te[2])
    )
  }
}
if (typeof window !== 'undefined') {
  const w = window as any
  w.THREE = THREE
  if (w.THREE.Matrix4 && !w.THREE.Matrix4.prototype.determinantAffine) {
    w.THREE.Matrix4.prototype.determinantAffine = (THREE.Matrix4.prototype as any).determinantAffine
  }
}

// Node type color mapping (Retained in full vibrant color for optimal clarity)
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

// Link type color mapping
const LINK_TYPE_COLORS: Record<string, string> = {
  CONTAINS: '#4b5563',   // Muted Gray
  DEFINES: '#818cf8',    // Indigo
  IMPORTS: '#60a5fa',    // Bright Blue
  CALLS: '#ec4899',      // Pink
  INHERITS: '#10b981',   // Green
  CHANGED: '#f97316',    // Orange
  AUTHORED: '#fbbf24',   // Yellow
}

export interface ThreeDGraphProps {
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

export default function ThreeDArchitectureGraph({
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
}: ThreeDGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const graphRef = useRef<ForceGraph3DInstance | null>(null)
  const [isRotating, setIsRotating] = useState(false)
  const [hoveredNode, setHoveredNode] = useState<any | null>(null)
  const lastClickTimeRef = useRef<number>(0)
  const lastClickedNodeIdRef = useRef<string | null>(null)

  const propsRef = useRef({
    selectedNodeId,
    impactModeActive,
    impactTargetId,
    impactedNodeIds,
    onNodeClick,
    onNodeDoubleClick,
    onBackgroundClick,
    hoveredNode,
  })

  useEffect(() => {
    propsRef.current = {
      selectedNodeId,
      impactModeActive,
      impactTargetId,
      impactedNodeIds,
      onNodeClick,
      onNodeDoubleClick,
      onBackgroundClick,
      hoveredNode,
    }
  }, [
    selectedNodeId,
    impactModeActive,
    impactTargetId,
    impactedNodeIds,
    onNodeClick,
    onNodeDoubleClick,
    onBackgroundClick,
    hoveredNode,
  ])

  // Pixel Text Sprite Creator
  const createTextSprite = useCallback((text: string, color: string) => {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) return null

    canvas.width = 256
    canvas.height = 64
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    // Pixel Box Background
    ctx.fillStyle = '#000000'
    ctx.fillRect(4, 4, canvas.width - 8, canvas.height - 8)
    ctx.lineWidth = 3
    ctx.strokeStyle = color
    ctx.strokeRect(4, 4, canvas.width - 8, canvas.height - 8)

    // Typography
    ctx.font = 'bold 20px "JetBrains Mono", monospace'
    ctx.fillStyle = '#ffffff'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const truncated = text.length > 15 ? text.substring(0, 13) + '…' : text
    ctx.fillText(truncated, canvas.width / 2, canvas.height / 2)

    const texture = new THREE.CanvasTexture(canvas)
    texture.minFilter = THREE.LinearFilter
    const spriteMaterial = new THREE.SpriteMaterial({ map: texture, depthWrite: false, transparent: true })
    const sprite = new THREE.Sprite(spriteMaterial)
    sprite.scale.set(24, 6, 1)
    return sprite
  }, [])

  // Initialize ForceGraph3D instance
  useEffect(() => {
    if (!containerRef.current) return

    const graph = new ForceGraph3D(containerRef.current)
      .backgroundColor('#000000')
      .showNavInfo(false)
      .nodeRelSize(5.5)
      .nodeResolution(24)
      .nodeOpacity(0.95)
      .nodeLabel((node: any) => {
        const d = node.raw || node
        return `
          <div style="background: #000000; border: 2px solid #ffffff; padding: 8px 12px; font-family: 'JetBrains Mono', monospace; box-shadow: 3px 3px 0px 0px #00f3ff;">
            <div style="font-size: 10px; font-family: 'Silkscreen', monospace; text-transform: uppercase; font-weight: 700; color: ${NODE_TYPE_COLORS[d.type] || '#9ca3af'}; margin-bottom: 2px;">[ ${d.type} ]</div>
            <div style="font-size: 12px; font-weight: 700; color: #ffffff;">${d.label || d.name || d.id}</div>
            ${d.path ? `<div style="font-size: 10px; color: #a3a3a3; margin-top: 3px;">${d.path}</div>` : ''}
            ${d.total_lines ? `<div style="font-size: 10px; color: #00f3ff; margin-top: 2px;">LINES: ${d.total_lines}</div>` : ''}
            ${d.cyclomatic_complexity !== undefined ? `<div style="font-size: 10px; color: #f59e0b;">COMPLEXITY: ${d.cyclomatic_complexity}</div>` : ''}
          </div>
        `
      })
      .nodeThreeObject((node: any) => {
        const d = node.raw || node
        const group = new THREE.Group()

        const { selectedNodeId: selId, impactModeActive: isImp, impactTargetId: impTarget, impactedNodeIds: impSet, hoveredNode: hNode } = propsRef.current
        
        let color = NODE_TYPE_COLORS[d.type] || '#3b82f6'
        let isHighlighted = false
        let isDimmed = false

        if (isImp) {
          if (d.id === impTarget) {
            color = '#f97316'
            isHighlighted = true
          } else if (impSet.has(d.id)) {
            color = '#fdba74'
            isHighlighted = true
          } else {
            color = '#333333'
            isDimmed = true
          }
        } else if (selId && d.id === selId) {
          color = '#00f3ff'
          isHighlighted = true
        } else if (hNode && hNode.id === d.id) {
          isHighlighted = true
        }

        // Sizing
        let radius = 3.5
        if (d.type === 'Repository') radius = 8.5
        else if (d.type === 'Module' || d.type === 'Directory') radius = 5.5
        else if (d.type === 'Class') radius = 4.5
        else if (d.type === 'File') radius = Math.max(3.5, Math.min(6.5, (d.total_lines || 30) / 25))

        // Sphere Mesh
        const geometry = new THREE.SphereGeometry(radius, 24, 24)
        const material = new THREE.MeshStandardMaterial({
          color: new THREE.Color(color),
          emissive: new THREE.Color(color),
          emissiveIntensity: isHighlighted ? 0.9 : isDimmed ? 0.1 : 0.4,
          roughness: 0.2,
          metalness: 0.3,
          transparent: true,
          opacity: isDimmed ? 0.2 : 0.95,
        })
        const sphere = new THREE.Mesh(geometry, material)
        group.add(sphere)

        // Pulsing Orbital Halo for Selected or Target
        if (isHighlighted) {
          const ringGeo = new THREE.RingGeometry(radius * 1.35, radius * 1.6, 32)
          const ringMat = new THREE.MeshBasicMaterial({
            color: new THREE.Color(color),
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.85,
          })
          const ring = new THREE.Mesh(ringGeo, ringMat)
          ring.rotation.x = Math.PI / 2
          group.add(ring)
        }

        // Text Sprite
        if (d.type === 'Repository' || d.type === 'Module' || d.type === 'Class' || isHighlighted) {
          const sprite = createTextSprite(d.label || d.name || d.id, color)
          if (sprite) {
            sprite.position.set(0, radius + 5, 0)
            group.add(sprite)
          }
        }

        return group
      })
      .linkColor((link: any) => {
        const label = link.label || 'CONTAINS'
        const { impactModeActive: isImp, impactedNodeIds: impSet, hoveredNode: hNode } = propsRef.current
        
        if (isImp) {
          const sId = link.source?.id || link.source
          const tId = link.target?.id || link.target
          const isImpactLink = impSet.has(sId) || impSet.has(tId)
          return isImpactLink ? '#f97316' : 'rgba(50, 50, 50, 0.15)'
        }

        if (hNode) {
          const sId = link.source?.id || link.source
          const tId = link.target?.id || link.target
          if (sId === hNode.id || tId === hNode.id) {
            return '#00f3ff'
          }
          return 'rgba(40, 40, 40, 0.15)'
        }

        return LINK_TYPE_COLORS[label] || 'rgba(100, 100, 100, 0.5)'
      })
      .linkWidth((link: any) => {
        const label = link.label || 'CONTAINS'
        if (label === 'IMPORTS' || label === 'CALLS' || label === 'DEFINES') return 1.8
        return 0.8
      })
      .linkDirectionalParticles((link: any) => {
        const label = link.label || 'CONTAINS'
        if (label === 'IMPORTS' || label === 'CALLS' || label === 'DEFINES') return 3
        return 0
      })
      .linkDirectionalParticleWidth(2.2)
      .linkDirectionalParticleSpeed(0.007)
      .linkDirectionalParticleColor((link: any) => LINK_TYPE_COLORS[link.label] || '#00f3ff')
      .linkDirectionalArrowLength(3.5)
      .linkDirectionalArrowRelPos(1)
      .linkCurvature(0.12)
      .onNodeHover((node: any) => {
        setHoveredNode(node ? (node.raw || node) : null)
        if (containerRef.current) {
          containerRef.current.style.cursor = node ? 'pointer' : 'grab'
        }
      })
      .onNodeClick((node: any) => {
        const now = Date.now()
        const d = node.raw || node
        
        if (lastClickedNodeIdRef.current === d.id && now - lastClickTimeRef.current < 350) {
          propsRef.current.onNodeDoubleClick?.(d.id)
        } else {
          if (graphRef.current) {
            const distance = 90
            const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z)
            graphRef.current.cameraPosition(
              { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
              node,
              1000
            )
          }
          propsRef.current.onNodeClick?.(d)
        }

        lastClickTimeRef.current = now
        lastClickedNodeIdRef.current = d.id
      })
      .onBackgroundClick(() => {
        propsRef.current.onBackgroundClick?.()
      })

    // Lighting
    const scene = graph.scene()
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.1)
    scene.add(ambientLight)

    const dirLight1 = new THREE.DirectionalLight(0x00f3ff, 1.4)
    dirLight1.position.set(100, 150, 100)
    scene.add(dirLight1)

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 1.0)
    dirLight2.position.set(-100, -150, -100)
    scene.add(dirLight2)

    // Cosmic Starfield
    const starGeo = new THREE.BufferGeometry()
    const starCount = 600
    const starPos = new Float32Array(starCount * 3)
    for (let i = 0; i < starCount * 3; i++) {
      starPos[i] = (Math.random() - 0.5) * 1200
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3))
    const starMat = new THREE.PointsMaterial({
      color: 0x525252,
      size: 1.5,
      transparent: true,
      opacity: 0.6,
    })
    const starField = new THREE.Points(starGeo, starMat)
    scene.add(starField)

    // Force simulation
    graph.d3Force('charge')?.strength(-160)
    graph.d3Force('link')?.distance(65)
    graph.d3VelocityDecay(0.35)
    graph.warmupTicks(30)
    graph.cooldownTicks(150)

    graphRef.current = graph

    const handleResize = () => {
      if (containerRef.current && graphRef.current) {
        graphRef.current.width(containerRef.current.clientWidth)
        graphRef.current.height(containerRef.current.clientHeight)
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      graph._destructor?.()
    }
  }, [createTextSprite])

  // Sync data & filters
  useEffect(() => {
    if (!graphRef.current || !data) return

    const rawNodes = data.nodes || []
    const rawEdges = data.edges || []

    const filteredNodes = rawNodes
      .map(n => ({
        id: n.data.id,
        label: n.data.label || n.data.name || n.data.path || 'Unnamed',
        type: n.data.type || 'Unknown',
        raw: n.data,
      }))
      .filter(n => activeFilters.types.includes(n.type))

    const validNodeIdSet = new Set(filteredNodes.map(n => n.id))

    const filteredEdges = rawEdges
      .filter(e => {
        const sourceId = e.data.source
        const targetId = e.data.target
        const label = e.data.label || 'CONTAINS'
        return (
          validNodeIdSet.has(sourceId) &&
          validNodeIdSet.has(targetId) &&
          activeFilters.relationships.includes(label)
        )
      })
      .map(e => ({
        id: e.data.id,
        source: e.data.source,
        target: e.data.target,
        label: e.data.label || 'CONTAINS',
        raw: e.data,
      }))

    graphRef.current.graphData({
      nodes: filteredNodes,
      links: filteredEdges,
    })
  }, [data, activeFilters])

  useEffect(() => {
    if (!graphRef.current) return
    graphRef.current.nodeThreeObject(graphRef.current.nodeThreeObject())
    graphRef.current.linkColor(graphRef.current.linkColor())
  }, [selectedNodeId, impactModeActive, impactTargetId, impactedNodeIds, hoveredNode])

  useEffect(() => {
    if (!graphRef.current || !focusedNodeId) return

    const gData = graphRef.current.graphData()
    const targetNode: any = gData.nodes.find((n: any) => n.id === focusedNodeId)

    if (targetNode && targetNode.x !== undefined) {
      const distance = 85
      const distRatio = 1 + distance / Math.hypot(targetNode.x, targetNode.y, targetNode.z || 1)
      graphRef.current.cameraPosition(
        { x: targetNode.x * distRatio, y: targetNode.y * distRatio, z: (targetNode.z || 0) * distRatio },
        targetNode,
        1200
      )
    }
  }, [focusedNodeId])

  useEffect(() => {
    if (!graphRef.current) return
    const controls = graphRef.current.controls() as any
    if (controls) {
      controls.autoRotate = isRotating
      controls.autoRotateSpeed = 0.8
    }
  }, [isRotating])

  const handleResetCamera = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.cameraPosition({ x: 0, y: 0, z: 280 }, { x: 0, y: 0, z: 0 }, 1000)
    }
  }, [])

  const handleTopDownView = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.cameraPosition({ x: 0, y: 350, z: 1 }, { x: 0, y: 0, z: 0 }, 1000)
    }
  }, [])

  const handleFitToScreen = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoomToFit(800, 40)
    }
  }, [])

  const handleZoomIn = useCallback(() => {
    if (graphRef.current) {
      const { x, y, z } = graphRef.current.cameraPosition()
      graphRef.current.cameraPosition({ x: x * 0.7, y: y * 0.7, z: z * 0.7 }, undefined, 400)
    }
  }, [])

  const handleZoomOut = useCallback(() => {
    if (graphRef.current) {
      const { x, y, z } = graphRef.current.cameraPosition()
      graphRef.current.cameraPosition({ x: x * 1.4, y: y * 1.4, z: z * 1.4 }, undefined, 400)
    }
  }, [])

  return (
    <div className="relative w-full h-full bg-black overflow-hidden select-none">
      <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Cyber-Pixel 3D Toolbar - Centered HUD */}
      <div className="absolute bottom-5 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 pixel-box p-1.5 shadow-pixel">
        <button
          onClick={() => setIsRotating(!isRotating)}
          className={`p-1.5 border border-neutral-700 hover:border-cyan-400 transition-colors ${
            isRotating ? 'bg-cyan-400 text-black border-cyan-400' : 'text-neutral-300 hover:text-white'
          }`}
          title={isRotating ? 'Pause orbit rotation' : 'Auto orbit rotation'}
        >
          {isRotating ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>

        <button
          onClick={handleTopDownView}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Top-Down Planar (2.5D)"
        >
          <Compass className="w-4 h-4" />
        </button>

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
          onClick={handleFitToScreen}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Fit to Screen"
        >
          <Maximize2 className="w-4 h-4" />
        </button>

        <button
          onClick={handleResetCamera}
          className="p-1.5 border border-neutral-700 hover:border-cyan-400 text-neutral-300 hover:text-white transition-colors"
          title="Reset Camera"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Cyber-Pixel Hint Banner */}
      <div className="absolute top-3 left-3 z-10 pointer-events-none flex items-center gap-2 border border-neutral-800 bg-black/90 px-3 py-1 text-[11px] text-neutral-400 font-mono shadow-pixel-sm">
        <span className="w-2 h-2 bg-cyan-400 animate-pulse shadow-glow-cyan" />
        <span>3D_NAV :: Drag: Rotate • Right-Drag: Pan • Scroll: Zoom • Click: Inspect</span>
      </div>
    </div>
  )
}
