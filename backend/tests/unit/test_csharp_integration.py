"""
Integration Tests for C# & .NET Parser (Slice ML-6)

Verifies:
  1. Scanner automatically discovers .cs files via registry.supported_extensions()
  2. GraphBuilder consumes C# ParsedFile without C#-specific pipeline branches
  3. EmbeddingGenerator extracts semantic units from C# ParsedFile
  4. Cross-Language Endpoint Resolver matches TypeScript/JavaScript calls to C# ASP.NET Core routes
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from archon.pipeline.ingestion.scanner import scan_directory
from archon.pipeline.parsers.registry import registry
from archon.pipeline.parsers.csharp.parser import CSharpParser
from archon.pipeline.parsers.typescript.parser import TypeScriptParser
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.embeddings.generator import EmbeddingGenerator
from archon.pipeline.resolution.endpoints import EndpointResolver


def test_scanner_automatically_discovers_csharp(tmp_path: Path):
    """Scanner discovers .cs files solely via registry.supported_extensions()."""
    assert ".cs" in registry.supported_extensions()

    (tmp_path / "Program.cs").write_text("public class Program {}", encoding="utf-8")
    (tmp_path / "Services").mkdir()
    (tmp_path / "Services" / "PaymentService.cs").write_text("namespace Services; public class PaymentService {}", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("hello", encoding="utf-8")

    discovered = scan_directory(tmp_path)
    discovered_posix = [str(p).replace("\\", "/") for p in discovered]

    assert any(p.endswith("Program.cs") for p in discovered_posix)
    assert any(p.endswith("Services/PaymentService.cs") for p in discovered_posix)
    assert not any(p.endswith("ignored.txt") for p in discovered_posix)


@patch("archon.pipeline.graph.builder.neo4j_driver")
@patch("archon.pipeline.graph.builder.async_session_factory")
async def test_graph_builder_accepts_csharp_parsed_files(mock_db, mock_driver):
    """GraphBuilder creates Neo4j nodes from C# ParsedFile without C#-specific branches."""
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    cs_code = """
namespace MyApp.Services;

using System.Threading.Tasks;

public class PaymentService : BaseService, IPaymentService
{
    public async Task<bool> ProcessPayment(int id)
    {
        return true;
    }
}
"""
    parser = CSharpParser()
    pfile = parser.parse_file("src/Services/PaymentService.cs", cs_code)

    builder = GraphBuilder(uuid.uuid4(), uuid.uuid4(), "commit-sha")
    builder._build_git_graph = AsyncMock()
    await builder.build([pfile])

    cypher_calls = [call_args[0][0] for call_args in mock_session.run.call_args_list if call_args[0]]
    assert any("MERGE (m:Module" in q for q in cypher_calls)
    assert any("MERGE (c:Class" in q for q in cypher_calls)
    assert any("MERGE (func:Function" in q for q in cypher_calls)


def test_embedding_generator_extracts_csharp_semantic_units():
    """EmbeddingGenerator extracts semantic chunks from C# classes and methods."""
    cs_code = """
namespace MyApp.Services;

public class PaymentService
{
    public void Process()
    {
        // execute payment
    }
}
"""
    parser = CSharpParser()
    pfile = parser.parse_file("src/PaymentService.cs", cs_code)

    generator = EmbeddingGenerator(uuid.uuid4(), uuid.uuid4())
    units = generator._extract_semantic_units([pfile])

    assert len(units) >= 1
    assert any("MyApp.Services.PaymentService" in u.get("qualified_name", "") or "Process" in u.get("source_text", "") for u in units)


def test_cross_language_http_resolution_ts_to_aspnetcore():
    """Resolves TypeScript fetch / axios calls to ASP.NET Core controller and minimal API routes."""
    # 1. C# ASP.NET Core Backend
    cs_code = """
namespace MyApp.Controllers;

[ApiController]
[Route("api/[controller]")]
public class OrdersController : ControllerBase
{
    [HttpGet]
    public IActionResult GetOrders() => Ok();

    [HttpPost("create")]
    public IActionResult CreateOrder([FromBody] OrderRequest req) => Ok();
}

public class Program
{
    public static void Main(string[] args)
    {
        app.MapGet("/api/v1/health", () => "OK");
    }
}
"""
    cs_parser = CSharpParser()
    cs_pfile = cs_parser.parse_file("backend/Controllers/OrdersController.cs", cs_code)

    # 2. TypeScript Frontend
    ts_code = """
export async function fetchOrders(): Promise<void> {
    const res = await fetch("/api/orders");
}

export async function submitOrder(order: any): Promise<void> {
    await axios.post("/api/orders/create", order);
}

export async function checkHealth(): Promise<void> {
    await fetch("/api/v1/health");
}
"""
    ts_parser = TypeScriptParser()
    ts_pfile = ts_parser.parse_file("frontend/src/api/orders.ts", ts_code)

    file_contents = {
        "backend/Controllers/OrdersController.cs": cs_code,
        "frontend/src/api/orders.ts": ts_code
    }

    resolver = EndpointResolver()
    results = resolver.resolve([cs_pfile, ts_pfile], file_contents)

    # 3 endpoints matched -> 6 resolution results (3 REQUESTS + 3 HANDLED_BY)
    assert len(results) == 6

    req_results = [r for r in results if r.relationship == "REQUESTS"]
    assert len(req_results) == 3

    handled_results = [r for r in results if r.relationship == "HANDLED_BY"]
    assert len(handled_results) == 3

    # Check controller GET /api/orders
    get_orders_req = next(r for r in req_results if "endpoint:GET:/api/orders" == r.target_id)
    assert get_orders_req.source_id == f"{ts_pfile.module_name}.fetchOrders"
    assert get_orders_req.target_language == "csharp"

    get_orders_hby = next(r for r in handled_results if "endpoint:GET:/api/orders" == r.source_id)
    assert get_orders_hby.target_id == "MyApp.Controllers.OrdersController.GetOrders"
    assert get_orders_hby.target_language == "csharp"

    # Check minimal API GET /api/v1/health
    health_req = next(r for r in req_results if "endpoint:GET:/api/v1/health" == r.target_id)
    assert health_req.source_id == f"{ts_pfile.module_name}.checkHealth"

    health_hby = next(r for r in handled_results if "endpoint:GET:/api/v1/health" == r.source_id)
    assert "MapGet" in health_hby.target_id
    assert health_hby.target_language == "csharp"
