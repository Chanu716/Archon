"""
Unit & Integration Tests for Cross-Language Resolution Engine (Slice ML-4)

Tests:
  1. Cross-Extension Module Resolution (TS -> JS, JS -> TS, .ts/.tsx/.js/.jsx/.mjs/.cjs/.py)
  2. Python Relative & Absolute Module Resolution
  3. Symbol Resolution & Call Upgrade to 'exact'
  4. API / HTTP Endpoint Cross-Language Resolution (FastAPI / Flask <-> fetch / axios)
  5. Ambiguity & Security: Path traversal protection, dynamic URL handling
  6. Idempotency & Snapshot Isolation
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from archon.pipeline.parsers.base import (
    ParsedFile, ParsedFunction, ParsedClass, ParsedImport, ResolvedCall
)
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.resolution.imports import ModuleAndSymbolResolver
from archon.pipeline.resolution.endpoints import EndpointResolver, _normalize_http_path, _normalize_param_path
from archon.pipeline.resolution.resolver import CrossLanguageResolver


# ---------------------------------------------------------------------------
# Section A: Cross-Extension Module Resolution
# ---------------------------------------------------------------------------

def test_ts_imports_js_module():
    """TypeScript file imports a JavaScript module extensionlessly."""
    ts_file = ParsedFile(
        path="src/app.ts",
        language="typescript",
        module_name="src/app",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="formatDate", alias=None, is_from_import=True, module="./utils")
        ]
    )

    js_file = ParsedFile(
        path="src/utils.js",
        language="javascript",
        module_name="src/utils",
        total_lines=15,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="formatDate",
                qualified_name="src/utils.formatDate",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=1,
                end_line=5,
                line_count=5,
                docstring=None
            )
        ],
        imports=[]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([ts_file, js_file])

    import_results = [r for r in results if r.relationship == "IMPORTS"]
    assert len(import_results) == 1
    res = import_results[0]
    assert res.source_id == "src/app"
    assert res.target_id == "src/utils"
    assert res.resolution == "exact"
    assert res.source_language == "typescript"
    assert res.target_language == "javascript"
    assert res.evidence_type == "relative_import"


def test_js_imports_ts_module():
    """JavaScript file imports a TypeScript module."""
    js_file = ParsedFile(
        path="frontend/main.js",
        language="javascript",
        module_name="frontend/main",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="ApiService", alias=None, is_from_import=True, module="./apiService")
        ]
    )

    ts_file = ParsedFile(
        path="frontend/apiService.ts",
        language="typescript",
        module_name="frontend/apiService",
        total_lines=20,
        docstring=None,
        classes=[
            ParsedClass(
                name="ApiService",
                qualified_name="frontend/apiService.ApiService",
                base_classes=[],
                methods=[],
                start_line=1,
                end_line=10,
                line_count=10,
                docstring=None
            )
        ],
        functions=[],
        imports=[]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([js_file, ts_file])

    import_results = [r for r in results if r.relationship == "IMPORTS"]
    assert len(import_results) == 1
    assert import_results[0].resolution == "exact"
    assert import_results[0].target_id == "frontend/apiService"


def test_directory_index_resolution():
    """Extensionless import resolves to directory index.tsx entrypoint."""
    importer = ParsedFile(
        path="src/App.tsx",
        language="typescript",
        module_name="src/App",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="Header", alias=None, is_from_import=True, module="./components/Header")
        ]
    )

    index_file = ParsedFile(
        path="src/components/Header/index.tsx",
        language="typescript",
        module_name="src/components/Header/index",
        total_lines=15,
        docstring=None,
        classes=[],
        functions=[],
        imports=[]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer, index_file])

    import_results = [r for r in results if r.relationship == "IMPORTS"]
    assert len(import_results) == 1
    assert import_results[0].target_file == "src/components/Header/index.tsx"


def test_ambiguous_extension_candidates_remain_unresolved():
    """When both .js and .ts exist for an extensionless import, do not guess."""
    importer = ParsedFile(
        path="src/index.js",
        language="javascript",
        module_name="src/index",
        total_lines=5,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="helper", alias=None, is_from_import=True, module="./helper")
        ]
    )

    js_helper = ParsedFile(path="src/helper.js", language="javascript", module_name="src/helper", total_lines=5, docstring=None, classes=[], functions=[], imports=[])
    ts_helper = ParsedFile(path="src/helper.ts", language="typescript", module_name="src/helper", total_lines=5, docstring=None, classes=[], functions=[], imports=[])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer, js_helper, ts_helper])

    # Ambiguous candidate -> no exact edge created
    import_results = [r for r in results if r.relationship == "IMPORTS"]
    assert len(import_results) == 0


def test_path_traversal_escape_prevented():
    """Attempts to escape repository root via ../../ are rejected."""
    importer = ParsedFile(
        path="src/api.js",
        language="javascript",
        module_name="src/api",
        total_lines=5,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="passwd", alias=None, is_from_import=True, module="../../etc/passwd")
        ]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer])
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Section B: Python Module Resolution
# ---------------------------------------------------------------------------

def test_python_relative_import_resolution():
    """from .utils import helper in Python package resolves uniquely."""
    importer = ParsedFile(
        path="services/auth.py",
        language="python",
        module_name="services.auth",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="hash_password", alias=None, is_from_import=True, module=".crypto")
        ]
    )

    crypto_file = ParsedFile(
        path="services/crypto.py",
        language="python",
        module_name="services.crypto",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="hash_password",
                qualified_name="services.crypto.hash_password",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=1,
                end_line=5,
                line_count=5,
                docstring=None
            )
        ],
        imports=[]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer, crypto_file])

    import_results = [r for r in results if r.relationship == "IMPORTS"]
    assert len(import_results) == 1
    assert import_results[0].target_id == "services.crypto"
    assert import_results[0].resolution == "exact"


def test_python_stdlib_and_third_party_remain_unresolved():
    """Standard library (os, sys) and third-party (requests) do not resolve to repo nodes."""
    importer = ParsedFile(
        path="main.py",
        language="python",
        module_name="main",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="os", alias=None, is_from_import=False, module="os"),
            ParsedImport(name="requests", alias=None, is_from_import=False, module="requests"),
            ParsedImport(name="join", alias=None, is_from_import=True, module="os.path")
        ]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer])
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Section C: Symbol Resolution & Call Upgrade
# ---------------------------------------------------------------------------

def test_symbol_resolution_upgrades_call_to_exact():
    """Imported symbol call in source function is upgraded to exact CALLS edge."""
    importer = ParsedFile(
        path="src/index.ts",
        language="typescript",
        module_name="src/index",
        total_lines=20,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="runPipeline",
                qualified_name="src/index.runPipeline",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=1,
                end_line=10,
                line_count=10,
                docstring=None,
                calls=[
                    ResolvedCall(raw_name="calcTotal", target_qualified_name=None, resolution="inferred")
                ]
            )
        ],
        imports=[
            ParsedImport(name="calculateTotal", alias="calcTotal", is_from_import=True, module="./billing")
        ]
    )

    billing = ParsedFile(
        path="src/billing.js",
        language="javascript",
        module_name="src/billing",
        total_lines=20,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="calculateTotal",
                qualified_name="src/billing.calculateTotal",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=1,
                end_line=10,
                line_count=10,
                docstring=None
            )
        ],
        imports=[]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer, billing])

    call_results = [r for r in results if r.relationship == "CALLS"]
    assert len(call_results) == 1
    assert call_results[0].source_id == "src/index.runPipeline"
    assert call_results[0].target_id == "src/billing.calculateTotal"
    assert call_results[0].resolution == "exact"
    assert call_results[0].evidence_type == "explicit_import_symbol"


def test_namespace_import_call_resolution():
    """import * as utils from './utils'; utils.log() is upgraded to exact."""
    importer = ParsedFile(
        path="src/service.ts",
        language="typescript",
        module_name="src/service",
        total_lines=15,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="execute",
                qualified_name="src/service.execute",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=1,
                end_line=5,
                line_count=5,
                docstring=None,
                calls=[
                    ResolvedCall(raw_name="log", target_qualified_name=None, resolution="unresolved")
                ]
            )
        ],
        imports=[
            ParsedImport(name="utils", alias="utils", is_from_import=False, module="./utils")
        ]
    )

    utils_file = ParsedFile(
        path="src/utils.js",
        language="javascript",
        module_name="src/utils",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="log",
                qualified_name="src/utils.log",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=1,
                end_line=5,
                line_count=5,
                docstring=None
            )
        ],
        imports=[]
    )

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([importer, utils_file])

    call_results = [r for r in results if r.relationship == "CALLS"]
    assert len(call_results) == 1
    assert call_results[0].target_id == "src/utils.log"
    assert call_results[0].resolution == "exact"


# ---------------------------------------------------------------------------
# Section D: API & HTTP Endpoint Resolution
# ---------------------------------------------------------------------------

def test_fastapi_and_fetch_endpoint_resolution():
    """FastAPI route @app.get('/users') matches frontend fetch('/users')."""
    py_code = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    return []
"""
    py_pfile = ParsedFile(
        path="backend/api.py",
        language="python",
        module_name="backend.api",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="list_users",
                qualified_name="backend.api.list_users",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=False,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=6,
                end_line=7,
                line_count=2,
                docstring=None
            )
        ],
        imports=[]
    )

    ts_code = """
export async function getUsers() {
    const res = await fetch('/users');
    return res.json();
}
"""
    ts_pfile = ParsedFile(
        path="frontend/src/api.ts",
        language="typescript",
        module_name="frontend/src/api",
        total_lines=5,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="getUsers",
                qualified_name="frontend/src/api.getUsers",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=True,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=2,
                end_line=5,
                line_count=4,
                docstring=None
            )
        ],
        imports=[]
    )

    resolver = EndpointResolver()
    file_contents = {
        "backend/api.py": py_code,
        "frontend/src/api.ts": ts_code
    }
    results = resolver.resolve([py_pfile, ts_pfile], file_contents)

    requests_edges = [r for r in results if r.relationship == "REQUESTS"]
    handled_edges = [r for r in results if r.relationship == "HANDLED_BY"]

    assert len(requests_edges) == 1
    assert len(handled_edges) == 1

    # Frontend Function -> Endpoint
    req = requests_edges[0]
    assert req.source_id == "frontend/src/api.getUsers"
    assert req.target_id == "endpoint:GET:/users"
    assert req.resolution == "exact"
    assert req.metadata["http_method"] == "GET"
    assert req.metadata["path"] == "/users"

    # Endpoint -> Backend Handler Function
    hnd = handled_edges[0]
    assert hnd.source_id == "endpoint:GET:/users"
    assert hnd.target_id == "backend.api.list_users"
    assert hnd.resolution == "exact"


def test_fastapi_router_prefix_and_axios_post():
    """FastAPI APIRouter(prefix='/api/v1') + @router.post('/payments') matches axios.post('/api/v1/payments')."""
    py_code = """
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

@router.post("/payments")
async def create_payment(data: dict):
    return {"status": "ok"}
"""
    py_pfile = ParsedFile(
        path="backend/routes/payments.py",
        language="python",
        module_name="backend.routes.payments",
        total_lines=10,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="create_payment",
                qualified_name="backend.routes.payments.create_payment",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=True,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=6,
                end_line=7,
                line_count=2,
                docstring=None
            )
        ],
        imports=[]
    )

    js_code = """
import axios from 'axios';

export const submitPayment = async (amount) => {
    return axios.post('/api/v1/payments', { amount });
};
"""
    js_pfile = ParsedFile(
        path="frontend/src/services/payment.js",
        language="javascript",
        module_name="frontend/src/services/payment",
        total_lines=6,
        docstring=None,
        classes=[],
        functions=[
            ParsedFunction(
                name="submitPayment",
                qualified_name="frontend/src/services/payment.submitPayment",
                parameters=[],
                decorators=[],
                return_annotation=None,
                is_method=False,
                is_async=True,
                cyclomatic_complexity=1,
                nesting_depth=0,
                start_line=4,
                end_line=6,
                line_count=3,
                docstring=None
            )
        ],
        imports=[]
    )

    resolver = EndpointResolver()
    file_contents = {
        "backend/routes/payments.py": py_code,
        "frontend/src/services/payment.js": js_code
    }
    results = resolver.resolve([py_pfile, js_pfile], file_contents)

    requests_edges = [r for r in results if r.relationship == "REQUESTS"]
    assert len(requests_edges) == 1
    assert requests_edges[0].target_id == "endpoint:POST:/api/v1/payments"
    assert requests_edges[0].resolution == "exact"


def test_flask_route_and_method_mismatch_does_not_resolve():
    """Flask route @app.route('/login', methods=['POST']) does not match fetch('/login') with GET."""
    py_code = """
@app.route("/login", methods=["POST"])
def handle_login():
    return "ok"
"""
    py_pfile = ParsedFile(
        path="server.py", language="python", module_name="server", total_lines=5,
        docstring=None, classes=[],
        functions=[
            ParsedFunction(name="handle_login", qualified_name="server.handle_login", parameters=[], decorators=[], return_annotation=None, is_method=False, is_async=False, cyclomatic_complexity=1, nesting_depth=0, start_line=2, end_line=3, line_count=2, docstring=None)
        ],
        imports=[]
    )

    js_code = """
function getLogin() {
    return fetch('/login'); // GET by default -> method mismatch!
}
"""
    js_pfile = ParsedFile(
        path="client.js", language="javascript", module_name="client", total_lines=4,
        docstring=None, classes=[],
        functions=[
            ParsedFunction(name="getLogin", qualified_name="client.getLogin", parameters=[], decorators=[], return_annotation=None, is_method=False, is_async=False, cyclomatic_complexity=1, nesting_depth=0, start_line=2, end_line=4, line_count=3, docstring=None)
        ],
        imports=[]
    )

    resolver = EndpointResolver()
    results = resolver.resolve([py_pfile, js_pfile], {"server.py": py_code, "client.js": js_code})
    assert len(results) == 0


def test_dynamic_url_does_not_resolve_exact():
    """Dynamic URLs with template expressions (`/users/${id}`) do not resolve exact."""
    py_code = """
@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {}
"""
    py_pfile = ParsedFile(path="api.py", language="python", module_name="api", total_lines=5, docstring=None, classes=[], functions=[ParsedFunction(name="get_user", qualified_name="api.get_user", parameters=[], decorators=[], return_annotation=None, is_method=False, is_async=False, cyclomatic_complexity=1, nesting_depth=0, start_line=2, end_line=3, line_count=2, docstring=None)], imports=[])

    ts_code = """
function loadUser(id) {
    return fetch(`/users/${id}`); // Dynamic URL!
}
"""
    ts_pfile = ParsedFile(path="client.ts", language="typescript", module_name="client", total_lines=4, docstring=None, classes=[], functions=[ParsedFunction(name="loadUser", qualified_name="client.loadUser", parameters=[], decorators=[], return_annotation=None, is_method=False, is_async=False, cyclomatic_complexity=1, nesting_depth=0, start_line=2, end_line=4, line_count=3, docstring=None)], imports=[])

    resolver = EndpointResolver()
    results = resolver.resolve([py_pfile, ts_pfile], {"api.py": py_code, "client.ts": ts_code})
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Section E: Idempotency & Snapshot Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_idempotency_and_snapshot_isolation():
    """
    Running CrossLanguageResolver against Neo4j:
      1. Correctly enforces snapshot_id on all queries
      2. Uses MERGE statements guaranteeing idempotency on reruns
    """
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    pfile = ParsedFile(
        path="src/main.ts",
        language="typescript",
        module_name="src/main",
        total_lines=5,
        docstring=None,
        classes=[],
        functions=[],
        imports=[
            ParsedImport(name="util", alias=None, is_from_import=True, module="./util")
        ]
    )

    util_file = ParsedFile(
        path="src/util.js",
        language="javascript",
        module_name="src/util",
        total_lines=5,
        docstring=None,
        classes=[],
        functions=[],
        imports=[]
    )

    resolver = CrossLanguageResolver(repo_id, snapshot_id)

    mock_session = AsyncMock()
    with patch("archon.pipeline.resolution.resolver.neo4j_driver") as mock_driver:
        mock_driver.session.return_value.__aenter__.return_value = mock_session

        # Run 1
        results1 = await resolver.resolve_and_persist([pfile, util_file], {})
        assert len(results1) == 1

        # Check Cypher parameter snapshot_id
        for call_args in mock_session.run.call_args_list:
            params = call_args[1]
            assert params.get("snapshot_id") == str(snapshot_id)
            assert params.get("repo_id") == str(repo_id)

        # Run 2 (Idempotency assertion)
        results2 = await resolver.resolve_and_persist([pfile, util_file], {})
        assert len(results2) == len(results1)
        assert results1[0].source_id == results2[0].source_id
        assert results1[0].target_id == results2[0].target_id
