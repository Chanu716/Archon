# 📖 ARCHON :: Complete System User Manual & Operating Handbook

> **System**: Archon Code Intelligence & Architecture Reasoning Platform  
> **Aesthetic**: Cyber-Pixel (16-Bit Retro-Terminal)  
> **Core Principle**: *Structure first. Intelligence second.*

---

## 📑 Table of Contents

1. [System Overview & User Interface Conventions](#1-system-overview--user-interface-conventions)
2. [Chapter 1: Installation & Quick Setup](#chapter-1-installation--quick-setup)
3. [Chapter 2: Ingesting & Analyzing a Repository](#chapter-2-ingesting--analyzing-a-repository)
4. [Chapter 3: Navigating the 3D Galaxy & 2D Planar Graph](#chapter-3-navigating-the-3d-galaxy--2d-planar-graph)
5. [Chapter 4: Using Dual-Engine Search (Symbol & Semantic)](#chapter-4-using-dual-engine-search-symbol--semantic)
6. [Chapter 5: Entity Inspection & Subtree Expansion](#chapter-5-entity-inspection--subtree-expansion)
7. [Chapter 6: Running Blast Radius & Impact Analysis](#chapter-6-running-blast-radius--impact-analysis)
8. [Chapter 7: Interacting with the AI Code Analyst](#chapter-7-interacting-with-the-ai-code-analyst)
9. [Chapter 8: Tracking Architecture Evolution & Drift](#chapter-8-tracking-architecture-evolution--drift)
10. [Chapter 9: Codebase Health Radar & Git Intelligence](#chapter-9-codebase-health-radar--git-intelligence)
11. [Chapter 10: Troubleshooting, FAQ & Pro Tips](#chapter-10-troubleshooting-faq--pro-tips)

---

## 1. System Overview & User Interface Conventions

Archon presents a **Cyber-Pixel retro-terminal interface** designed for maximum density, contrast, and clarity:

* **Black & White Canvas (`#000000` / `#ffffff`)**: Crisp 2px borders and window frames that minimize cognitive fatigue.
* **Electric Neon Cyber-Cyan (`#00f3ff`)**: Highlights active tabs, focused elements, and real-time status indicators.
* **Color-Coded AST Graph Nodes**:
  * 🟡 **Repository** (`#f59e0b`): Root project entity.
  * 🟠 **Directory** (`#fb923c`): Folder structure.
  * 🟣 **File** (`#818cf8`): Source files.
  * 🔵 **Module** (`#3b82f6`): Python modules.
  * 🟢 **Class** (`#10b981`): Object classes.
  * 🌸 **Function** (`#ec4899`): Standalone functions.
  * 🪻 **Method** (`#a78bfa`): Class-bound methods.
* **Bracket Tags**: Indicators like `[STATUS: OK]`, `[DET]`, `[HEU]`, and `[ 3D_GALAXY ]` indicate interactive controls and verified telemetry sources.

---

## Chapter 1: Installation & Quick Setup

### Step 1.1: Clone & Configure
Open a terminal in your workspace directory:
```bash
git clone https://github.com/Chanu716/Archon.git
cd Archon
cp .env.example .env
```

### Step 1.2: Configure Environment (.env)
Edit `.env` to configure your API keys (optional but recommended for AI features):
```ini
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

### Step 1.3: Start Services via Docker
Run the automated multi-container stack:
```bash
docker-compose up -d --build
```
This launches:
* **Frontend**: `http://localhost:3000`
* **FastAPI Backend**: `http://localhost:8000`
* **Neo4j Graph Database**: `http://localhost:7474` (Bolt: `localhost:7687`)
* **PostgreSQL + pgvector**: `localhost:5432`

---

## Chapter 2: Ingesting & Analyzing a Repository

### Step 2.1: Open the Repository Vault
Navigate to `http://localhost:3000/repositories` in your browser.

### Step 2.2: Add a Repository
1. In the **`[ INGEST_NEW_REPOSITORY ]`** terminal bar, paste any public GitHub repository URL:
   ```
   https://github.com/encode/starlette
   ```
2. Click the cyan **`[ INGEST_REPO ]`** button.
3. Archon clones the repository into internal storage and registers a metadata entry in PostgreSQL.

### Step 2.3: Trigger AST Analysis
1. Click **`[ OVERVIEW ]`** on the newly ingested repository card.
2. In the top right corner, click **`[ TRIGGER_ANALYSIS ]`**.
3. Watch the stepped pixel progress bar as Archon executes:
   * **Stage 1 (CLONING)**: Verifies git ref and tree integrity.
   * **Stage 2 (AST_PARSING)**: Parses syntax trees into modules, classes, functions, and call graphs.
   * **Stage 3 (STATIC_ANALYSIS)**: Computes cyclomatic complexity, nesting depth, and coupling.
   * **Stage 4 (GIT_ANALYSIS)**: Analyzes commit logs, churn rates, and author distributions.
   * **Stage 5 (GRAPH_POPULATION)**: Commits the snapshot sub-graph to Neo4j.
   * **Stage 6 (VECTOR_EMBEDDING)**: Generates embeddings for semantic retrieval.
4. When status reaches **`COMPLETED` (100%)**, click **`[ 🌌 ARCHITECTURE GRAPH ]`** to enter the visualization canvas.

---

## Chapter 3: Navigating the 3D Galaxy & 2D Planar Graph

Archon provides dual visualization perspectives for different analysis workflows:

```
[ ARCHITECTURE VIEWPORT ]
 ├── [ 3D_GALAXY ]: Immersive cosmic force graph for structural overview and clustering.
 └── [ 2D_PLANAR ]: Strict 2D layout engine with explicit topological trees and cycles.
```

### 3.1: 3D Galaxy Navigation Controls
* **Left-Click + Drag**: Orbit and rotate the 3D camera around the galaxy.
* **Right-Click + Drag**: Pan the viewport horizontally and vertically.
* **Scroll Wheel**: Zoom into individual node clusters or zoom out for a macro overview.
* **Click Node**: Center the camera on the node, auto-expand its 1-hop dependencies, and open the Entity Details Inspector.
* **Double-Click Node**: Trigger deep sub-tree expansion.

#### Floating HUD Toolbar (Bottom-Right in 3D View):
* **▶ / ⏸ (Auto-Orbit)**: Toggles smooth cosmic orbital camera rotation.
* **🧭 (Compass / Top-Down 2.5D)**: Snaps the camera into a clean top-down orthogonal angle.
* **➕ / ➖ (Zoom)**: Incremental magnification buttons.
* **⛶ (Fit to Screen)**: Auto-centers all active nodes in the camera frustum.
* **↺ (Reset Camera)**: Restores default perspective.

### 3.2: 2D Planar Navigation & Layout Engines
Click the **`[ 2D_PLANAR ]`** switch in the top bar to activate the Cytoscape view:

#### Layout Engine Switcher (Bottom-Right Dropdown):
1. **FORCE (CoSE)**: Physics-based spring layout separating interconnected clusters.
2. **TREE (DAG / Breadthfirst)**: Hierarchical top-to-bottom dependency hierarchy.
3. **CONCENTRIC**: Puts critical repositories and core modules at the center with outer orbiting components.
4. **CIRCLE RING**: Arranges nodes along a circular perimeter to quickly spot circular dependency chords.

#### 2D Controls:
* **👁 (Eye Icon)**: Toggles edge label visibility (`DEFINES`, `CALLS`, `IMPORTS`).
* **Hover Node**: Automatically highlights connected neighbors and dims unrelated nodes.

### 3.3: Left Sidebar Filters
Use the left sidebar to isolate architectural layers:
* **`[ NODE_TYPES ]`**: Check/uncheck `File`, `Class`, `Function`, etc. to show or hide node tiers.
* **`[ RELATIONSHIPS ]`**: Filter specific dependency types (`CALLS`, `IMPORTS`, `DEFINES`).

---

## Chapter 4: Using Dual-Engine Search (Symbol & Semantic)

Archon features two complementary search systems:

### 4.1: Real-time Symbol Quick-Search (`> query_symbol…`)
Located on the top-right of the Architecture page:
1. Type any function, class, file, or module name (e.g. `base64` or `Request`).
2. A retro pixel dropdown appears instantly showing all matching symbols across the entire repository.
3. Click any result (or press **Enter**):
   * The node is injected into the graph canvas.
   * The camera animates and focuses directly on the target.
   * Its 1-hop relationships are automatically loaded.
   * The **Entity Details Inspector** opens with full metrics.

### 4.2: Semantic Natural Language Search (`[ SEARCH ]` Button)
Click **`[ SEARCH ]`** in the top navigation bar to open the AI vector search drawer:
1. Enter questions or descriptions in plain English:
   * *"Where is request cookie parsing handled?"*
   * *"Face detection and landmark preprocessing pipeline"*
2. Archon calculates cosine similarity across vector embeddings and returns ranked matches.
3. View source code previews and similarity percentages (`e.g. 94%`).
4. Click **`[ INVESTIGATE ]`** to inspect the node in the Intelligence Workbench or click the symbol name to zoom directly to it on the graph.

### 4.3: When to Use Semantic Search vs. AI Analyst

| Task | Recommended Tool | Why |
|---|---|---|
| **Find where a feature or logic is implemented** | 🔍 **Semantic Search** (`[ SEARCH ]`) | Instant vector search returns the exact code entities and files. |
| **Locate a specific function or class by name** | ⚡ **Symbol Quick-Search** (`> query_symbol…`) | Instant indexed exact/fuzzy matching across all AST symbols. |
| **Understand system data flow or architecture patterns** | 🤖 **AI Analyst** (`[ AI_ANALYST ]`) | Multi-step agent traverses the Neo4j graph and explains the relationships. |
| **Find dead code, high coupling, or circular dependencies** | 🤖 **AI Analyst** (`[ AI_ANALYST ]`) | Analyzes metrics across the graph with step-by-step reasoning traces. |
| **Calculate blast radius / refactoring impact** | 💥 **Blast Radius Engine** (`[ ! BLAST_RADIUS ]`) | Deterministic BFS graph traversal showing direct and indirect callers. |

---

## Chapter 5: Entity Inspection & Subtree Expansion

When any node is selected, the **Entity Details Inspector** opens on the right side of the screen:

### 5.1: Key Telemetry Fields
* **Entity Type & Qualified Name**: Full module path (e.g. `starlette.middleware.base.BaseHTTPMiddleware`).
* **Source Path & Line Numbers**: Exact file path and starting/ending lines.
* **Docstring**: Extracted documentation strings from the AST parser.
* **Deterministic Metrics (`[DET]`)**:
  * **Cyclomatic Complexity (CC)**: Number of linearly independent code paths.
  * **Nesting Depth**: Maximum depth of loops and conditional blocks.
  * **Line Count**: Total physical lines of code.
  * **Fan-in / Fan-out**: Number of inbound callers vs outbound callees.
  * **Coupling Factor**: Incoming/outgoing module coupling.
* **Archon Risk Score (`[HEU]`)**: Composite algorithmic risk index (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`).

### 5.2: Action Buttons
* **`[ + EXPAND_CHILDREN ]`**: Queries Neo4j for all 1-hop adjacent nodes and merges them dynamically into the graph.
* **`[ > OPEN_WORKBENCH ]`**: Launches the full Intelligence Workbench dossier for the entity.
* **`[ ! BLAST_RADIUS ]`**: Switches directly into the Blast Radius & Impact Analysis panel.

---

## Chapter 6: Running Blast Radius & Impact Analysis

The Blast Radius engine identifies every component that will break if you modify or refactor an entity:

### 6.1: Launching Blast Radius
1. Click on any Function, Class, or Module in the graph.
2. In the Inspector panel, click **`[ ! BLAST_RADIUS ]`**.

### 6.2: Configuring Traversal
* **Direction Dropdown**:
  * **Both Directions**: Upstream callers + downstream callees.
  * **Upstream (Callers)**: Components that depend on this entity (*"Who will break if I change this?"*).
  * **Downstream (Callees)**: Components that this entity relies upon (*"What does this depend on?"*).
* **Depth Selector (`Depth 1–10`)**: Sets BFS graph traversal radius.

### 6.3: Visualizing Impact on Canvas
Click the cyan button **`[ HIGHLIGHT_IN_GRAPH ]`**:
* The selected entity glows bright orange (`#f97316`).
* Direct callers/callees glow amber with solid links.
* Indirect callers/callees are marked with dashed rings.
* Unaffected nodes are dimmed to 15% opacity.

---

## Chapter 7: Interacting with the AI Code Analyst

The AI Analyst is a structure-grounded reasoning engine connected to the Neo4j graph and vector database:

### 7.1: Opening the Analyst
Click the cyan **`[ AI_ANALYST ]`** button in the top navigation bar.

### 7.2: Asking Architectural Questions
Type your query in the prompt box:
* *"Identify any circular dependencies in the routing and middleware modules."*
* *"Explain the lifecycle of a Request object from ingestion to response."*
* *"Which modules have the highest coupling and need refactoring?"*

### 7.3: Reading Reasoning Traces & Evidence Citations
* **Reasoning Trace (`[ REASONING_TRACE ]`)**: Real-time SSE stream displaying which graph queries and vector searches the agent performed.
* **Synthesized Analysis**: Markdown explanation formatted with syntax-highlighted code symbols.
* **Confidence Rating**: Categorized as `HIGH`, `MEDIUM`, or `LOW`.
* **Evidence Citations (`[ EVIDENCE_CITATIONS ]`)**: Verifiable AST entity tags (e.g. `[starlette.applications.Starlette]`) confirming factual grounding.

---

## Chapter 8: Tracking Architecture Evolution & Drift

To measure architectural health across time, click **`[ EVOLUTION ]`** in the repository overview:

### 8.1: Evolution Trend Charts
* **Complexity & Coupling Trend**: Multi-snapshot line graph tracking whether codebase complexity is escalating or stabilizing.
* **Repository Risk Evolution**: Tracks the macro Archon Risk Score over consecutive releases.

### 8.2: Snapshot Comparison (`Compare: S1 → S2`)
1. Select two snapshots from the comparison dropdowns.
2. Inspect the **`[ ENTITY_LIFECYCLE_CHANGES ]`** list:
   * 🟢 **`ADDED`**: New classes/functions introduced.
   * 🔴 **`REMOVED`**: Deprecated or deleted symbols.
   * 🟡 **`MODIFIED`**: Symbols whose implementation or signature changed.
3. Inspect **`[ DEPENDENCY_GRAPH_CHANGES ]`**: Shows new or removed `CALLS` and `IMPORTS` edges.

### 8.3: Architecture Drift Findings
Alerts you to unintended architectural degradation, such as a utility module suddenly calling high-level application handlers.

---

## Chapter 9: Codebase Health Radar & Git Intelligence

### 9.1: Health Radar (`/repositories/:id/health`)
* **Structural Topology**: Instant counts of total files, classes, functions, and circular dependency loops.
* **Risk Factors**: Lists functions with Cyclomatic Complexity > 15 and modules with high coupling.

### 9.2: Git Intelligence (`/repositories/:id/git`)
* **Commits & Contributors**: Total commits analyzed and active contributors.
* **Risk Hotspots**: Files with high churn + high complexity (the #1 source of production regressions).
* **Most Churned Files**: Code files with the highest line additions/deletions.
* **Author Touch Matrix**: Breakdown of commits and line velocity per contributor.

---

## Chapter 10: Troubleshooting, FAQ & Pro Tips

### Q1: Why is the 3D graph blank or showing only top-level nodes?
* **Answer**: Archon loads top-level modules by default to maintain 60 FPS performance on large repos. Simply click or double-click any module node, or use the **`> query_symbol…`** search box to expand sub-trees on demand.

### Q2: How do I clear an active Blast Radius visualization?
* **Answer**: In the Impact panel, click the **`✕`** close button or select a different node.

### Q3: My repository analysis failed with an error.
* **Answer**: Verify that the repository contains valid Python code. Check Docker container logs:
  ```bash
  docker-compose logs -f backend
  ```

### Q4: Pro Tip — Keyboard Shortcuts:
* **`Enter` (in search input)**: Auto-selects the top matching symbol and centers the camera.
* **`Escape` (in search input)**: Closes the search dropdown.
* **`Scroll Wheel`**: Zooms in and out smoothly on both 3D Galaxy and 2D Planar graphs.

---

<div align="center">

**ARCHON :: CODE INTELLIGENCE PLATFORM**  
*Deterministic Graphs. Verifiable Reasoning. Zero Hallucinations.*

</div>
