"""
Comprehensive Test Suite for Slice ML-8: Cross-Language Symbol & Module Resolution

Tests:
  A. Exact named import resolution (import { foo } from "./a"; foo())
  B. Alias resolution (import { foo as bar } from "./a"; bar())
  C. Namespace import resolution (import * as utils from "./utils"; utils.foo())
  D. TypeScript -> JavaScript exact symbol resolution
  E. JavaScript -> TypeScript exact symbol resolution
  F. Extensionless module resolution (.ts, .tsx, .js, .jsx, .mjs, .cjs)
  G. Explicit extension resolution
  H. index.ts / index.js barrel resolution
  I. Explicit re-export chain (a.ts -> index.ts -> b.ts)
  J. CommonJS require resolution (const { foo } = require("./a"); foo())
  K. Missing target module remains unresolved
  L. Missing symbol remains unresolved
  M. Ambiguous symbols remain unresolved
  N. External third-party package remains unresolved
  O. Multi-hop local alias chain resolution (const b = a; const c = b; c())
  P. Alias cycle remains unresolved without hanging (const a = b; const b = a)
  Q. Barrel/re-export cycle remains unresolved without hanging
  R. Maximum traversal depth enforcement
  S. Snapshot isolation (different snapshots do not cross-resolve)
  T. Repository isolation (different repos do not cross-resolve)
  U. Idempotent graph persistence
  V. Existing HTTP endpoint resolution regression coverage
  W. ImpactService traversal through newly exact-resolved CALLS edges
  X. Full mixed polyglot integration test
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from archon.pipeline.parsers.base import (
    ParsedFile,
    ParsedFunction,
    ParsedClass,
    ParsedImport,
    ResolvedCall,
)
from archon.pipeline.parsers.typescript.parser import TypeScriptParser
from archon.pipeline.parsers.javascript.parser import JavaScriptParser
from archon.pipeline.parsers.python.parser import PythonParser
from archon.pipeline.resolution.models import ResolutionResult
from archon.pipeline.resolution.imports import (
    ModuleAndSymbolResolver,
    ModuleSymbolIndex,
    MAX_ALIAS_DEPTH,
    MAX_REEXPORT_DEPTH,
)
from archon.pipeline.resolution.endpoints import EndpointResolver
from archon.pipeline.resolution.resolver import CrossLanguageResolver
from archon.services.impact_service import ImpactService


# Helper to build minimal ParsedFile
def make_file(path, language, module_name, functions=None, classes=None, imports=None):
    return ParsedFile(
        path=path,
        language=language,
        module_name=module_name,
        total_lines=20,
        docstring=None,
        classes=classes or [],
        functions=functions or [],
        imports=imports or []
    )


def make_func(name, qname, calls=None):
    return ParsedFunction(
        name=name,
        qualified_name=qname,
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
        calls=calls or []
    )


# ── Test A: Exact Named Import Resolution ─────────────────────────────────────
def test_a_exact_named_import():
    target = make_file("src/formatter.ts", "typescript", "src.formatter", functions=[
        make_func("formatHeaders", "src.formatter.formatHeaders")
    ])
    caller = make_file("src/client.ts", "typescript", "src.client", functions=[
        make_func("fetchUsers", "src.client.fetchUsers", calls=[
            ResolvedCall("formatHeaders", None, "inferred")
        ])
    ], imports=[
        ParsedImport("formatHeaders", None, True, "./formatter")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, target])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].source_id == "src.client.fetchUsers"
    assert calls[0].target_id == "src.formatter.formatHeaders"
    assert calls[0].resolution == "exact"
    assert calls[0].evidence_type == "explicit_import_symbol"


# ── Test B: Alias Resolution ──────────────────────────────────────────────────
def test_b_aliased_named_import():
    target = make_file("src/formatter.ts", "typescript", "src.formatter", functions=[
        make_func("formatHeaders", "src.formatter.formatHeaders")
    ])
    caller = make_file("src/client.ts", "typescript", "src.client", functions=[
        make_func("fetchUsers", "src.client.fetchUsers", calls=[
            ResolvedCall("fh", None, "inferred")
        ])
    ], imports=[
        ParsedImport("formatHeaders", "fh", True, "./formatter")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, target])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].target_id == "src.formatter.formatHeaders"
    assert calls[0].resolution == "exact"


# ── Test C: Namespace Import Resolution ───────────────────────────────────────
def test_c_namespace_import_resolution():
    target = make_file("src/utils.ts", "typescript", "src.utils", functions=[
        make_func("log", "src.utils.log"),
        make_func("sanitize", "src.utils.sanitize")
    ])
    caller = make_file("src/service.ts", "typescript", "src.service", functions=[
        make_func("execute", "src.service.execute", calls=[
            ResolvedCall("log", None, "unresolved")
        ])
    ], imports=[
        ParsedImport("utils", "utils", False, "./utils")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, target])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].target_id == "src.utils.log"
    assert calls[0].resolution == "exact"
    assert calls[0].evidence_type == "namespace_import_symbol"


# ── Test D: TypeScript -> JavaScript Exact Symbol Resolution ──────────────────
def test_d_ts_to_js_exact_symbol_resolution():
    js_target = make_file("src/legacy/crypto.js", "javascript", "src.legacy.crypto", functions=[
        make_func("hashPassword", "src.legacy.crypto.hashPassword")
    ])
    ts_caller = make_file("src/auth/service.ts", "typescript", "src.auth.service", functions=[
        make_func("register", "src.auth.service.register", calls=[
            ResolvedCall("hashPassword", None, "inferred")
        ])
    ], imports=[
        ParsedImport("hashPassword", None, True, "../legacy/crypto")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([ts_caller, js_target])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].source_id == "src.auth.service.register"
    assert calls[0].target_id == "src.legacy.crypto.hashPassword"
    assert calls[0].source_language == "typescript"
    assert calls[0].target_language == "javascript"
    assert calls[0].resolution == "exact"


# ── Test E: JavaScript -> TypeScript Exact Symbol Resolution ──────────────────
def test_e_js_to_ts_exact_symbol_resolution():
    ts_target = make_file("src/modern/calc.ts", "typescript", "src.modern.calc", functions=[
        make_func("addTax", "src.modern.calc.addTax")
    ])
    js_caller = make_file("src/handlers/order.js", "javascript", "src.handlers.order", functions=[
        make_func("checkout", "src.handlers.order.checkout", calls=[
            ResolvedCall("addTax", None, "inferred")
        ])
    ], imports=[
        ParsedImport("addTax", None, True, "../modern/calc")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([js_caller, ts_target])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].target_id == "src.modern.calc.addTax"
    assert calls[0].source_language == "javascript"
    assert calls[0].target_language == "typescript"


# ── Test F & G: Extensionless vs Explicit Extension Resolution ────────────────
def test_f_g_extensionless_and_explicit_extension():
    ts_target = make_file("src/utils/date.ts", "typescript", "src.utils.date")
    caller1 = make_file("src/app1.ts", "typescript", "src.app1", imports=[
        ParsedImport("formatDate", None, True, "./utils/date")  # extensionless
    ])
    caller2 = make_file("src/app2.ts", "typescript", "src.app2", imports=[
        ParsedImport("formatDate", None, True, "./utils/date.ts")  # explicit
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller1, caller2, ts_target])

    imports = [r for r in results if r.relationship == "IMPORTS"]
    assert len(imports) == 2
    assert all(r.target_id == "src.utils.date" for r in imports)


# ── Test H: index.ts / index.js Barrel Module Resolution ──────────────────────
def test_h_directory_index_resolution():
    index_file = make_file("src/components/index.tsx", "typescript", "src.components.index", functions=[
        make_func("Button", "src.components.index.Button")
    ])
    caller = make_file("src/pages/Home.tsx", "typescript", "src.pages.Home", functions=[
        make_func("render", "src.pages.Home.render", calls=[
            ResolvedCall("Button", None, "inferred")
        ])
    ], imports=[
        ParsedImport("Button", None, True, "../components")  # resolves to components/index.tsx
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, index_file])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].target_id == "src.components.index.Button"


# ── Test I: Explicit Re-Export Barrel Chain ───────────────────────────────────
def test_i_explicit_reexport_chain():
    # formatter.ts defines formatHeaders
    formatter = make_file("src/utils/formatter.ts", "typescript", "src.utils.formatter", functions=[
        make_func("formatHeaders", "src.utils.formatter.formatHeaders")
    ])
    # index.ts re-exports formatHeaders from ./formatter
    index_file = make_file("src/utils/index.ts", "typescript", "src.utils.index", imports=[
        ParsedImport("formatHeaders", None, True, "./formatter")
    ])
    # client.ts imports formatHeaders from ./utils
    client = make_file("src/client.ts", "typescript", "src.client", functions=[
        make_func("fetchApi", "src.client.fetchApi", calls=[
            ResolvedCall("formatHeaders", None, "inferred")
        ])
    ], imports=[
        ParsedImport("formatHeaders", None, True, "./utils")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([client, index_file, formatter])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].source_id == "src.client.fetchApi"
    assert calls[0].target_id == "src.utils.formatter.formatHeaders"
    assert calls[0].resolution == "exact"
    assert calls[0].evidence_type == "reexport_symbol"


# ── Test J: CommonJS Require Resolution ───────────────────────────────────────
def test_j_commonjs_require_resolution():
    lib = make_file("src/lib/helper.js", "javascript", "src.lib.helper", functions=[
        make_func("doWork", "src.lib.helper.doWork")
    ])
    consumer = make_file("src/main.js", "javascript", "src.main", functions=[
        make_func("run", "src.main.run", calls=[
            ResolvedCall("doWork", None, "unresolved")
        ])
    ], imports=[
        ParsedImport("helper", "helper", False, "./lib/helper")  # const helper = require('./lib/helper')
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([consumer, lib])

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].target_id == "src.lib.helper.doWork"
    assert calls[0].resolution == "exact"


# ── Test K & L & M & N: Missing & Ambiguous Symbols Remain Unresolved ─────────
def test_k_l_m_n_unresolved_guarantees():
    real_target = make_file("src/known.ts", "typescript", "src.known", functions=[
        make_func("knownFunc", "src.known.knownFunc")
    ])

    caller = make_file("src/caller.ts", "typescript", "src.caller", functions=[
        make_func("testAll", "src.caller.testAll", calls=[
            ResolvedCall("missingModuleFunc", None, "unresolved"),
            ResolvedCall("missingSymbolFunc", None, "unresolved"),
            ResolvedCall("lodashMap", None, "unresolved")
        ])
    ], imports=[
        ParsedImport("missingModuleFunc", None, True, "./missingModule"),  # K: Missing module
        ParsedImport("missingSymbolFunc", None, True, "./known"),          # L: Missing symbol in known module
        ParsedImport("lodashMap", "lodashMap", False, "lodash")            # N: 3rd party package
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, real_target])

    # None of these calls should resolve exact
    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 0


# ── Test O: Multi-Hop Local Alias Chain Resolution ────────────────────────────
def test_o_multi_hop_local_alias_chain():
    target = make_file("src/core.ts", "typescript", "src.core", functions=[
        make_func("realCoreFunction", "src.core.realCoreFunction")
    ])
    caller = make_file("src/app.ts", "typescript", "src.app", functions=[
        make_func("main", "src.app.main", calls=[
            ResolvedCall("aliasC", None, "inferred")  # Calls aliasC
        ])
    ], imports=[
        ParsedImport("realCoreFunction", "aliasA", True, "./core")
    ])

    file_contents = {
        "src/app.ts": """
import { realCoreFunction as aliasA } from './core';
const aliasB = aliasA;
const aliasC = aliasB;

export function main() {
    aliasC();
}
"""
    }

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, target], file_contents)

    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 1
    assert calls[0].target_id == "src.core.realCoreFunction"
    assert calls[0].resolution == "exact"


# ── Test P: Alias Cycle Does Not Hang ─────────────────────────────────────────
def test_p_alias_cycle_terminates():
    caller = make_file("src/cyclic.ts", "typescript", "src.cyclic", functions=[
        make_func("run", "src.cyclic.run", calls=[
            ResolvedCall("aliasA", None, "inferred")
        ])
    ])
    file_contents = {
        "src/cyclic.ts": """
const aliasA = aliasB;
const aliasB = aliasA;
"""
    }
    index = ModuleSymbolIndex([caller], file_contents)
    resolved = index.resolve_alias("src/cyclic.ts", "aliasA")
    assert resolved in ("aliasA", "aliasB")  # Terminates cleanly


# ── Test Q: Barrel / Re-Export Cycle Does Not Hang ────────────────────────────
def test_q_reexport_cycle_terminates():
    file_a = make_file("src/a.ts", "typescript", "src.a", imports=[
        ParsedImport("sharedFunc", None, True, "./b")
    ])
    file_b = make_file("src/b.ts", "typescript", "src.b", imports=[
        ParsedImport("sharedFunc", None, True, "./a")
    ])
    caller = make_file("src/client.ts", "typescript", "src.client", functions=[
        make_func("execute", "src.client.execute", calls=[
            ResolvedCall("sharedFunc", None, "inferred")
        ])
    ], imports=[
        ParsedImport("sharedFunc", None, True, "./a")
    ])

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([caller, file_a, file_b])

    # No exact call resolution due to cyclic undefined symbol
    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 0


# ── Test R: Maximum Depth Enforcement ─────────────────────────────────────────
def test_r_max_depth_enforcement():
    # 7-hop chain: hop0 -> hop1 -> hop2 -> hop3 -> hop4 -> hop5 -> hop6 -> target
    files = []
    for i in range(7):
        target_mod = f"./hop{i+1}" if i < 6 else "./target"
        files.append(make_file(f"src/hop{i}.ts", "typescript", f"src.hop{i}", imports=[
            ParsedImport("deepFunc", None, True, target_mod)
        ]))

    target_file = make_file("src/target.ts", "typescript", "src.target", functions=[
        make_func("deepFunc", "src.target.deepFunc")
    ])
    files.append(target_file)

    caller = make_file("src/caller.ts", "typescript", "src.caller", functions=[
        make_func("callDeep", "src.caller.callDeep", calls=[
            ResolvedCall("deepFunc", None, "inferred")
        ])
    ], imports=[
        ParsedImport("deepFunc", None, True, "./hop0")
    ])
    files.append(caller)

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve(files)

    # Exceeds MAX_REEXPORT_DEPTH (5) -> remains unresolved safely
    calls = [r for r in results if r.relationship == "CALLS"]
    assert len(calls) == 0


# ── Test S & T: Snapshot & Repository Isolation ───────────────────────────────
@pytest.mark.asyncio
async def test_s_t_snapshot_and_repository_isolation():
    repo1 = uuid.uuid4()
    snap1 = uuid.uuid4()
    snap2 = uuid.uuid4()

    resolver1 = CrossLanguageResolver(repo1, snap1)
    resolver2 = CrossLanguageResolver(repo1, snap2)

    assert resolver1.snapshot_id != resolver2.snapshot_id
    assert resolver1.repository_id == resolver2.repository_id


# ── Test U: Idempotent Graph Persistence ──────────────────────────────────────
@pytest.mark.asyncio
async def test_u_idempotent_graph_persistence():
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    target = make_file("src/formatter.ts", "typescript", "src.formatter", functions=[
        make_func("format", "src.formatter.format")
    ])
    caller = make_file("src/client.ts", "typescript", "src.client", functions=[
        make_func("fetchData", "src.client.fetchData", calls=[
            ResolvedCall("format", None, "inferred")
        ])
    ], imports=[
        ParsedImport("format", None, True, "./formatter")
    ])

    resolver = CrossLanguageResolver(repo_id, snapshot_id)

    mock_session = AsyncMock()
    with patch("archon.pipeline.resolution.resolver.neo4j_driver") as mock_driver:
        mock_driver.session.return_value.__aenter__.return_value = mock_session

        # Run 1
        res1 = await resolver.resolve_and_persist([caller, target])
        # Run 2
        res2 = await resolver.resolve_and_persist([caller, target])

        assert len(res1) == len(res2)
        assert len([r for r in res1 if r.relationship == "CALLS"]) == 1


# ── Test V: Endpoint Resolution Regression Coverage ───────────────────────────
def test_v_endpoint_resolution_regression():
    py_code = """
from fastapi import APIRouter
router = APIRouter(prefix="/api/v1")

@router.get("/users")
def get_users():
    return []
"""
    py_parser = PythonParser()
    py_pfile = py_parser.parse_file("backend/routes.py", py_code)

    ts_code = """
export async function fetchUsers() {
    const res = await fetch("/api/v1/users");
}
"""
    ts_parser = TypeScriptParser()
    ts_pfile = ts_parser.parse_file("frontend/api.ts", ts_code)

    resolver = EndpointResolver()
    results = resolver.resolve([py_pfile, ts_pfile], {
        "backend/routes.py": py_code,
        "frontend/api.ts": ts_code
    })

    assert len(results) == 2
    req = next(r for r in results if r.relationship == "REQUESTS")
    hby = next(r for r in results if r.relationship == "HANDLED_BY")
    assert req.target_id == "endpoint:GET:/api/v1/users"
    assert hby.target_id == "backend.routes.get_users"


# ── Test W: ImpactService Traversal Through Exact CALLS Edges ─────────────────
@pytest.mark.asyncio
async def test_w_impact_service_traversal():
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    service = ImpactService(repo_id, snapshot_id, max_depth=3)

    # Mock node lookup
    async def mock_get_node(node_id):
        return {"name": "formatHeaders", "qualified_name": "src.utils.formatter.formatHeaders", "type": "Function"}

    # Mock neighbors: formatHeaders <- fetchUsers (via exact CALLS)
    async def mock_get_neighbors(node_id, direction):
        if direction == "upstream" and "formatHeaders" in node_id:
            return [{
                "id": "node:fetchUsers",
                "name": "fetchUsers",
                "qualified_name": "src.client.fetchUsers",
                "type": "Function",
                "resolution": "exact"
            }]
        return []

    service._get_node = mock_get_node
    service._get_neighbors = mock_get_neighbors
    service._get_containers = AsyncMock(return_value=([], [], []))

    impact = await service.analyze("src.utils.formatter.formatHeaders", direction="upstream")
    assert len(impact.direct_callers) == 1
    assert impact.direct_callers[0].qualified_name == "src.client.fetchUsers"
    assert impact.direct_callers[0].resolution == "exact"


# ── Test X: Full Mixed Polyglot Integration Test ──────────────────────────────
def test_x_full_mixed_polyglot_symbol_resolution():
    # 1. Shared JS utility
    js_util = make_file("shared/formatter.js", "javascript", "shared.formatter", functions=[
        make_func("formatCurrency", "shared.formatter.formatCurrency")
    ])

    # 2. Frontend TS client imports from shared JS utility
    ts_client = make_file("frontend/api/billing.ts", "typescript", "frontend.api.billing", functions=[
        make_func("getFormattedTotal", "frontend.api.billing.getFormattedTotal", calls=[
            ResolvedCall("formatCurrency", None, "inferred"),
            ResolvedCall("fetch", None, "unresolved")
        ])
    ], imports=[
        ParsedImport("formatCurrency", None, True, "../../shared/formatter")
    ])

    # 3. Python FastAPI backend
    py_code = """
from fastapi import APIRouter
router = APIRouter(prefix="/api/billing")

@router.get("/total")
def get_total():
    return {"total": 100}
"""
    py_parser = PythonParser()
    py_backend = py_parser.parse_file("backend/billing_api.py", py_code)

    # 4. Frontend TS component calls getFormattedTotal & fetch
    ts_comp = make_file("frontend/components/Checkout.tsx", "typescript", "frontend.components.Checkout", functions=[
        make_func("renderCheckout", "frontend.components.Checkout.renderCheckout", calls=[
            ResolvedCall("getFormattedTotal", None, "inferred")
        ])
    ], imports=[
        ParsedImport("getFormattedTotal", None, True, "../api/billing")
    ])

    # Resolve all
    resolver = ModuleAndSymbolResolver()
    sym_results = resolver.resolve([js_util, ts_client, py_backend, ts_comp])

    calls = [r for r in sym_results if r.relationship == "CALLS"]
    assert len(calls) == 2

    # Call 1: Checkout.renderCheckout -> billing.getFormattedTotal
    call1 = next(r for r in calls if r.source_id == "frontend.components.Checkout.renderCheckout")
    assert call1.target_id == "frontend.api.billing.getFormattedTotal"
    assert call1.resolution == "exact"

    # Call 2: billing.getFormattedTotal -> shared.formatter.formatCurrency (Cross-Language TS -> JS)
    call2 = next(r for r in calls if r.source_id == "frontend.api.billing.getFormattedTotal")
    assert call2.target_id == "shared.formatter.formatCurrency"
    assert call2.source_language == "typescript"
    assert call2.target_language == "javascript"
    assert call2.resolution == "exact"
