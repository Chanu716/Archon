"""
Integration Tests for Java Parser (Slice ML-5)

Verifies:
  1. Scanner automatically discovers .java files via registry.supported_extensions()
  2. GraphBuilder consumes Java ParsedFile without Java-specific pipeline branches
  3. EmbeddingGenerator extracts semantic units from Java ParsedFile
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from archon.pipeline.ingestion.scanner import scan_directory
from archon.pipeline.parsers.registry import registry
from archon.pipeline.parsers.java.parser import JavaParser
from archon.pipeline.graph.builder import GraphBuilder
from archon.pipeline.embeddings.generator import EmbeddingGenerator


def test_scanner_automatically_discovers_java(tmp_path: Path):
    """Scanner discovers .java files solely via registry.supported_extensions()."""
    assert ".java" in registry.supported_extensions()

    (tmp_path / "App.java").write_text("public class App {}", encoding="utf-8")
    (tmp_path / "service").mkdir()
    (tmp_path / "service" / "OrderService.java").write_text("package service; public class OrderService {}", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("hello", encoding="utf-8")

    discovered = scan_directory(tmp_path)
    discovered_posix = [str(p).replace("\\", "/") for p in discovered]

    assert any(p.endswith("App.java") for p in discovered_posix)
    assert any(p.endswith("service/OrderService.java") for p in discovered_posix)
    assert not any(p.endswith("ignored.txt") for p in discovered_posix)


@patch("archon.pipeline.graph.builder.neo4j_driver")
@patch("archon.pipeline.graph.builder.async_session_factory")
async def test_graph_builder_accepts_java_parsed_files(mock_db, mock_driver):
    """GraphBuilder creates Neo4j nodes from Java ParsedFile without Java-specific branches."""
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    java_code = """
package com.example.service;

import com.example.model.Order;

public class OrderService extends BaseService {
    public Order processOrder(Long id) {
        return null;
    }
}
"""
    parser = JavaParser()
    pfile = parser.parse_file("src/main/java/com/example/service/OrderService.java", java_code)

    builder = GraphBuilder(uuid.uuid4(), uuid.uuid4(), "commit-sha")
    builder._build_git_graph = AsyncMock()
    await builder.build([pfile])

    # Assert Cypher run calls were made for File, Module, Class, and Function
    cypher_calls = [call_args[0][0] for call_args in mock_session.run.call_args_list if call_args[0]]
    assert any("MERGE (m:Module" in q for q in cypher_calls)
    assert any("MERGE (c:Class" in q for q in cypher_calls)
    assert any("MERGE (func:Function" in q for q in cypher_calls)


def test_embedding_generator_extracts_java_semantic_units():
    """EmbeddingGenerator extracts semantic chunks from Java classes and methods."""
    java_code = """
package com.example.service;

public class OrderService {
    public void execute() {
        // do work
    }
}
"""
    parser = JavaParser()
    pfile = parser.parse_file("src/OrderService.java", java_code)

    generator = EmbeddingGenerator(uuid.uuid4(), uuid.uuid4())
    units = generator._extract_semantic_units([pfile])

    assert len(units) >= 1
    # Check that unit has Java module name
    assert any("com.example.service.OrderService" in u.get("qualified_name", "") or "execute" in u.get("source_text", "") for u in units)
