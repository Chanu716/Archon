"""
Integration Tests for JavaScript & JSX in Archon Pipeline (ML-3)

Tests:
  1. Scanner automatically discovers .js, .jsx, .mjs, .cjs files without modifying scanner.py
  2. GraphBuilder builds Neo4j entities from JavaScript ParsedFiles
  3. EmbeddingGenerator generates semantic units from JavaScript ParsedFiles
  4. Snapshot isolation is preserved for JavaScript graph nodes
"""

import pytest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import archon.pipeline.parsers.python.parser  # Ensure Python is registered
import archon.pipeline.parsers.typescript.parser  # Ensure TypeScript is registered
from archon.pipeline.parsers.javascript.parser import JavaScriptParser  # Ensure JavaScript is registered
from archon.pipeline.ingestion.scanner import scan_directory
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.embeddings.generator import EmbeddingGenerator
from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction, ParsedImport, ResolvedCall


def test_scanner_automatically_discovers_js_jsx_mjs_cjs(tmp_path):
    """
    Validates ML-1/ML-3 core architectural test:
    Registering JavaScriptParser automatically makes scan_directory discover
    .js, .jsx, .mjs, .cjs files without modifying a single line of scanner.py.
    """
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "index.js").write_text("const a = 1;", encoding="utf-8")
    (src_dir / "App.jsx").write_text("export function App() { return null; }", encoding="utf-8")
    (src_dir / "module.mjs").write_text("export const x = 10;", encoding="utf-8")
    (src_dir / "config.cjs").write_text("module.exports = {};", encoding="utf-8")
    (src_dir / "helper.py").write_text("def helper(): pass", encoding="utf-8")
    (src_dir / "component.tsx").write_text("export const C = () => null;", encoding="utf-8")
    (src_dir / "readme.md").write_text("# Readme", encoding="utf-8")
    (src_dir / "bundle.zip").write_bytes(b"PK\x03\x04")

    discovered = scan_directory(tmp_path)
    discovered_names = {f.name for f in discovered}

    assert "index.js" in discovered_names
    assert "App.jsx" in discovered_names
    assert "module.mjs" in discovered_names
    assert "config.cjs" in discovered_names
    assert "helper.py" in discovered_names
    assert "component.tsx" in discovered_names
    assert "readme.md" not in discovered_names
    assert "bundle.zip" not in discovered_names


@pytest.mark.asyncio
async def test_graph_builder_accepts_javascript_parsed_files():
    """
    Validates that GraphBuilder processes JavaScript ParsedFiles without any
    JavaScript-specific logic or modification to GraphBuilder.
    """
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    js_parser = JavaScriptParser()
    js_code = """
const BaseService = require('./base');

class PaymentService extends BaseService {
    process(amount) {
        this.log(amount);
        return true;
    }
    log(msg) {}
}

function createPayment() {
    new PaymentService().process(100);
}
"""
    pfile = js_parser.parse_file("src/services/payment.js", js_code)

    builder = GraphBuilder(repo_id, snapshot_id, "commit-sha-js-123")

    mock_session = AsyncMock()
    with patch("archon.pipeline.graph.builder.neo4j_driver") as mock_driver, \
         patch("archon.pipeline.graph.builder.async_session_factory") as mock_db_factory:

        mock_driver.session.return_value.__aenter__.return_value = mock_session
        mock_db = AsyncMock()
        mock_cursor = MagicMock()
        mock_cursor.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_cursor)
        mock_db_factory.return_value.__aenter__.return_value = mock_db

        await builder.build([pfile])

        # Verify queries were run
        assert mock_session.run.call_count > 0

        # Verify File node with language = 'javascript'
        file_calls = [c for c in mock_session.run.call_args_list if "MERGE (f:File" in c[0][0]]
        assert len(file_calls) == 1
        assert file_calls[0][1]["language"] == "javascript"
        assert file_calls[0][1]["path"] == "src/services/payment.js"
        assert file_calls[0][1]["snapshot_id"] == str(snapshot_id)

        # Verify Module node with canonical JavaScript module_name
        module_calls = [c for c in mock_session.run.call_args_list if "MERGE (m:Module" in c[0][0]]
        assert len(module_calls) >= 1
        assert module_calls[0][1]["module"] == "src/services/payment"
        assert module_calls[0][1]["snapshot_id"] == str(snapshot_id)

        # Verify Class node
        class_calls = [c for c in mock_session.run.call_args_list if "MERGE (c:Class" in c[0][0]]
        assert len(class_calls) >= 1
        assert class_calls[0][1]["qname"] == "src/services/payment.PaymentService"
        assert class_calls[0][1]["snapshot_id"] == str(snapshot_id)


def test_embedding_generator_extracts_javascript_semantic_units():
    """
    Validates that EmbeddingGenerator extracts semantic units from JavaScript
    ParsedFiles without any modification to the embedding generator.
    """
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    js_parser = JavaScriptParser()
    code = """
/**
 * User authentication service
 */
class AuthService {
    /**
     * Authenticate with token
     */
    login(token) {
        return true;
    }
}

const helperFunc = () => {};
"""
    pfile = js_parser.parse_file("src/auth.js", code)

    embedder = EmbeddingGenerator(repo_id, snapshot_id)
    units = embedder._extract_semantic_units([pfile])

    assert len(units) >= 3  # Module + Class + Method + Function

    unit_ids = {u["entity_id"] for u in units}
    assert "src/auth" in unit_ids
    assert "src/auth.AuthService" in unit_ids
    assert "src/auth.AuthService.login" in unit_ids
    assert "src/auth.helperFunc" in unit_ids
