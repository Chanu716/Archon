import React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Terminal,
  Network,
  Zap,
  ShieldAlert,
  ArrowRight,
  Sparkles,
  GitBranch,
  Play,
  Layers,
  Activity
} from 'lucide-react'

export default function LandingOnboardingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-black text-white font-mono crt-grid flex flex-col justify-between p-6 md:p-10 selection:bg-cyan-500 selection:text-black">
      {/* Top Bar */}
      <header className="max-w-5xl w-full mx-auto flex items-center justify-between border-b-2 border-white pb-4">
        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt="Archon Logo"
            className="w-8 h-8 object-contain filter drop-shadow-[0_0_8px_rgba(6,182,212,0.8)]"
          />
          <div>
            <span className="font-pixel text-base text-white tracking-wider">ARCHON</span>
            <span className="text-neutral-500 text-xs font-mono ml-2">// CODE_INTELLIGENCE</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 border border-neutral-800 bg-neutral-950 px-3 py-1 text-[10px] text-neutral-400">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse shadow-glow-cyan" />
            <span>CORE: ONLINE</span>
          </div>
          <button
            onClick={() => navigate('/repositories')}
            className="pixel-btn-filled-cyan text-xs flex items-center gap-1.5 px-3 py-1.5"
          >
            <span>[ ENTER_VAULT ]</span>
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </header>

      {/* Main Centerpiece (Single-Screen Focus) */}
      <main className="max-w-4xl w-full mx-auto my-auto py-8 flex flex-col items-center text-center space-y-7">
        {/* Glowing Logo */}
        <div 
          onClick={() => navigate('/repositories')}
          className="relative group cursor-pointer"
        >
          <div className="absolute -inset-4 bg-cyan-500/20 rounded-full blur-xl opacity-75 group-hover:opacity-100 transition duration-500 animate-pulse" />
          <img
            src="/logo.png"
            alt="Archon Core"
            className="relative w-24 h-24 sm:w-28 sm:h-28 object-contain filter drop-shadow-[0_0_20px_rgba(6,182,212,0.8)] transform group-hover:scale-105 transition-transform duration-300"
          />
        </div>

        {/* Title & Tagline */}
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 border border-cyan-400/40 bg-cyan-950/20 px-3 py-0.5 text-cyan-300 font-pixel text-[10px] uppercase">
            <Sparkles className="w-3 h-3 text-cyan-400 animate-spin" />
            [ DETERMINISTIC AST CODEBASE KNOWLEDGE GRAPH ]
          </div>
          <h1 className="font-pixel text-2xl sm:text-4xl text-white tracking-wide leading-tight">
            EXPLORE YOUR CODEBASE IN <span className="text-cyan-400">3D</span>
          </h1>
          <p className="text-neutral-400 text-xs sm:text-sm font-mono max-w-xl mx-auto leading-relaxed">
            Deterministic Knowledge Graphs • ReAct AI Code Analyst • Blast Radius Propagation • AST Snapshot Drift Telemetry
          </p>
        </div>

        {/* Main Action Button */}
        <div>
          <button
            onClick={() => navigate('/repositories')}
            className="pixel-btn-filled-cyan text-sm px-8 py-3.5 inline-flex items-center gap-2.5 shadow-[0_0_20px_rgba(6,182,212,0.5)] transform hover:scale-102 transition"
          >
            <Terminal className="w-4 h-4" />
            <span>[ INITIALIZE_REPOSITORY_VAULT → ]</span>
          </button>
        </div>

        {/* 3 Compact Feature Pills */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-3xl pt-2 text-left">
          <div className="pixel-box p-3 bg-neutral-950/50 border border-neutral-800 hover:border-cyan-400 transition">
            <div className="flex items-center gap-2 font-pixel text-xs text-white mb-1">
              <Network className="w-3.5 h-3.5 text-cyan-400" />
              <span>3D / 2D GALAXY</span>
            </div>
            <p className="text-[11px] text-neutral-400 font-mono">
              Force-directed orbits of modules, classes, and call hierarchies.
            </p>
          </div>

          <div className="pixel-box p-3 bg-neutral-950/50 border border-neutral-800 hover:border-cyan-400 transition">
            <div className="flex items-center gap-2 font-pixel text-xs text-white mb-1">
              <Zap className="w-3.5 h-3.5 text-cyan-400" />
              <span>REACT AI ANALYST</span>
            </div>
            <p className="text-[11px] text-neutral-400 font-mono">
              Tool-grounded multi-hop reasoning across AST and graph topology.
            </p>
          </div>

          <div className="pixel-box p-3 bg-neutral-950/50 border border-neutral-800 hover:border-cyan-400 transition">
            <div className="flex items-center gap-2 font-pixel text-xs text-white mb-1">
              <ShieldAlert className="w-3.5 h-3.5 text-cyan-400" />
              <span>BLAST RADIUS</span>
            </div>
            <p className="text-[11px] text-neutral-400 font-mono">
              Multi-hop mutation propagation & caller/callee boundary simulation.
            </p>
          </div>
        </div>

        {/* 3-Step Quick Flow Bar */}
        <div className="border border-neutral-800 bg-neutral-950/80 px-4 py-2.5 max-w-2xl w-full flex items-center justify-between text-[10px] text-neutral-400 font-pixel uppercase">
          <span className="text-cyan-400">[01] LINK_GIT_REPO</span>
          <span className="text-neutral-600">→</span>
          <span className="text-cyan-400">[02] SYNTHESIZE_AST</span>
          <span className="text-neutral-600">→</span>
          <span className="text-cyan-400">[03] EXPLORE_GRAPH</span>
        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-5xl w-full mx-auto border-t border-neutral-800 pt-3 flex flex-col sm:flex-row items-center justify-between text-[11px] text-neutral-500 font-mono gap-2">
        <div className="flex items-center gap-2">
          <img src="/logo.png" alt="Archon" className="w-3.5 h-3.5 object-contain" />
          <span>ARCHON CODE INTELLIGENCE</span>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/repositories')} className="hover:text-cyan-400 transition">
            [ VAULT ]
          </button>
          <span>•</span>
          <span className="text-neutral-400">SYS_VER: 2.1.0</span>
        </div>
      </footer>
    </div>
  )
}
