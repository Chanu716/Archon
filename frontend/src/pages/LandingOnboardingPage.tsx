import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Terminal,
  Cpu,
  Layers,
  Network,
  Zap,
  ShieldAlert,
  ArrowRight,
  Sparkles,
  GitBranch,
  Play,
  Box,
  Code2,
  Database,
  Activity,
  CheckCircle2
} from 'lucide-react'

export default function LandingOnboardingPage() {
  const navigate = useNavigate()
  const [activeCommand, setActiveCommand] = useState<'galaxy' | 'blast' | 'analyst' | 'drift'>('galaxy')

  const commands = {
    galaxy: {
      cmd: 'archon explore-galaxy --target root://Forensic-Vision',
      output: [
        '>>> INITIALIZING THREE.JS FORCE-DIRECTED 3D COSMOS...',
        '>>> CLUSTERING 47 MODULES, 111 FUNCTIONS, 8 CLASSES IN ORBIT',
        '>>> 3D FORCE GRAPH STABILIZED: 328 BI-DIRECTIONAL EDGES MAPPED',
        '>>> TOPOLOGY READY: [2D_PLANAR] & [3D_GALAXY] CLUSTER CODES ACTIVE'
      ]
    },
    blast: {
      cmd: 'archon blast-radius --entity "backend.archon.models.evolution" --depth 5',
      output: [
        '>>> TRACING MULTI-HOP IMPORTERS, CALLERS & SUBCLASSES...',
        '>>> UPSTREAM PROPAGATION: 6 DIRECT CALLERS | 14 TRANSITIVE CALLERS',
        '>>> DOWNSTREAM DEPENDENCIES: 8 IMPORTS | 4 INHERITED CLASS TREES',
        '>>> TOTAL IMPACT BOUNDARY: 28 AFFECTED ENTITIES IN 4 SUB-PACKAGES'
      ]
    },
    analyst: {
      cmd: 'archon ask-analyst "Detect dead code & coupling risks in models"',
      output: [
        '>>> REACT AGENT: THOUGHT -> Grepping AST graph for isolated subtrees',
        '>>> TOOL EXECUTION: query_graph_symbols(type="Function", callers=0)',
        '>>> OBSERVATION: 3 uncalled helper functions identified in utility modules',
        '>>> SYNTHESIZING ARCHITECTURAL REPORT WITH GROUNDED CITATIONS...'
      ]
    },
    drift: {
      cmd: 'archon diff-snapshots --from snap_001 --to snap_002',
      output: [
        '>>> COMPARING DETERMINISTIC AST STRUCTURE TREES...',
        '>>> LIFECYCLE DELTA: 12 ADDED | 2 MODIFIED | 0 DELETED',
        '>>> CIRCULAR DEPENDENCY CHECK: 0 CYCLES DETECTED (HEALTH SCORE: 0.94)',
        '>>> EVOLUTION AUDIT COMPLETE: ARCHITECTURAL INTEGRITY PRESERVED'
      ]
    }
  }

  return (
    <div className="min-h-screen bg-black text-white font-mono crt-grid flex flex-col selection:bg-cyan-500 selection:text-black">
      {/* Top Header Bar */}
      <header className="border-b-2 border-white bg-black/90 sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt="Archon Emblem"
            className="w-8 h-8 object-contain filter drop-shadow-[0_0_10px_rgba(6,182,212,0.9)] animate-pulse"
          />
          <div>
            <div className="font-pixel text-sm md:text-base text-white tracking-widest flex items-center gap-2">
              ARCHON <span className="text-cyan-400 text-xs font-mono">// OS_2.0</span>
            </div>
            <div className="text-[10px] text-neutral-400 font-mono hidden sm:block">
              CODEBASE GRAPH INTELLIGENCE SYSTEM
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/repositories')}
            className="pixel-btn-filled-cyan text-xs flex items-center gap-2 px-3 py-1.5"
          >
            <span>[ LAUNCH_VAULT ]</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative px-6 py-16 md:py-24 max-w-6xl mx-auto flex flex-col items-center text-center space-y-8">
        {/* Glow Emblem */}
        <div className="relative group cursor-pointer" onClick={() => navigate('/repositories')}>
          <div className="absolute -inset-4 bg-cyan-500/20 rounded-full blur-xl opacity-75 group-hover:opacity-100 transition duration-500 animate-pulse" />
          <img
            src="/logo.png"
            alt="Archon Core"
            className="relative w-24 h-24 md:w-32 md:h-32 object-contain filter drop-shadow-[0_0_25px_rgba(6,182,212,0.9)] transform group-hover:scale-105 transition-transform duration-300"
          />
        </div>

        {/* Hero Title & Badges */}
        <div className="space-y-4 max-w-4xl">
          <div className="inline-flex items-center gap-2 border border-cyan-400/50 bg-cyan-950/30 px-3 py-1 text-cyan-300 font-pixel text-[10px] uppercase tracking-wider">
            <Sparkles className="w-3 h-3 text-cyan-400 animate-spin" />
            [ DETERMINISTIC AST CODEBASE KNOWLEDGE GRAPH ]
          </div>
          <h1 className="font-pixel text-2xl sm:text-4xl md:text-5xl text-white tracking-wide leading-tight">
            SEE YOUR CODEBASE AS A <span className="text-cyan-400 underline decoration-cyan-400/50 decoration-2">LIVING GALAXY</span>
          </h1>
          <p className="text-neutral-300 font-mono text-sm md:text-base max-w-2xl mx-auto leading-relaxed">
            Archon transforms complex Git repositories into interactive 3D/2D topological Knowledge Graphs with ReAct AI investigation, blast radius simulation, and structural drift telemetry.
          </p>
        </div>

        {/* Primary Call to Actions */}
        <div className="flex flex-col sm:flex-row items-center gap-4 pt-2">
          <button
            onClick={() => navigate('/repositories')}
            className="pixel-btn-filled-cyan text-sm px-6 py-3 flex items-center gap-2.5 w-full sm:w-auto justify-center shadow-[0_0_20px_rgba(6,182,212,0.4)]"
          >
            <Terminal className="w-4 h-4" />
            <span>[ INITIALIZE_REPOSITORY_VAULT → ]</span>
          </button>
          <a
            href="#interactive-sandbox"
            className="pixel-btn text-sm px-6 py-3 flex items-center gap-2 w-full sm:w-auto justify-center hover:border-cyan-400 text-neutral-300"
          >
            <Activity className="w-4 h-4 text-cyan-400" />
            <span>[ EXPLORE_CAPABILITIES ↓ ]</span>
          </a>
        </div>
      </section>

      {/* Interactive Command Sandbox */}
      <section id="interactive-sandbox" className="px-6 py-12 max-w-6xl mx-auto w-full space-y-6">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-2 border-b border-neutral-800 pb-3">
          <div>
            <div className="font-pixel text-xs text-cyan-400 uppercase">[ INTERACTIVE_COMMAND_MATRIX ]</div>
            <p className="text-xs text-neutral-400 font-mono mt-0.5">Click any subsystem command to preview live graph telemetry responses</p>
          </div>
          <span className="text-[10px] font-pixel text-neutral-500">[ SYSTEM_RUNTIME: V2.1_STABLE ]</span>
        </div>

        {/* Command Selector Buttons */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { id: 'galaxy', label: '3D_GALAXY', icon: Network },
            { id: 'blast', label: 'BLAST_RADIUS', icon: ShieldAlert },
            { id: 'analyst', label: 'REACT_ANALYST', icon: Zap },
            { id: 'drift', label: 'AST_DRIFT', icon: GitBranch },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveCommand(id as any)}
              className={`pixel-box p-2.5 text-left flex items-center gap-2 transition ${
                activeCommand === id
                  ? 'border-cyan-400 bg-cyan-950/30 text-cyan-300'
                  : 'hover:border-neutral-600 text-neutral-400'
              }`}
            >
              <Icon className="w-4 h-4 shrink-0 text-cyan-400" />
              <span className="font-pixel text-[10px]">{label}</span>
            </button>
          ))}
        </div>

        {/* Terminal Screen */}
        <div className="pixel-box bg-black border-2 border-neutral-800 overflow-hidden font-mono text-xs shadow-2xl">
          {/* Terminal Titlebar */}
          <div className="bg-neutral-950 px-4 py-2 border-b border-neutral-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 bg-red-500 rounded-none inline-block" />
              <span className="w-2.5 h-2.5 bg-amber-500 rounded-none inline-block" />
              <span className="w-2.5 h-2.5 bg-green-500 rounded-none inline-block" />
              <span className="font-pixel text-[9px] text-neutral-400 ml-2">ARCHON_SHELL :: REACT_EXEC</span>
            </div>
            <span className="text-[10px] text-cyan-400 font-mono">STATUS: 200_OK</span>
          </div>

          {/* Terminal Body */}
          <div className="p-5 space-y-3 bg-neutral-950/80 min-h-[200px]">
            <div className="flex items-center gap-2 text-cyan-400 font-bold">
              <span className="text-neutral-500">$</span>
              <span>{commands[activeCommand].cmd}</span>
            </div>

            <div className="space-y-1.5 text-neutral-300 pl-4 border-l-2 border-cyan-500/40">
              {commands[activeCommand].output.map((line, idx) => (
                <div key={idx} className="flex items-start gap-2 leading-relaxed">
                  <span className="text-cyan-400 select-none">▶</span>
                  <span className="font-mono text-[11px]">{line}</span>
                </div>
              ))}
            </div>

            <div className="pt-3 flex items-center gap-2 text-neutral-500 text-[11px]">
              <span className="w-2 h-3.5 bg-cyan-400 animate-pulse" />
              <span>Awaiting next telemetry instruction...</span>
            </div>
          </div>
        </div>
      </section>

      {/* Core Capabilities Deck */}
      <section className="px-6 py-12 max-w-6xl mx-auto w-full space-y-8">
        <div className="text-center space-y-2">
          <div className="font-pixel text-xs text-cyan-400 uppercase">[ SUBSYSTEM_CAPABILITIES ]</div>
          <h2 className="font-pixel text-xl sm:text-2xl text-white">FOUR PILLARS OF ARCHON INTELLIGENCE</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Card 1 */}
          <div className="pixel-box p-6 space-y-3 bg-neutral-950/40 border border-neutral-800 hover:border-cyan-400 transition group">
            <div className="flex items-center gap-3">
              <div className="p-2 border border-cyan-400/40 bg-cyan-950/30 text-cyan-400">
                <Network className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-pixel text-sm text-white group-hover:text-cyan-300 transition">3D COSMIC GALAXY & 2D PLANAR</h3>
                <span className="text-[10px] text-neutral-500 font-mono">Force-Directed Knowledge Graph</span>
              </div>
            </div>
            <p className="text-xs text-neutral-400 leading-relaxed font-mono">
              Explore your architecture in full 3D space with orbits, hierarchical layouts, caller/callee tracing, and real-time semantic zoom.
            </p>
          </div>

          {/* Card 2 */}
          <div className="pixel-box p-6 space-y-3 bg-neutral-950/40 border border-neutral-800 hover:border-cyan-400 transition group">
            <div className="flex items-center gap-3">
              <div className="p-2 border border-cyan-400/40 bg-cyan-950/30 text-cyan-400">
                <Zap className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-pixel text-sm text-white group-hover:text-cyan-300 transition">REACT MULTI-HOP AI ANALYST</h3>
                <span className="text-[10px] text-neutral-500 font-mono">Tool-Grounded LLM Reasoning Agent</span>
              </div>
            </div>
            <p className="text-xs text-neutral-400 leading-relaxed font-mono">
              AI Analyst executes AST queries, code extraction, and Neo4j traversals to deliver zero-hallucination code reviews and refactoring plans.
            </p>
          </div>

          {/* Card 3 */}
          <div className="pixel-box p-6 space-y-3 bg-neutral-950/40 border border-neutral-800 hover:border-cyan-400 transition group">
            <div className="flex items-center gap-3">
              <div className="p-2 border border-cyan-400/40 bg-cyan-950/30 text-cyan-400">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-pixel text-sm text-white group-hover:text-cyan-300 transition">MUTATION BLAST RADIUS SIMULATOR</h3>
                <span className="text-[10px] text-neutral-500 font-mono">Deterministic Dependency Propagation</span>
              </div>
            </div>
            <p className="text-xs text-neutral-400 leading-relaxed font-mono">
              Simulate breaking changes before merging. Trace upstream callers, downstream callees, and impacted files across depth 1 to 10.
            </p>
          </div>

          {/* Card 4 */}
          <div className="pixel-box p-6 space-y-3 bg-neutral-950/40 border border-neutral-800 hover:border-cyan-400 transition group">
            <div className="flex items-center gap-3">
              <div className="p-2 border border-cyan-400/40 bg-cyan-950/30 text-cyan-400">
                <GitBranch className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-pixel text-sm text-white group-hover:text-cyan-300 transition">AST SNAPSHOT DRIFT & HEALTH</h3>
                <span className="text-[10px] text-neutral-500 font-mono">Historical Architectural Degradation</span>
              </div>
            </div>
            <p className="text-xs text-neutral-400 leading-relaxed font-mono">
              Track cyclomatic complexity, circular dependencies, coupling spikes, and structural mutations between git commits.
            </p>
          </div>
        </div>
      </section>

      {/* 3-Step Quick Start Protocol */}
      <section className="px-6 py-12 max-w-6xl mx-auto w-full space-y-6">
        <div className="border border-neutral-800 bg-neutral-950 p-6 md:p-8 space-y-6">
          <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
            <div className="font-pixel text-xs text-white uppercase">[ 3_STEP_ONBOARDING_PROTOCOL ]</div>
            <span className="text-[10px] text-cyan-400 font-mono">EFFORTLESS_ONBOARDING</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs">
            <div className="space-y-2 p-4 border border-neutral-800 bg-black/60">
              <div className="font-pixel text-cyan-400 text-sm">[ STEP 01 ]</div>
              <div className="font-bold text-white text-sm">Clone or Link Git Repository</div>
              <p className="text-neutral-400 font-mono">
                Paste any public GitHub HTTPS URL or local repository path into the Vault terminal.
              </p>
            </div>

            <div className="space-y-2 p-4 border border-neutral-800 bg-black/60">
              <div className="font-pixel text-cyan-400 text-sm">[ STEP 02 ]</div>
              <div className="font-bold text-white text-sm">Automated AST Synthesis</div>
              <p className="text-neutral-400 font-mono">
                Archon parses syntax trees, computes cyclomatic metrics, and constructs the Neo4j Knowledge Graph.
              </p>
            </div>

            <div className="space-y-2 p-4 border border-neutral-800 bg-black/60">
              <div className="font-pixel text-cyan-400 text-sm">[ STEP 03 ]</div>
              <div className="font-bold text-white text-sm">Explore & Investigate</div>
              <p className="text-neutral-400 font-mono">
                Launch the 3D Galaxy Graph, run Blast Radius simulations, and converse with the ReAct AI Analyst.
              </p>
            </div>
          </div>

          <div className="text-center pt-2">
            <button
              onClick={() => navigate('/repositories')}
              className="pixel-btn-filled-cyan text-sm px-8 py-3.5 inline-flex items-center gap-2.5 shadow-[0_0_25px_rgba(6,182,212,0.5)]"
            >
              <Play className="w-4 h-4 fill-current" />
              <span>ENTER REPOSITORY VAULT NOW</span>
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto border-t-2 border-white bg-black px-6 py-6 text-xs text-neutral-500 font-mono flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <img src="/logo.png" alt="Archon" className="w-4 h-4 object-contain" />
          <span>ARCHON :: DETERMINISTIC CODE KNOWLEDGE GRAPH & AI INTELLIGENCE</span>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <button onClick={() => navigate('/repositories')} className="hover:text-cyan-400 transition">
            [ VAULT ]
          </button>
          <span>•</span>
          <span className="text-neutral-400">SYS_VER: 2.1.0-CYBER</span>
        </div>
      </footer>
    </div>
  )
}