<div align="center">

<pre>
█████╗ ██████╗  ██████╗██╗  ██╗ ██████╗ ███╗   ██╗
██╔══██╗██╔══██╗██╔════╝██║  ██║██╔═══██╗████╗  ██║
███████║██████╔╝██║     ███████║██║   ██║██╔██╗ ██║
██╔══██║██╔══██╗██║     ██╔══██║██║   ██║██║╚██╗██║
██║  ██║██║  ██║╚██████╗██║  ██║╚██████╔╝██║ ╚████║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
</pre>

[![Status](https://img.shields.io/badge/System-Operational-00f3ff?style=for-the-badge&logo=statuspage&logoColor=black)](http://localhost:3000)
[![Graph](https://img.shields.io/badge/Graph-Neo4j_5.x-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)](https://neo4j.com)
[![Vectors](https://img.shields.io/badge/Vectors-pgvector-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Visualization](https://img.shields.io/badge/WebGL-Three.js_&_Cytoscape-black?style=for-the-badge&logo=three.js&logoColor=white)](https://threejs.org)
[![Languages](https://img.shields.io/badge/Parsers-Python_•_TS_•_JS_•_Go_•_Java_•_C%23_•_Rust-brightgreen?style=for-the-badge)](https://github.com/Chanu716/Archon)

**Archon** transforms complex codebases into interactive, deterministic knowledge graphs and equips an evidence-grounded AI analyst to reason over structural dependencies without hallucinations.

[User Operating Handbook (MANUAL.md)](MANUAL.md) • [Technical Architecture Specification](archon_architecture.md)

</div>

> **Core Principle**: Structure first. Intelligence second.

---

## Source of Truth Hierarchy

```
SOURCE REPOSITORY (Git tree + Multi-Language AST source files)
       │
       ▼ [Subprocess-Isolated Tree-Sitter & Python AST Parsers]
KNOWLEDGE GRAPH (Neo4j Graph Database)
       │
       ▼ [Topological Traversal + Cross-Language Resolution + Static Metrics]
RETRIEVAL & BLAST RADIUS ENGINE (pgvector + BFS)
       │
       ▼ [Evidence Injection]
AI REASONING & VERIFIABLE CITATIONS
```

Archon enforces a strict hierarchy between verified facts and machine learning inference:

| Category | Definition | Presentation |
|---|---|---|
| **Deterministic Facts** | Directly computed from the AST (cyclomatic complexity, line count, fan-in/fan-out, call hierarchy, cross-language routes, git churn). | Labeled `[DET]` / `computed` |
| **Archon Heuristics** | Algorithmic indices combining complexity, coupling, and churn into risk scores. | Labeled `[HEU]` / `Risk Heuristic v1` |
| **AI Analysis** | Natural language synthesis produced by the LLM citing verified graph entities and call paths. | Labeled `AI Analysis` |

---

## Semantic Search vs. AI Analyst

Archon provides two complementary AI intelligence layers with distinct purposes:

| Feature | 🔍 **Semantic Vector Search** (`[ SEARCH ]`) | 🤖 **AI Code Analyst** (`[ AI_ANALYST ]`) |
|---|---|---|
| **Primary Role** | Neural Symbol & Concept Finder | Autonomous Senior Architect Reasoning Agent |
| **How it Works** | Generates text embeddings and executes mathematical cosine-distance nearest-neighbor queries via `pgvector`. | Executes a multi-step ReAct agent using dynamic tools across the Neo4j Knowledge Graph, AST, Git commit history, and complexity metrics. |
| **Ideal Query** | *"where is token validation handled?"*, *"face detection pipeline"* | *"How is data routed from HTTP request to model inference?", "Is there architectural drift in the auth module?"* |
| **Output Type** | Ranked list of exact code entities (classes, functions, modules) with similarity scores and one-click graph centering. | Conversational architectural synthesis with streaming step-by-step reasoning traces (`[ REASONING_TRACE ]`), confidence ratings, and citations. |
| **Response Latency** | Instant (~50ms) | Multi-step Streaming (~3–8s) |

---

## Key Capabilities

### 1. Dual 3D & 2D Architecture Visualization
* **3D Galaxy Graph (Three.js WebGL)**: Force-directed cosmic topology showing hierarchical clusters, particle streams on imports/calls, orbital rotation, and 2.5D planar camera modes.
* **2D Planar Graph (Cytoscape.js)**: Deterministic 2D view supporting 4 layout engines (CoSE physics, DAG hierarchical tree, Concentric rings, Circle chord layout) with neighborhood hover tracing.

### 2. Polyglot AST Parsing & Subprocess Isolation
* Deterministic parsing across **Python**, **TypeScript**, **JavaScript**, **Go**, **Java**, **C#**, and **Rust**.
* **Subprocess Isolation (`safe_parse.py`)**: Runs Tree-Sitter grammars inside isolated worker processes with automatic memory protection and recovery.
* **Cross-Language Resolution**: Links frontend API calls (`fetch`, `axios`) to backend route handlers across languages and maps shared schemas.

### 3. Dual-Engine Search
* **AST Symbol Quick Search**: Real-time indexed query across function, class, module, and file names with immediate graph centering and subtree expansion.
* **Semantic Natural Language Search**: Vector similarity search using pgvector embeddings for conceptual queries (e.g. *where is authentication middleware configured?*).

### 4. Deterministic Blast Radius & Impact Analysis
* Breadth-First Search (BFS) graph traversal across configurable depths (1–10).
* Traces upstream callers (who breaks if this changes) and downstream callees (what this depends on).
* Highlights direct and indirect impact chains visually on the architecture graph.

### 5. Grounded AI Code Analyst
* Interactive reasoning console with real-time Server-Sent Events (SSE) streaming.
* Inspectable reasoning traces showing Cypher queries and vector lookups performed during synthesis.
* Verifiable entity citations linking claims directly to AST nodes.

### 6. Evolution & Drift Tracking
* Multi-snapshot comparison tracking structural additions, removals, and signature modifications across commits.
* Architecture drift detector surfacing unexpected coupling or architectural decay.

### 7. Code Health & Git Intelligence
* Structural topology metrics (circular dependency detection, cyclomatic complexity distributions, coupling factors).
* Git commit velocity, author touch distribution, and churn-vs-complexity risk hotspots with thread-offloaded async processing.

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          ARCHON FRONTEND                               │
│        React 18 + Vite + TypeScript + Three.js WebGL + Cytoscape       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / SSE
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        ARCHON FASTAPI BACKEND                          │
│                                                                        │
│  ┌─────────────────────────┐  ┌───────────────────┐  ┌───────────────┐ │
│  │ Polyglot Parser Engine  │  │   Graph Service   │  │Impact Analysis│ │
│  │ (Tree-Sitter + Safe AST)│  │  (Neo4j Cypher)   │  │  (Async BFS)  │ │
│  └───────────┬─────────────┘  └─────────┬─────────┘  └───────┬───────┘ │
│              │                          │                    │         │
│  ┌───────────▼─────────────┐  ┌─────────▼─────────┐  ┌───────▼───────┐ │
│  │ Cross-Language Resolver │  │ AI Analyst Engine │  │Vector Service │ │
│  │  (Route & Model Binding)│  │ (Gemini / Ollama) │  │  (pgvector)   │ │
│  └───────────┬─────────────┘  └───────────────────┘  └───────────────┘ │
│              │                                                         │
│  ┌───────────▼─────────────┐                                           │
│  │  Git Analytics Engine   │                                           │
│  │ (GitPython Async Thread)│                                           │
│  └─────────────────────────┘                                           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
   ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐
   │   PostgreSQL    │    │      Neo4j       │    │     pgvector      │
   │ Metadata & Jobs │    │ Knowledge Graph  │    │  Code Embeddings  │
   └─────────────────┘    └──────────────────┘    └───────────────────┘
```

---

## Quickstart

### Option 1: Docker Compose (Recommended)

1. Clone the repository and configure environment variables:
   ```bash
   git clone https://github.com/Chanu716/Archon.git
   cd Archon
   cp .env.example .env
   ```

2. Start all services:
   ```bash
   docker-compose up -d --build
   ```

3. Access the web application:
   - **Frontend**: [http://localhost:3000](http://localhost:3000)
   - **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)

---

### Option 2: Local Development Setup

#### Prerequisites
- Python 3.11+
- Node.js 20+ & npm
- Docker (for PostgreSQL + Neo4j)

#### 1. Start Database Dependencies
```bash
docker-compose up -d postgres neo4j
```

#### 2. Start Backend
```bash
cd backend
poetry install
poetry run uvicorn archon.main:app --reload --port 8000
```

#### 3. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql+asyncpg://archon:archon_secret@localhost:5432/archon` |
| `NEO4J_URI` | Neo4j Bolt connection URI | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `neo4j_secret` |
| `LLM_PROVIDER` | LLM provider (`gemini`, `openai`, `anthropic`, `ollama`, `openrouter`, `groq`) | `ollama` |
| `GEMINI_API_KEY` | Google Gemini API Key | Optional |
| `OPENAI_API_KEY` | OpenAI API Key | Optional |
| `ANTHROPIC_API_KEY`| Anthropic API Key | Optional |
| `EMBEDDING_PROVIDER`| Code embedding provider (`gemini`, `openai`, `ollama`, `huggingface`) | `ollama` |

---

## Route Overview

| Route | Page | Description |
|---|---|---|
| `/repositories` | Repositories Vault | Register targets and view analysis status |
| `/repositories/:id/overview` | Repository Hub | Analysis progress, repository metadata, and quick navigation |
| `/repositories/:id/architecture` | Architecture Graph | Interactive 3D Galaxy & 2D Planar graph topologies |
| `/repositories/:id/health` | Health Dashboard | Complexity, coupling, and circular dependency metrics |
| `/repositories/:id/git` | Git Intelligence | Churn hotspots, commit velocity, and author statistics |
| `/repositories/:id/evolution` | Evolution Dashboard | Snapshot comparison, timeline charts, and drift findings |
| `/repositories/:id/investigation` | Intelligence Workbench | Multi-dimensional entity investigation dossier |

---

## Documentation

* [User Operating Handbook (MANUAL.md)](MANUAL.md) — Step-by-step operational guide for all features, graphs, search, and blast radius workflows.
* [Technical Architecture Specification (archon_architecture.md)](archon_architecture.md) — Detailed engineering document covering database schemas, parser visitor patterns, and algorithms.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
