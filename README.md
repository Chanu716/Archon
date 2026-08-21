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

**Archon** transforms complex codebases into interactive, deterministic knowledge graphs and equips an evidence-grounded AI analyst to reason over structural dependencies without hallucinations.

[User Operating Handbook (MANUAL.md)](MANUAL.md) • [Technical Architecture Specification](archon_architecture.md)

</div>

> **Core Principle**: Structure first. Intelligence second.

---

## Key Features

- **Polyglot AST Parsing**: Subprocess-isolated Tree-Sitter parsers for **Python**, **TypeScript**, **JavaScript**, **Go**, **Java**, **C#**, and **Rust**. Computes cyclomatic complexity, nesting depth, class hierarchies, imports, and call sites.
- **Cross-Language Resolution**: Tracks cross-boundary invocations, shared schemas, API route bindings, and multi-language dependency graphs.
- **3D Galaxy & 2D Planar Visualizations**: Interactive WebGL force-directed 3D topology (Three.js) and 2D planar graph (Cytoscape.js) with layout switching and neighborhood inspection.
- **Blast Radius & Impact Analysis**: Directional graph traversal (upstream callers, downstream callees, affected files/modules) to trace regression risks.
- **Git Intelligence**: Tracks commit velocity, file churn, author contributions, and complexity-vs-churn risk hotspots.
- **Evidence-Grounded AI Analyst**: Multi-step reasoning agent with streaming traces citing verified graph entities and call paths.
- **Architecture Evolution & Drift**: Snapshot-isolated comparison detecting structural additions, removals, and coupling drift across commits.

---

## System Architecture

```
                       ┌──────────────────────────────────────┐
                       │           ARCHON FRONTEND            │
                       │ React 18 + Vite + TypeScript + WebGL │
                       └──────────────────┬───────────────────┘
                                          │ HTTP / SSE (Port 3000)
                                          ▼
                       ┌──────────────────────────────────────┐
                       │        ARCHON FASTAPI BACKEND        │
                       │   Subprocess-Isolated Tree-Sitter    │
                       └───────────┬──────────────┬───────────┘
                                   │              │
                    ┌──────────────▼───┐      ┌───▼──────────────┐
                    │    PostgreSQL    │      │      Neo4j       │
                    │ Metadata, Jobs,  │      │ Knowledge Graph  │
                    │ pgvector Vectors │      │   (Port 7687)    │
                    │   (Port 5432)    │      └──────────────────┘
                    └──────────────────┘
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

## Testing

Run the complete backend test suite:
```bash
cd backend
poetry run pytest tests/unit/
```

---

## Documentation

* [User Operating Handbook (MANUAL.md)](MANUAL.md) — Step-by-step operational guide for all features, graphs, search, and blast radius workflows.
* [Technical Architecture Specification (archon_architecture.md)](archon_architecture.md) — Detailed engineering document covering database schemas, parser visitor patterns, and algorithms.
