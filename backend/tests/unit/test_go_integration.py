"""
Integration Tests for Go Parser (Slice ML-7)

Verifies:
  1. Scanner automatically discovers .go files via registry.supported_extensions()
  2. GraphBuilder consumes Go ParsedFile without Go-specific pipeline branches
  3. EmbeddingGenerator extracts semantic units from Go ParsedFile
  4. Cross-Language Endpoint Resolver matches TypeScript/JavaScript calls to Go Gin & net/http routes
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from archon.pipeline.ingestion.scanner import scan_directory
from archon.pipeline.parsers.registry import registry
from archon.pipeline.parsers.go.parser import GoParser
from archon.pipeline.parsers.typescript.parser import TypeScriptParser
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.embeddings.generator import EmbeddingGenerator
from archon.pipeline.resolution.endpoints import EndpointResolver


def test_scanner_automatically_discovers_go(tmp_path: Path):
    """Scanner discovers .go files solely via registry.supported_extensions()."""
    assert ".go" in registry.supported_extensions()

    (tmp_path / "main.go").write_text("package main\nfunc main() {}", encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "payment.go").write_text("package services\ntype PaymentService struct {}", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("hello", encoding="utf-8")

    discovered = scan_directory(tmp_path)
    discovered_posix = [str(p).replace("\\", "/") for p in discovered]

    assert any(p.endswith("main.go") for p in discovered_posix)
    assert any(p.endswith("services/payment.go") for p in discovered_posix)
    assert not any(p.endswith("ignored.txt") for p in discovered_posix)


@patch("archon.pipeline.graph.builder.neo4j_driver")
@patch("archon.pipeline.graph.builder.async_session_factory")
async def test_graph_builder_accepts_go_parsed_files(mock_db, mock_driver):
    """GraphBuilder creates Neo4j nodes from Go ParsedFile without Go-specific branches."""
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    go_code = """
package services

import "fmt"

type OrderService struct {
    BaseService
}

func (s *OrderService) ProcessOrder(id int) error {
    return nil
}
"""
    parser = GoParser()
    pfile = parser.parse_file("src/services/order.go", go_code)

    builder = GraphBuilder(uuid.uuid4(), uuid.uuid4(), "commit-sha")
    builder._build_git_graph = AsyncMock()
    await builder.build([pfile])

    cypher_calls = [call_args[0][0] for call_args in mock_session.run.call_args_list if call_args[0]]
    assert any("MERGE (m:Module" in q for q in cypher_calls)
    assert any("MERGE (c:Class" in q for q in cypher_calls)
    assert any("MERGE (func:Function" in q for q in cypher_calls)


def test_embedding_generator_extracts_go_semantic_units():
    """EmbeddingGenerator extracts semantic chunks from Go structs, functions, and methods."""
    go_code = """
package services

type OrderService struct {}

func (s *OrderService) Process() {
    // execute order
}

func Helper() {}
"""
    parser = GoParser()
    pfile = parser.parse_file("src/services/order.go", go_code)

    generator = EmbeddingGenerator(uuid.uuid4(), uuid.uuid4())
    units = generator._extract_semantic_units([pfile])

    assert len(units) >= 1
    assert any("OrderService" in u.get("qualified_name", "") or "Process" in u.get("source_text", "") for u in units)


def test_cross_language_http_resolution_ts_to_go_gin():
    """Resolves TypeScript fetch / axios calls to Go Gin and net/http routes."""
    # 1. Go Gin Backend
    go_code = """
package routes

import (
    "net/http"
    "github.com/gin-gonic/gin"
)

func Register(r *gin.Engine, svc *OrderService) {
    r.GET("/api/v1/orders", svc.ListOrders)
    r.POST("/api/v1/orders/create", svc.CreateOrder)
    
    api := r.Group("/api/v1/users")
    api.GET("/profile", svc.GetProfile)

    http.HandleFunc("/api/v1/health", HealthCheck)
}

func HealthCheck(w http.ResponseWriter, r *http.Request) {}
"""
    go_parser = GoParser()
    go_pfile = go_parser.parse_file("backend/routes/routes.go", go_code)

    # 2. TypeScript Frontend
    ts_code = """
export async function fetchOrders(): Promise<void> {
    await fetch("/api/v1/orders");
}

export async function submitOrder(order: any): Promise<void> {
    await axios.post("/api/v1/orders/create", order);
}

export async function getUserProfile(): Promise<void> {
    await fetch("/api/v1/users/profile");
}

export async function checkHealth(): Promise<void> {
    await fetch("/api/v1/health");
}
"""
    ts_parser = TypeScriptParser()
    ts_pfile = ts_parser.parse_file("frontend/src/api/orders.ts", ts_code)

    file_contents = {
        "backend/routes/routes.go": go_code,
        "frontend/src/api/orders.ts": ts_code
    }

    resolver = EndpointResolver()
    results = resolver.resolve([go_pfile, ts_pfile], file_contents)

    # 4 endpoints matched -> 8 resolution results (4 REQUESTS + 4 HANDLED_BY)
    assert len(results) == 8

    req_results = [r for r in results if r.relationship == "REQUESTS"]
    assert len(req_results) == 4

    handled_results = [r for r in results if r.relationship == "HANDLED_BY"]
    assert len(handled_results) == 4

    # Check Gin GET /api/v1/orders
    get_orders_req = next(r for r in req_results if "endpoint:GET:/api/v1/orders" == r.target_id)
    assert get_orders_req.source_id == f"{ts_pfile.module_name}.fetchOrders"
    assert get_orders_req.target_language == "go"

    get_orders_hby = next(r for r in handled_results if "endpoint:GET:/api/v1/orders" == r.source_id)
    assert "ListOrders" in get_orders_hby.target_id
    assert get_orders_hby.target_language == "go"

    # Check Gin Group GET /api/v1/users/profile
    profile_req = next(r for r in req_results if "endpoint:GET:/api/v1/users/profile" == r.target_id)
    assert profile_req.source_id == f"{ts_pfile.module_name}.getUserProfile"
    assert profile_req.target_language == "go"

    # Check net/http GET /api/v1/health
    health_req = next(r for r in req_results if "endpoint:GET:/api/v1/health" == r.target_id)
    assert health_req.source_id == f"{ts_pfile.module_name}.checkHealth"

    health_hby = next(r for r in handled_results if "endpoint:GET:/api/v1/health" == r.source_id)
    assert "HealthCheck" in health_hby.target_id
    assert health_hby.target_language == "go"
