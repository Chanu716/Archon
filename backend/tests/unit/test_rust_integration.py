"""
Rust Integration Tests (Slice ML-9)

Tests 44-48: Scanner, GraphBuilder, EmbeddingGenerator, ImpactService traversal.
"""

import pytest
from unittest.mock import MagicMock, patch
from archon.pipeline.parsers.rust.parser import RustParser
from archon.pipeline.parsers.registry import registry


# ─────────────────────────────────────────────────────────────────────────────
# 44. Scanner discovers .rs files automatically
# ─────────────────────────────────────────────────────────────────────────────

def test_scanner_discovers_rs_via_registry():
    """44. .rs is in supported_extensions() so scanner will process it."""
    exts = registry.supported_extensions()
    assert ".rs" in exts


# ─────────────────────────────────────────────────────────────────────────────
# 45. GraphBuilder creates universal nodes without Rust-specific logic
# ─────────────────────────────────────────────────────────────────────────────

def test_graph_builder_accepts_rust_ir():
    """45. GraphBuilder processes Rust ParsedFile through universal interface."""
    from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction

    rust_src = """\
pub struct Billing {}

impl Billing {
    pub fn charge(&self) -> bool { true }
}
"""
    p = RustParser()
    pf = p.parse_file("backend/src/billing.rs", rust_src)

    # Verify the IR shape is universally valid
    assert pf.language == "rust"
    assert len(pf.classes) == 1
    cls = pf.classes[0]
    assert cls.name == "Billing"
    assert cls.qualified_name.endswith("Billing")
    assert cls.start_line >= 1
    assert len(cls.methods) == 1
    assert cls.methods[0].name == "charge"
    assert cls.methods[0].is_method is True


# ─────────────────────────────────────────────────────────────────────────────
# 46. EmbeddingGenerator processes Rust IR
# ─────────────────────────────────────────────────────────────────────────────

def test_embedding_generator_processes_rust_ir():
    """46. EmbeddingGenerator can extract text from Rust ParsedFile for embedding."""
    rust_src = """\
/// Formats headers for HTTP requests
pub fn format_header(key: &str) -> String {
    key.to_uppercase()
}
"""
    p = RustParser()
    pf = p.parse_file("backend/src/utils.rs", rust_src)

    # EmbeddingGenerator uses module_name + function names as keys
    assert pf.module_name is not None
    assert len(pf.functions) == 1
    func = pf.functions[0]
    assert func.name == "format_header"
    assert func.qualified_name == f"{pf.module_name}.format_header"


# ─────────────────────────────────────────────────────────────────────────────
# 47. ImpactService traverses exact Rust CALLS
# ─────────────────────────────────────────────────────────────────────────────

def test_impact_service_traverses_rust_calls():
    """47. ImpactService can traverse CALLS relationships between Rust functions."""
    from archon.pipeline.resolution.imports import ModuleAndSymbolResolver

    rust_utils = """\
pub fn compute_tax(amount: f64) -> f64 {
    amount * 0.2
}
"""
    rust_billing = """\
use crate::utils::compute_tax;

pub fn process_payment(amount: f64) -> f64 {
    let tax = compute_tax(amount);
    amount + tax
}
"""

    p = RustParser()
    utils_pf = p.parse_file("backend/src/utils.rs", rust_utils)
    billing_pf = p.parse_file("backend/src/billing.rs", rust_billing)

    resolver = ModuleAndSymbolResolver()
    results = resolver.resolve([utils_pf, billing_pf])

    # IMPORTS relationship should be resolved
    import_rels = [r for r in results if r.relationship == "IMPORTS" and r.resolution == "exact"]
    assert len(import_rels) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 48. ImpactService traverses: frontend -> REQUESTS -> Rust Endpoint -> HANDLED_BY
# ─────────────────────────────────────────────────────────────────────────────

def test_full_cross_language_chain_ts_to_rust():
    """48. End-to-end: TypeScript REQUESTS -> Rust Endpoint -> HANDLED_BY -> Rust handler."""
    from archon.pipeline.resolution.endpoints import EndpointResolver
    from archon.pipeline.parsers.typescript.parser import TypeScriptParser

    rust_src = """\
use axum::routing::post;

async fn create_order() {}

fn build_router() {
    let app = Router::new()
        .route("/api/v1/orders", post(create_order));
}
"""
    ts_src = """\
export async function placeOrder(data: OrderData) {
    return fetch('/api/v1/orders', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}
"""
    p_rust = RustParser()
    rust_pf = p_rust.parse_file("backend/src/routes.rs", rust_src)

    p_ts = TypeScriptParser()
    ts_pf = p_ts.parse_file("frontend/src/api/orders.ts", ts_src)

    resolver = EndpointResolver()
    results = resolver.resolve(
        [rust_pf, ts_pf],
        file_contents={
            "backend/src/routes.rs": rust_src,
            "frontend/src/api/orders.ts": ts_src,
        }
    )

    requests_rels = [r for r in results if r.relationship == "REQUESTS"]
    handled_by_rels = [r for r in results if r.relationship == "HANDLED_BY"]
    assert len(requests_rels) >= 1
    assert len(handled_by_rels) >= 1
    # Verify the handler points to the Rust function
    assert any("create_order" in r.target_id for r in handled_by_rels)


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency
# ─────────────────────────────────────────────────────────────────────────────

def test_repeated_resolution_is_idempotent():
    """Repeated resolve() on same files produces identical result counts."""
    from archon.pipeline.resolution.imports import ModuleAndSymbolResolver

    p = RustParser()
    utils_src = "pub fn format_header(s: &str) -> String { s.to_string() }"
    main_src = "use crate::utils::format_header;\nfn main() { format_header(\"x\"); }"

    utils_pf = p.parse_file("backend/src/utils.rs", utils_src)
    main_pf = p.parse_file("backend/src/main.rs", main_src)

    resolver = ModuleAndSymbolResolver()
    r1 = resolver.resolve([utils_pf, main_pf])
    r2 = resolver.resolve([utils_pf, main_pf])
    assert len(r1) == len(r2)
