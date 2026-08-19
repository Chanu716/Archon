# Archon — Technical Architecture & Design Document

> **Version**: MVP Design v1.1
> **Status**: Approved — Ready for implementation
> **Principle**: Structure first. Intelligence second.

---

## Table of Contents

1. [Complete System Architecture](#1-complete-system-architecture)
2. [Component and Service Boundaries](#2-component-and-service-boundaries)
3. [Project and Folder Structure](#3-project-and-folder-structure)
4. [PostgreSQL Schema](#4-postgresql-schema)
5. [Neo4j Graph Schema](#5-neo4j-graph-schema)
6. [pgvector Data Model](#6-pgvector-data-model)
7. [Python Parser Architecture](#7-python-parser-architecture)
8. [Static Analysis Architecture](#8-static-analysis-architecture)
9. [Git Analysis Architecture](#9-git-analysis-architecture)
10. [Analysis Job Lifecycle](#10-analysis-job-lifecycle)
11. [Repository Storage Layer](#11-repository-storage-layer)
12. [Analysis Snapshot Concept](#12-analysis-snapshot-concept)
13. [API Endpoint Design](#13-api-endpoint-design)
14. [AI Analyst Tool Definitions](#14-ai-analyst-tool-definitions)
15. [Data Flow Between Major Components](#15-data-flow-between-major-components)
16. [Frontend Page and Component Architecture](#16-frontend-page-and-component-architecture)
17. [Docker Compose Architecture](#17-docker-compose-architecture)
18. [Configuration and Environment Variables](#18-configuration-and-environment-variables)
19. [Error Handling Strategy](#19-error-handling-strategy)
20. [Logging and Observability Strategy](#20-logging-and-observability-strategy)
21. [Testing Strategy](#21-testing-strategy)
22. [Security Considerations](#22-security-considerations)
23. [Future Extension Points — Additional Languages](#23-future-extension-points--additional-languages)
24. [Future Extension Point — ChaOS Integration](#24-future-extension-point--chaos-integration)

---

## Source of Truth Hierarchy

This hierarchy is fundamental and must never be violated:

```
SOURCE REPOSITORY
       ↓
     PARSER
       ↓
DETERMINISTIC FACTS
       ↓
KNOWLEDGE GRAPH  (Archon's structured representation)
       ↓
METRICS / RETRIEVAL
       ↓
AI REASONING
```

**Neo4j is not the ultimate source of truth. The original repository is.**

If the graph ever diverges from the source code, the graph is stale and must be regenerated. The LLM is never a source of truth for repository structure.

### Three Categories of Information — Must Never Be Conflated

| Category | Example | Presentation |
|---|---|---|
| **Deterministic Fact** | Cyclomatic Complexity = 17, Fan-out = 12, Commits = 31 | Shown as data with source: "computed" |
| **Archon Heuristic** | Risk Score = 0.73, Risk Level = HIGH | Labeled "Archon Risk Heuristic v1" |
| **AI Interpretation** | "This module may be a maintenance hotspot." | Labeled "AI Analysis" |

---

## 1. Complete System Architecture

### The Two-Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCE REPOSITORY                         │
│              (Ultimate Source of Truth)                     │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   DETERMINISTIC LAYER                        │
│                                                             │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │  Repository  │  │  Python Parser  │  │  Git Analyzer │  │
│  │  Ingestion   │  │  (AST module)   │  │  (GitPython)  │  │
│  └──────┬───────┘  └────────┬────────┘  └───────┬───────┘  │
│         │                   │                   │           │
│         └───────────────────┴───────────────────┘           │
│                             │                               │
│                             ▼                               │
│                   ┌──────────────────┐                      │
│                   │  Static Analysis │                      │
│                   │  Engine          │                      │
│                   └────────┬─────────┘                      │
│                            │                                │
│                            ▼                                │
│                   ┌──────────────────┐                      │
│                   │  Knowledge Graph │                      │
│                   │  (Neo4j)         │                      │
│                   │  [NOT the source │                      │
│                   │   of truth]      │                      │
│                   └────────┬─────────┘                      │
│                            │                                │
│              ┌─────────────┴─────────────┐                  │
│              ▼                           ▼                  │
│     ┌──────────────┐          ┌───────────────────┐         │
│     │Graph Analysis│          │Architecture       │         │
│     │(traversal,   │          │Metrics + Archon   │         │
│     │cycles,       │          │Risk Heuristic v1  │         │
│     │centrality)   │          └───────────────────┘         │
│     └──────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼ (structured evidence only — never raw code dumps)
┌─────────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER                        │
│                                                             │
│  ┌──────────────────┐      ┌──────────────────────────┐     │
│  │  Semantic Index  │      │  Graph Retrieval         │     │
│  │  PostgreSQL +    │      │  (Cypher queries via     │     │
│  │  pgvector        │      │   Graph Service)         │     │
│  └────────┬─────────┘      └────────────┬─────────────┘     │
│           │                             │                   │
│           └─────────────┬───────────────┘                   │
│                         │                                   │
│                         ▼                                   │
│                ┌─────────────────┐                          │
│                │   AI Analyst    │                          │
│                │  (Tool-calling  │                          │
│                │   LLM)         │                          │
│                │                │                          │
│                │ Deterministic   │                          │
│                │ layer must NOT  │                          │
│                │ depend on this  │                          │
│                └─────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    API LAYER (FastAPI)                       │
│  REST endpoints / SSE streaming                             │
│  Job Manager → Execution Adapter → Pipeline                 │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              FRONTEND (React + TypeScript)                   │
│  Dashboard / Graph visualization / AI chat / Code explorer  │
└─────────────────────────────────────────────────────────────┘
```

### Critical Architectural Rule: Deterministic Layer Never Calls the LLM

```
Parser              ❌ must not call LLM
Static Analyzer     ❌ must not call LLM
Git Analyzer        ❌ must not call LLM
Graph Builder       ❌ must not call LLM
AI Analyst          ✅ may query results from all of them
```

---

## 2. Component and Service Boundaries

### Backend Process Boundaries

All components run within the same FastAPI process for MVP. They are structurally separated so they can be extracted later.

```
archon-api (single FastAPI process)
│
├── API Layer              → HTTP routing, response shaping
├── Job Manager            → creates, tracks, updates analysis jobs
├── Execution Adapter      → abstracts job execution mechanism
│   ├── BackgroundTasksAdapter  ← MVP (FastAPI BackgroundTasks)
│   └── CeleryAdapter           ← Future (Redis/Celery)
├── Analysis Pipeline      → framework-independent, pure Python
│   ├── Ingestion          → clones/scans repo; produces IngestionResult
│   ├── Parser             → language-agnostic + Python implementation
│   ├── Static Analyzer    → computes deterministic metrics
│   ├── Git Analyzer       → extracts git history
│   ├── Graph Builder      → writes Neo4j nodes and relationships
│   └── Embedder           → generates and stores pgvector embeddings
├── Repository Storage     → safe filesystem access layer
│   └── get_file(repo_id, relative_path) — never raw user path
├── Graph Service          → query-side Neo4j access (Cypher)
├── Search Service         → pgvector similarity search
├── AI Service             → LLM provider abstraction + tool orchestration
└── DB Layer               → SQLAlchemy ORM for PostgreSQL
```

### Execution Adapter Pattern (Correction #1)

The analysis pipeline has NO dependency on FastAPI `BackgroundTasks`. The adapter handles the mechanics of scheduling:

```
API Layer
    ↓
Job Manager                (creates DB record)
    ↓
Execution Adapter          (schedules execution)
    ↓
Analysis Pipeline          (pure Python, no HTTP framework dependency)
```

The pipeline can be invoked directly in:
- Tests (no FastAPI needed)
- Celery workers (future)
- CLI scripts (debugging)

---

## 3. Project and Folder Structure

```
archon/
│
├── docker-compose.yml
├── .env.example
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   │
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── archon/
│   │   ├── main.py               (FastAPI app)
│   │   ├── config.py             (pydantic-settings)
│   │   │
│   │   ├── api/v1/
│   │   │   ├── deps.py
│   │   │   ├── repositories.py
│   │   │   ├── analysis.py
│   │   │   ├── graph.py
│   │   │   ├── search.py
│   │   │   ├── ai.py
│   │   │   └── health.py
│   │   │
│   │   ├── models/               (SQLAlchemy ORM)
│   │   │   ├── base.py
│   │   │   ├── repository.py
│   │   │   └── analysis_job.py
│   │   │
│   │   ├── schemas/              (Pydantic API contracts)
│   │   │
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── neo4j.py
│   │   │
│   │   ├── pipeline/             (Framework-independent — no FastAPI imports)
│   │   │   ├── orchestrator.py
│   │   │   ├── ingestion/
│   │   │   │   ├── base.py       (IngestionResult)
│   │   │   │   ├── github.py
│   │   │   │   ├── local.py
│   │   │   │   └── scanner.py
│   │   │   ├── parsers/
│   │   │   │   ├── base.py       (LanguageParser ABC + parsed models)
│   │   │   │   ├── registry.py
│   │   │   │   └── python/
│   │   │   │       └── parser.py
│   │   │   ├── analysis/
│   │   │   │   ├── complexity.py
│   │   │   │   ├── dependencies.py
│   │   │   │   ├── coupling.py
│   │   │   │   ├── cycles.py
│   │   │   │   └── hotspots.py
│   │   │   ├── git/
│   │   │   │   ├── models.py
│   │   │   │   └── analyzer.py
│   │   │   ├── graph/
│   │   │   │   ├── builder.py
│   │   │   │   └── queries.py
│   │   │   └── embeddings/
│   │   │       ├── chunker.py
│   │   │       └── embedder.py
│   │   │
│   │   ├── services/
│   │   │   ├── repository_service.py
│   │   │   ├── job_service.py
│   │   │   ├── storage_service.py    (safe file access — NEW)
│   │   │   ├── graph_service.py
│   │   │   ├── search_service.py
│   │   │   └── ai/
│   │   │       ├── analyst.py
│   │   │       ├── tools.py
│   │   │       └── providers/
│   │   │           ├── base.py       (LLMProvider ABC)
│   │   │           ├── openai.py
│   │   │           └── anthropic.py
│   │   │
│   │   ├── execution/                (NEW — Execution Adapter pattern)
│   │   │   ├── base.py              (ExecutionAdapter ABC)
│   │   │   ├── background_tasks.py  (BackgroundTasksAdapter — MVP)
│   │   │   └── celery_adapter.py    (CeleryAdapter — future stub)
│   │   │
│   │   └── utils/
│   │       ├── logging.py
│   │       └── exceptions.py
│   │
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── test_python_parser.py
│       │   ├── test_complexity.py
│       │   ├── test_cycles.py
│       │   └── test_hotspots.py
│       ├── integration/
│       └── fixtures/
│           └── sample_repos/
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── api/
        ├── components/
        ├── pages/
        ├── store/
        └── types/
```

---

## 4. PostgreSQL Schema

PostgreSQL stores operational data and metric snapshots. It does NOT store the knowledge graph or raw source code.

### Key Tables

1. **repositories** — `id`, `name`, `source_type`, `source_url`, `managed_path` (under REPOS_BASE_PATH), `detected_languages`, `last_analyzed_at`, `last_analyzed_commit`

2. **analysis_jobs** — `id`, `repository_id`, `status` (queued/running/completed/failed/cancelled), `current_stage`, `progress`, `error_message`, `started_at`, `completed_at`

3. **analysis_snapshots** — `id`, `repository_id`, `analysis_job_id`, `commit_sha`, `analyzed_at`, `archon_version`, `parser_version` *(new in v1.1)*

4. **repository_metrics** — Snapshot of aggregate counts and averages, linked to an `analysis_snapshot_id`

5. **file_metrics** — Per-file: `file_path`, `max_cyclomatic_complexity`, `fan_in`, `fan_out`, `churn_count`, `risk_score`, `risk_level`, linked to `analysis_snapshot_id`

6. **function_metrics** — Per-function: `qualified_name`, `cyclomatic_complexity`, `line_count`, `call_resolution_counts` (exact/inferred/unresolved), linked to `analysis_snapshot_id`

7. **code_embeddings** — pgvector table (see Section 6)

### Note on risk_score and risk_level fields

These fields store the **Archon Risk Heuristic v1** output, not an objective measurement. The API response schema labels them accordingly.

---

## 5. Neo4j Graph Schema

### Node Types

- `Repository`: `id`, `name`, `snapshot_id`, `commit_sha`
- `Directory`: `path`, `name`, `depth`
- `File`: `path`, `language`, `total_lines`
- `Module`: `qualified_name`
- `Class`: `qualified_name`, `line_count`, `base_classes`
- `Function`: `qualified_name`, `cyclomatic_complexity`, `is_method`, `is_async`
- `Commit`: `sha`, `message`, `timestamp`
- `Developer`: `name`, `email`

### Relationship Types

```
Structural:
(:Repository)-[:CONTAINS]->(:Directory | :File)
(:Directory)-[:CONTAINS]->(:Directory | :File)
(:File)-[:DEFINES]->(:Module)
(:File)-[:CONTAINS]->(:Class | :Function)
(:Class)-[:CONTAINS]->(:Function)

Code relationships:
(:File)-[:IMPORTS]->(:File)
(:Function)-[:CALLS {resolution: "exact"|"inferred"|"unresolved"}]->(:Function)
(:Class)-[:INHERITS]->(:Class)

Git relationships:
(:Developer)-[:AUTHORED]->(:Commit)
(:Commit)-[:CHANGED]->(:File)
(:File)-[:MODIFIED_BY]->(:Developer)
```

### Call Resolution Property (Correction #4)

Every `CALLS` relationship carries a `resolution` property:

| Value | Meaning |
|---|---|
| `exact` | Resolved to a specific function in a known file with high confidence |
| `inferred` | Plausible resolution based on import analysis, but not certain |
| `unresolved` | Call detected but target could not be determined statically |

**Unresolved calls are recorded as `(:Function)-[:CALLS {resolution: "unresolved"}]->(:UnresolvedCall {name: "..."})` rather than fabricated relationships.**

The UI and AI analyst must visually and semantically distinguish these three states.

### APOC Usage Policy (Correction #6)

APOC is included in Docker Compose as an available plugin. However:

```
Priority 1: Native Cypher (always preferred for clarity)
Priority 2: Application-level Python graph algorithms (for complex traversals)
Priority 3: APOC (only when native Cypher is impractical)
```

When APOC is used for a feature, the code must include a comment explaining:
1. Why native Cypher is insufficient
2. What the APOC procedure provides
3. Whether a native alternative exists

---

## 6. pgvector Data Model

### Configuration-Driven Dimensions (Correction #2)

The embedding dimension is **never hardcoded**. It is derived from configuration:

```
EMBEDDING_PROVIDER = "openai"
EMBEDDING_MODEL    = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536   ← must match the model above; documented
```

The `code_embeddings` table is created with the dimension from configuration at migration time. Changing the embedding model later requires a migration to recreate the table with the new dimension. This cost is explicitly documented.

### code_embeddings Table

- `id` (UUID)
- `repository_id`, `analysis_snapshot_id` (UUID)
- `file_path`, `chunk_type` ('function', 'method', 'class', 'module_docstring', 'commit_message')
- `qualified_name`, `start_line`, `end_line`
- `content` (text), `content_hash` (SHA256 for dedup)
- `embedding` (vector — dimension from EMBEDDING_DIMENSIONS setting)

HNSW index on `embedding` column. Filter indexes on `repository_id` and `chunk_type`.

---

## 7. Python Parser Architecture

### The Language-Agnostic Abstraction

`LanguageParser` ABC defines:
- `language: str` property
- `file_extensions: list[str]` property
- `parse_file(path: str, content: str) -> ParsedFile` — must not raise; capture errors in `ParsedFile.parse_errors`

`ParserRegistry` maps extensions to parser instances. Adding a new language = register one class.

### Parsed Data Models

Key models: `ParsedFile`, `ParsedClass`, `ParsedFunction`, `ParsedImport`, `ParsedParameter`

### Python Implementation

Uses Python's built-in `ast` module. Extracts functions, classes, methods, parameters, imports, decorators, inheritance, docstrings.

### Call Resolution Strategy (Correction #4)

Call extraction is explicit about confidence level:

```python
@dataclass
class ResolvedCall:
    raw_name: str              # as found in source: "self.service.process"
    target_qualified_name: Optional[str]  # resolved target or None
    resolution: str            # "exact" | "inferred" | "unresolved"
    resolution_note: Optional[str]  # e.g. "method call on untyped object"
```

Resolution rules:
- **exact**: Module-level function call where the function is defined in an imported module deterministically resolvable from the import list
- **inferred**: Call plausibly matches a known function in scope but cannot be confirmed without type information (e.g., `self.foo()` where class has `foo` method)
- **unresolved**: Call name present but target cannot be determined statically (e.g., `getattr(obj, name)()`, calls on external libraries)

The parser **never invents** an `exact` relationship when only `inferred` is justified.

### Cyclomatic Complexity

CC = 1 + count of decision points: `if`, `elif`, `for`, `while`, `except` (each handler), `with`, `assert`, `and`/`or` operators, ternary expressions, comprehension `if` clauses, `match`/`case` arms.

---

## 8. Static Analysis Architecture

### Order of Operations

```
ParsedFile list
       │
       ▼
1. build_dependency_graph()     — resolves imports to file paths
       │
       ▼
2. detect_cycles()              — DFS with color-marking
       │
       ▼
3. compute_fan_metrics()        — fan_in, fan_out per file
       │
       ▼
4. compute_coupling_scores()    — normalize to 0-1
       │
       ▼
5. compute_risk_scores()        — apply Archon Risk Heuristic v1
```

### Archon Risk Heuristic v1 (Correction #5)

This is an engineering heuristic, NOT a universal software quality measurement.

```
risk = RISK_WEIGHT_COMPLEXITY * normalized_complexity
     + RISK_WEIGHT_COUPLING   * normalized_coupling
     + RISK_WEIGHT_CHURN      * normalized_churn

Defaults:
  RISK_WEIGHT_COMPLEXITY = 0.40   (configurable)
  RISK_WEIGHT_COUPLING   = 0.30   (configurable)
  RISK_WEIGHT_CHURN      = 0.30   (configurable)

Classification thresholds (configurable):
  0.00 – 0.30  LOW
  0.30 – 0.60  MODERATE
  0.60 – 0.80  HIGH
  0.80 – 1.00  CRITICAL
```

Normalization uses min-max across the repository. `complexity_score` is derived from the **maximum** cyclomatic complexity of any function in the file.

### Metric Tagging in API Responses

Every metric value in API responses includes a `metric_source` field:

```json
{ "cyclomatic_complexity": 17, "metric_source": "deterministic" }
{ "risk_score": 0.73,          "metric_source": "archon_heuristic_v1" }
{ "interpretation": "...",     "metric_source": "ai_interpretation" }
```

The frontend renders these three source types with distinct visual treatments.

---

## 9. Git Analysis Architecture

Uses `GitPython`. Scope is configurable (`GIT_MAX_COMMITS`, `GIT_SINCE_DAYS`).

**Extracts:**
- Commits: SHA, message, author, timestamp, changed files
- File churn: commit count, last modified, distinct contributors
- Developer stats: total commits, files touched

**Scope limits are surfaced** in the API response so users know their churn data reflects a sample if the full history exceeds the limit.

---

## 10. Analysis Job Lifecycle

### State Machine
`queued` → `running` → `completed` | `failed` | `cancelled`

### Stages with Progress
1. `ingestion` (0–10%)
2. `parsing` (10–35%)
3. `static_analysis` (35–50%)
4. `git_analysis` (50–60%)
5. `graph_construction` (60–80%)
6. `graph_analysis` (80–85%)
7. `embedding` (85–98%)
8. `finalizing` (98–100%)

Progress is written to PostgreSQL via a progress callback injected into the orchestrator. The pipeline itself has no direct dependency on HTTP or the database layer; the callback is the only coupling point.

### Execution Adapter (Correction #1)

```python
class ExecutionAdapter(ABC):
    @abstractmethod
    async def submit(self, job_id: UUID, pipeline_fn: Callable) -> None:
        """Schedule pipeline_fn to run asynchronously."""

class BackgroundTasksAdapter(ExecutionAdapter):
    """MVP: Uses FastAPI BackgroundTasks. Replaced by CeleryAdapter later."""
    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    async def submit(self, job_id, pipeline_fn):
        self.background_tasks.add_task(pipeline_fn, job_id)
```

The pipeline function `pipeline_fn` is a plain async Python function with no FastAPI imports.

---

## 11. Repository Storage Layer (New in v1.1)

### Design (Correction #3)

Repositories are stored under a controlled, application-managed directory. User input (e.g., a relative file path from an API request) is **never** used directly in filesystem operations.

**Managed storage:**
```
{REPOS_BASE_PATH}/
└── {repository_id}/        ← UUID prevents path traversal
    └── <cloned or copied repo contents>
```

**Storage Service API:**
```python
class RepositoryStorageService:
    def get_repository_path(self, repository_id: UUID) -> Path:
        """Returns the root path for a repository. Always within REPOS_BASE_PATH."""

    def get_file(self, repository_id: UUID, relative_path: str) -> str:
        """
        Safely reads a file from within a repository.
        Raises PathTraversalError if relative_path escapes the repository root.
        Never accepts absolute paths from user input.
        """

    def resolve_safe_path(self, repository_id: UUID, relative_path: str) -> Path:
        """
        Resolves and validates a path. Uses Path.resolve() then checks
        the result is still inside the repository root.
        """
```

**Security invariants:**
- All paths are validated with `Path.resolve()` and confirmed to start with `get_repository_path(repo_id)`
- If the resolved path escapes the repository root → `PathTraversalError` (HTTP 400)
- Absolute paths from user input are always rejected
- The AI `get_file()` tool calls this service; it does NOT touch the filesystem directly

**Archon NEVER executes repository code (Correction #7):**
- No `eval()`, no `exec()`
- No `subprocess` calls with repository content as executable
- No running of repository scripts, tests, build systems, or package lifecycles
- Repository contents are treated as **untrusted data** parsed statically

---

## 12. Analysis Snapshot Concept (New in v1.1)

### Purpose

Every analysis represents Archon's interpretation of a repository **at a specific point in time**. This is formalized as an `AnalysisSnapshot`.

```
Repository
    │
    ├── AnalysisSnapshot #1  (commit abc123, analyzed 2025-01-10)
    │       └── Metrics, Graph, Embeddings for abc123
    │
    ├── AnalysisSnapshot #2  (commit def456, analyzed 2025-01-20)
    │       └── Metrics, Graph, Embeddings for def456
    │
    └── AnalysisSnapshot #3  (commit xyz789, analyzed 2025-02-01)
            └── Metrics, Graph, Embeddings for xyz789
```

### Schema

```sql
CREATE TABLE analysis_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id   UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    analysis_job_id UUID NOT NULL REFERENCES analysis_jobs(id),
    commit_sha      TEXT,           -- HEAD commit at time of analysis; nullable if no git
    analyzed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archon_version  TEXT NOT NULL,  -- e.g., "0.1.0"
    parser_version  TEXT NOT NULL,  -- e.g., "python-ast-0.1.0"
    is_latest       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id, commit_sha)
);
```

**MVP behavior:**
- One snapshot per analysis run
- `is_latest = TRUE` is set on the new snapshot; previous snapshots are set to `is_latest = FALSE`
- All `file_metrics`, `function_metrics`, `repository_metrics`, and `code_embeddings` rows are linked to `analysis_snapshot_id`
- All Neo4j nodes carry a `snapshot_id` property

**This design enables future features without redesigning the data model:**
- Architecture evolution tracking
- "How did complexity change between commits?"
- Architectural drift detection

---

## 13. API Endpoint Design

All endpoints under `/api/v1/`.

### Repositories
- `POST /repositories` — register a repo (GitHub URL or local path)
- `GET /repositories` — list all
- `GET /repositories/{id}` — detail with latest snapshot summary
- `DELETE /repositories/{id}` — remove repo, jobs, snapshot, embeddings, Neo4j subgraph

### Analysis
- `POST /repositories/{id}/analyze` — queue analysis job
- `GET /analysis-jobs/{job_id}` — poll progress
- `GET /repositories/{id}/analysis-jobs` — history

### Snapshots
- `GET /repositories/{id}/snapshots` — list all snapshots
- `GET /repositories/{id}/snapshots/latest` — current snapshot detail

### Graph
- `GET /repositories/{id}/graph/overview`
- `GET /repositories/{id}/graph/callers/{qualified_name}`
- `GET /repositories/{id}/graph/callees/{qualified_name}`
- `GET /repositories/{id}/graph/dependencies/{file_path}`
- `GET /repositories/{id}/graph/impact/{qualified_name}`
- `GET /repositories/{id}/graph/cycles`
- `GET /repositories/{id}/graph/hotspots`

### Metrics
- `GET /repositories/{id}/metrics` — repo-level snapshot
- `GET /repositories/{id}/metrics/files` — sorted by risk_score
- `GET /repositories/{id}/metrics/functions` — sorted by complexity

### Search
- `GET /repositories/{id}/search?q=...`

### Git
- `GET /repositories/{id}/git/summary`
- `GET /repositories/{id}/git/contributors`
- `GET /repositories/{id}/git/hotspots`
- `GET /repositories/{id}/git/history?file_path=...`

### AI Analyst
- `POST /repositories/{id}/ai/query` — SSE streaming

### Response Conventions
- All successful responses use a consistent envelope: `{ "data": ..., "meta": ... }`
- Error responses: `{ "error": { "code": "...", "message": "..." } }`
- Metric values always include `metric_source` in their schema

---

## 14. AI Analyst Tool Definitions

The LLM receives tools, not raw Cypher or filesystem access.

| Tool | Purpose |
|---|---|
| `query_graph(query_name, params)` | Named Cypher templates only — no raw Cypher from LLM |
| `search_code(query, chunk_types, limit)` | Semantic pgvector search |
| `get_file(file_path)` | Reads file via `RepositoryStorageService` (safe) |
| `get_function(qualified_name)` | Function source + metrics |
| `get_metrics(target_type, target_id)` | Deterministic metrics with `metric_source` tag |
| `get_dependencies(file_path, depth)` | Dependency traversal |
| `get_callers(qualified_name, depth)` | Reverse call graph |
| `get_callees(qualified_name, depth)` | Forward call graph |
| `get_git_history(file_path, limit)` | Churn and commits |
| `get_architecture_summary()` | Repo-level overview |

**System Prompt Invariants:**
1. Only make claims supported by tool-returned data
2. Label deterministic metrics as "computed"; label interpretations as "AI analysis"
3. Label risk scores as "Archon Risk Heuristic v1"
4. Distinguish `exact` / `inferred` / `unresolved` call relationships when reasoning about call chains
5. Include a Sources section in every answer

---

## 15. Data Flow Between Major Components

### Full Pipeline Flow

```
1. POST /repositories → create repo record → return repo

2. POST /repositories/{id}/analyze
   → job_service.create_job()
   → execution_adapter.submit(job_id, run_pipeline)
   → return { job_id, status: "queued" }

3. BACKGROUND (framework-independent):
   Orchestrator.run(job_id, progress_callback)

4. Ingestion: clone/copy → scan files → filter irrelevant
5. Parsing: ParserRegistry.get_parser(".py") → parse_file()
6. Static Analysis: dependency graph → cycles → fan metrics → coupling → hotspots
7. Git Analysis: walk commits → churn → contributors
8. Risk Scoring: normalize metrics → apply heuristic → classify
9. Graph Construction: MERGE Neo4j nodes + relationships
   - CALLS relationships carry resolution: exact|inferred|unresolved
10. Graph Analysis: cycle verification, centrality, hotspot tagging
11. Embedding: chunk at function/class level → embed → store pgvector
12. Finalizing: create AnalysisSnapshot → write metrics snapshots → update job COMPLETED

All writes use MERGE (idempotent). Re-analysis is safe.
```

### AI Query Flow

```
POST /repositories/{id}/ai/query { question }
   ↓
AI Analyst receives question + repository context
   ↓
Tool-calling loop:
  LLM selects tools → backend executes → structured data returned
  LLM decides: more tools OR produce final answer
   ↓
Stream final answer via SSE with Sources
  Sources distinguish: exact vs inferred call paths
  Metrics tagged as deterministic / heuristic / ai_interpretation
```

---

## 16. Frontend Page and Component Architecture

### Technology Stack
- React 18 + TypeScript (strict)
- Vite, React Router v6
- TanStack Query (server state & caching)
- Three.js WebGL (3D Force-directed Galaxy Graph)
- Cytoscape.js (2D Planar Graph with 4 layout engines: CoSE, DAG Tree, Concentric, Circle)
- Recharts (evolution & metric charts)
- Tailwind CSS

### Page Structure
- `/repositories` (`RepositoriesPage.tsx`) — repository registry and ingestion
- `/repositories/:id/overview` (`OverviewPage.tsx`) — analysis stage progress and repository hub
- `/repositories/:id/architecture` (`ArchitecturePage.tsx`) — interactive 3D Galaxy & 2D Planar architecture graphs
- `/repositories/:id/health` (`HealthDashboard.tsx`) — structural topology, complexity, and circular cycles
- `/repositories/:id/git` (`GitDashboard.tsx`) — commit velocity, author touch matrix, and churn hotspots
- `/repositories/:id/evolution` (`EvolutionDashboard.tsx`) — multi-snapshot comparison, drift findings, and timeline trends
- `/repositories/:id/investigation` (`IntelligenceWorkbench.tsx`) — multi-dimensional entity investigation dossier

### Core Component Architecture
- `ThreeDArchitectureGraph.tsx` — WebGL 3D galaxy visualization with orbit rotation, top-down 2.5D camera, and particle links
- `TwoDArchitectureGraph.tsx` — 2D Cytoscape architecture graph with layout selector, edge label toggles, and hover tracing
- `EntityDetailsPanel.tsx` — inspector drawer for AST properties, metrics (`[DET]` / `[HEU]`), and subtree expansion
- `ImpactPanel.tsx` — BFS blast radius and impact traversal with depth selection and graph highlighting
- `SemanticSearchPanel.tsx` — vector embedding code search modal with similarity scores and code snippets
- `AnalystPanel.tsx` — AI analyst console with streaming SSE reasoning traces and evidence citations

### Visual Distinction of Information Types

The UI renders three categories with distinct visual treatment:
- **Deterministic facts**: Tagged `[DET]`, computed directly from AST analysis
- **Archon Heuristic v1**: Tagged `[HEU]`, composite algorithmic risk and coupling scoring
- **AI Interpretation**: Labeled `AI Analysis`, streaming markdown with verifiable evidence citation chips

Call resolution states in graph views:
- **Exact**: solid edge with target color
- **Inferred**: directional particle stream / dashed boundary
- **Unresolved**: dimmed edge with low opacity

---

## 17. Docker Compose Architecture

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck: pg_isready

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_PLUGINS: '["apoc"]'  # APOC available but not required for core
    volumes: [neo4j_data:/data]

  api:
    build: ./backend
    volumes: [repos_storage:/repos]  # managed storage for cloned repos
    depends_on: [postgres, neo4j]

  frontend:
    build: ./frontend
    ports: ["3000:80"]
```

**APOC Note:** Included for availability, but Archon's core graph logic uses native Cypher first. APOC is used only where native alternatives are impractical.

---

## 18. Configuration and Environment Variables

All configuration via `pydantic-settings` with `.env` fallback.

```
# Database
DATABASE_URL
NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# LLM (provider-agnostic)
LLM_PROVIDER              = openai | anthropic
OPENAI_API_KEY
ANTHROPIC_API_KEY
LLM_MODEL                 = gpt-4o
LLM_TEMPERATURE           = 0.1

# Embeddings (config-driven dimensions — not hardcoded)
EMBEDDING_PROVIDER        = openai
EMBEDDING_MODEL           = text-embedding-3-small
EMBEDDING_DIMENSIONS      = 1536   # must match model above

# Storage
REPOS_BASE_PATH           = /repos

# Git Analysis (scope limits)
GIT_MAX_COMMITS           = 1000
GIT_SINCE_DAYS            = 365

# Risk Heuristic v1 (all configurable)
RISK_WEIGHT_COMPLEXITY    = 0.40
RISK_WEIGHT_COUPLING      = 0.30
RISK_WEIGHT_CHURN         = 0.30
RISK_THRESHOLD_LOW        = 0.30
RISK_THRESHOLD_MODERATE   = 0.60
RISK_THRESHOLD_HIGH       = 0.80

# App
LOG_LEVEL, DEBUG
ARCHON_VERSION            = 0.1.0
```

---

## 19. Error Handling Strategy

1. **Never swallow exceptions silently** — all caught exceptions must be logged.
2. **Recoverable vs. Fatal**: Unparseable file → log warning, continue. Neo4j failure → fail the job.
3. **File-parse failures do not abort the analysis** — they are collected as warnings in the job metadata.
4. **Path traversal attempts** → `PathTraversalError`, HTTP 400, logged at WARNING.
5. **Job failures** include a human-readable `error_message`.

---

## 20. Logging and Observability Strategy

Use **structlog** for structured JSON logging.

Log categories:
- API: request method, path, status, duration
- Pipeline: job/stage transitions, file counts, scope limit warnings
- AI: tool calls made (name only), token counts
- Security: path traversal attempts, oversized files

---

## 21. Testing Strategy

1. **Unit tests**: Parser against fixture `.py` files. CC calculation against known values. Risk formula math.
2. **Integration tests**: Full pipeline on small committed fixture repos (no network needed).
3. **Security tests**: Path traversal attempts on `RepositoryStorageService`.
4. **Parser tests**: Verify `ResolvedCall.resolution` values are correctly assigned for exact/inferred/unresolved cases.
5. Coverage target: >85% on `pipeline/` and `services/`.

---

## 22. Security Considerations

- **No code execution**: Archon never runs repository code. No `eval()`, `exec()`, subprocess with repo code. Repository is untrusted input.
- **Path traversal prevention**: `RepositoryStorageService` validates all paths. UUID-based repo directories prevent guessing.
- **SSRF prevention**: GitHub URL input validated against an allowlist of hosts; private IP ranges rejected.
- **Cypher injection**: LLM uses named templates only. No raw Cypher from user or LLM.
- **Auth stub**: `get_current_user` dependency in `api/deps.py` returns a system user for now. All repos have a nullable `owner_id` column — auth can be added without redesign.

---

## 23. Future Extension Points — Additional Languages

Adding a language:
1. Implement `LanguageParser` for the new language
2. Register in `ParserRegistry`
3. Add extension to `SUPPORTED_EXTENSIONS`

Nothing else changes. The pipeline, graph builder, metrics, and AI tools all operate on `ParsedFile` objects.

**Recommended future backend**: `tree-sitter` (consistent API for 50+ languages).

---

## 24. Future Extension Point — ChaOS Integration

Archon is fully independent. ChaOS integration is inbound API calls only.

ChaOS uses Archon's REST API. Archon's `/openapi.json` provides the tool schema.

**Clean boundary**: No Archon source file may import from, reference, or know about ChaOS.

When auth is added, ChaOS authenticates with a scoped API key via `Authorization: Bearer`.

---

## Appendix: Technology Decision Summary

| Component | Technology | Rationale |
|---|---|---|
| Backend API | FastAPI | Async, type-safe, auto OpenAPI, SSE support |
| Job Execution | BackgroundTasksAdapter (MVP) | Simple for MVP; pipeline is adapter-agnostic |
| Relational DB | PostgreSQL 16 | ACID, pgvector, mature |
| Vector Search | pgvector | Avoids a separate service; sufficient for MVP scale |
| Graph DB | Neo4j 5 Community | Graph-native; Cypher for traversal queries |
| Graph Algorithms | Native Cypher first; APOC as supplement | Keeps core logic readable and APOC-independent |
| Parser (Python) | `ast` module | Built-in, no dependencies, safe (no code exec) |
| Git | GitPython | Pythonic, well-maintained |
| LLM | Provider-abstracted (OpenAI default) | Swappable via LLMProvider ABC |
| Embeddings | Config-driven (text-embedding-3-small default) | Dimension not hardcoded; provider-swappable |
| Frontend | React 18 + TypeScript + Vite | Industry standard |
| Graph Visualization | Cytoscape.js | Graph-native, large-graph layout algorithms |
| Containers | Docker Compose | Full local stack in one command |
