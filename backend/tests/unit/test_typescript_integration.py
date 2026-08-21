"""
Integration Tests for TypeScript & TSX in Archon Pipeline (ML-2)

Tests:
  1. Scanner automatically discovers .ts and .tsx files without any changes to scanner.py
  2. GraphBuilder builds Neo4j entities from TypeScript ParsedFiles
  3. EmbeddingGenerator generates semantic units from TypeScript ParsedFiles
  4. Snapshot isolation is preserved for TypeScript graph nodes
"""

import pytest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import archon.pipeline.parsers.python.parser  # Ensure Python is registered
from archon.pipeline.parsers.typescript.parser import TypeScriptParser  # Ensure TypeScript is registered
from archon.pipeline.ingestion.scanner import scan_directory
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.embeddings.generator import EmbeddingGenerator
from archon.pipeline.parsers.base import ParsedFile, ParsedClass, ParsedFunction, ParsedImport, ResolvedCall


def test_scanner_automatically_discovers_ts_and_tsx(tmp_path):
    """
    Validates ML-1/ML-2 core architectural test:
    Registering TypeScriptParser automatically makes scan_directory discover
    .ts and .tsx files without modifying a single line of scanner.py.
    """
    # Create test directory structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    (src_dir / "index.ts").write_text("export const a = 1;", encoding="utf-8")
    (src_dir / "App.tsx").write_text("export function App() { return null; }", encoding="utf-8")
    (src_dir / "helper.py").write_text("def helper(): pass", encoding="utf-8")
    (src_dir / "readme.md").write_text("# Readme", encoding="utf-8")
    (src_dir / "image.png").write_bytes(b"\x89PNG")
    
    discovered = scan_directory(tmp_path)
    discovered_names = {f.name for f in discovered}
    
    assert "index.ts" in discovered_names
    assert "App.tsx" in discovered_names
    assert "helper.py" in discovered_names
    assert "readme.md" not in discovered_names
    assert "image.png" not in discovered_names


@pytest.mark.asyncio
async def test_graph_builder_accepts_typescript_parsed_files():
    """
    Validates that GraphBuilder processes TypeScript ParsedFiles without any
    TypeScript-specific logic or modification to GraphBuilder.
    """
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    
    ts_parser = TypeScriptParser()
    ts_code = """
import { BaseService } from './base';

export class OrderService extends BaseService {
    process(orderId: string): boolean {
        this.log(orderId);
        return true;
    }
    log(msg: string) {}
}

export function createOrder(): void {
    new OrderService().process("123");
}
"""
    pfile = ts_parser.parse_file("src/services/order.ts", ts_code)
    
    builder = GraphBuilder(repo_id, snapshot_id, "commit-sha-ts-123")
    
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
        
        # Verify File node with language = 'typescript'
        file_calls = [c for c in mock_session.run.call_args_list if "MERGE (f:File" in c[0][0]]
        assert len(file_calls) == 1
        assert file_calls[0][1]["language"] == "typescript"
        assert file_calls[0][1]["path"] == "src/services/order.ts"
        assert file_calls[0][1]["snapshot_id"] == str(snapshot_id)
        
        # Verify Module node with canonical TypeScript module_name
        module_calls = [c for c in mock_session.run.call_args_list if "MERGE (m:Module" in c[0][0]]
        assert len(module_calls) >= 1
        assert module_calls[0][1]["module"] == "src/services/order"
        assert module_calls[0][1]["snapshot_id"] == str(snapshot_id)
        
        # Verify Class node
        class_calls = [c for c in mock_session.run.call_args_list if "MERGE (c:Class" in c[0][0]]
        assert len(class_calls) >= 1
        assert class_calls[0][1]["qname"] == "src/services/order.OrderService"
        assert class_calls[0][1]["snapshot_id"] == str(snapshot_id)


def test_embedding_generator_extracts_typescript_semantic_units():
    """
    Validates that EmbeddingGenerator extracts semantic units from TypeScript
    ParsedFiles without any modification to the embedding generator.
    """
    repo_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    
    ts_parser = TypeScriptParser()
    code = """
/**
 * User authentication service
 */
export class AuthService {
    /**
     * Authenticate with token
     */
    login(token: string): boolean {
        return true;
    }
}

export const helperFunc = () => {};
"""
    pfile = ts_parser.parse_file("src/auth.ts", code)
    
    embedder = EmbeddingGenerator(repo_id, snapshot_id)
    units = embedder._extract_semantic_units([pfile])
    
    assert len(units) >= 3  # Module + Class + Method + Function
    
    unit_ids = {u["entity_id"] for u in units}
    assert "src/auth" in unit_ids
    assert "src/auth.AuthService" in unit_ids
    assert "src/auth.AuthService.login" in unit_ids
    assert "src/auth.helperFunc" in unit_ids
