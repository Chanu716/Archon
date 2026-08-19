from typing import List
import uuid
import structlog
from archon.db.neo4j import neo4j_driver
from archon.pipeline.parsers.base import ParsedFile, ParsedFunction
from archon.db.session import async_session_factory
from archon.models.git import GitCommit, GitFileChange
from sqlalchemy import select

logger = structlog.get_logger(__name__)

class GraphBuilder:
    def __init__(self, repository_id: uuid.UUID, snapshot_id: uuid.UUID, commit_sha: str):
        self.repository_id = str(repository_id)
        self.snapshot_id = str(snapshot_id)
        self.commit_sha = commit_sha

    async def build(self, parsed_files: List[ParsedFile]):
        async with neo4j_driver.session() as session:
            # 1. Create Repository Node
            await session.run(
                """
                MERGE (r:Repository {id: $repo_id})
                SET r.snapshot_id = $snapshot_id, r.commit_sha = $commit_sha
                """,
                repo_id=self.repository_id, snapshot_id=self.snapshot_id, commit_sha=self.commit_sha
            )
            
            for pfile in parsed_files:
                # 2. Create File Node
                await session.run(
                    """
                    MATCH (r:Repository {id: $repo_id})
                    MERGE (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    SET f.language = $language, f.total_lines = $lines, f.docstring = $docstring
                    MERGE (r)-[:CONTAINS]->(f)
                    """,
                    repo_id=self.repository_id, path=pfile.path, 
                    language=pfile.language, lines=pfile.total_lines, 
                    docstring=pfile.docstring, snapshot_id=self.snapshot_id
                )
                
                # 3. Create Module Node
                module_name = pfile.path.replace("/", ".").replace("\\", ".").replace(".py", "")
                if module_name.startswith("."):
                    module_name = module_name[1:]
                    
                await session.run(
                    """
                    MATCH (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (m:Module {qualified_name: $module, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (f)-[:DEFINES]->(m)
                    """,
                    repo_id=self.repository_id, path=pfile.path, module=module_name, snapshot_id=self.snapshot_id
                )
                
                # 4. Create Classes
                for cls in pfile.classes:
                    await session.run(
                        """
                        MATCH (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (c:Class {qualified_name: $qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        SET c.line_count = $lines, c.end_line = $end_line, c.docstring = $docstring
                        MERGE (f)-[:CONTAINS]->(c)
                        """,
                        repo_id=self.repository_id, path=pfile.path, qname=cls.qualified_name, 
                        lines=cls.line_count, end_line=cls.end_line, docstring=cls.docstring, 
                        snapshot_id=self.snapshot_id
                    )
                    
                    for base in cls.base_classes:
                        await session.run(
                            """
                            MATCH (c:Class {qualified_name: $qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                            MERGE (b:Class {qualified_name: $base, repository_id: $repo_id, snapshot_id: $snapshot_id})
                            MERGE (c)-[:INHERITS]->(b)
                            """,
                            repo_id=self.repository_id, qname=cls.qualified_name, base=base,
                            snapshot_id=self.snapshot_id
                        )
                        
                    # 5. Class Methods
                    for method in cls.methods:
                        await session.run(
                            """
                            MATCH (c:Class {qualified_name: $cqname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                            MERGE (func:Function {qualified_name: $qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                            SET func.cyclomatic_complexity = $cc, func.nesting_depth = $nd, func.is_method = true, 
                                func.line_count = $lines, func.end_line = $end_line, func.docstring = $docstring
                            MERGE (c)-[:CONTAINS]->(func)
                            """,
                            repo_id=self.repository_id, cqname=cls.qualified_name, qname=method.qualified_name,
                            cc=method.cyclomatic_complexity, nd=method.nesting_depth, lines=method.line_count, end_line=method.end_line,
                            docstring=method.docstring, snapshot_id=self.snapshot_id
                        )
                        await self._create_calls(session, method)
                        
                # 6. Module Functions
                for func in pfile.functions:
                    await session.run(
                        """
                        MATCH (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        MERGE (func:Function {qualified_name: $qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                        SET func.cyclomatic_complexity = $cc, func.nesting_depth = $nd, func.is_method = false, 
                            func.line_count = $lines, func.end_line = $end_line, func.docstring = $docstring
                        MERGE (f)-[:CONTAINS]->(func)
                        """,
                        repo_id=self.repository_id, path=pfile.path, qname=func.qualified_name,
                        cc=func.cyclomatic_complexity, nd=func.nesting_depth, lines=func.line_count, end_line=func.end_line,
                        docstring=func.docstring, snapshot_id=self.snapshot_id
                    )
                    await self._create_calls(session, func)
                    
                # 7. Imports
                for imp in pfile.imports:
                    if imp.module:
                        await session.run(
                            """
                            MATCH (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})-[:DEFINES]->(source_module:Module)
                            MERGE (target_module:Module {qualified_name: $module, repository_id: $repo_id, snapshot_id: $snapshot_id})
                            MERGE (source_module)-[:IMPORTS]->(target_module)
                            """,
                            repo_id=self.repository_id, path=pfile.path, module=imp.module,
                            snapshot_id=self.snapshot_id
                        )

            # 8. Git Intelligence (Developer -> Commit -> File)
            await self._build_git_graph(session)

    async def _build_git_graph(self, session):
        """Reads Git data from PostgreSQL and writes it to the Neo4j knowledge graph."""
        async with async_session_factory() as db:
            # 1. Fetch commits
            commits_res = await db.execute(
                select(GitCommit).where(GitCommit.snapshot_id == self.snapshot_id)
            )
            commits = commits_res.scalars().all()
            
            for commit in commits:
                # Merge Developer
                await session.run(
                    """
                    MERGE (d:Developer {email: $email, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    SET d.name = $name
                    """,
                    email=commit.author_email, name=commit.author_name,
                    repo_id=self.repository_id, snapshot_id=self.snapshot_id
                )
                
                # Merge Commit
                await session.run(
                    """
                    MATCH (d:Developer {email: $email, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (c:Commit {sha: $sha, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    SET c.message = $message, c.committed_at = $committed_at
                    MERGE (d)-[:AUTHORED]->(c)
                    """,
                    email=commit.author_email, sha=commit.commit_sha,
                    message=commit.message, committed_at=commit.committed_at.isoformat() if commit.committed_at else None,
                    repo_id=self.repository_id, snapshot_id=self.snapshot_id
                )
                
            # 2. Fetch File Changes
            changes_res = await db.execute(
                select(GitFileChange).where(GitFileChange.snapshot_id == self.snapshot_id)
            )
            changes = changes_res.scalars().all()
            
            for change in changes:
                # Link Commit to File
                await session.run(
                    """
                    MATCH (c:Commit {sha: $sha, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MATCH (f:File {path: $path, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (c)-[rel:CHANGED]->(f)
                    SET rel.type = $change_type, rel.insertions = $insertions, rel.deletions = $deletions
                    """,
                    sha=change.commit_sha, path=change.file_path,
                    change_type=change.change_type, insertions=change.insertions, deletions=change.deletions,
                    repo_id=self.repository_id, snapshot_id=self.snapshot_id
                )

    async def _create_calls(self, session, function: ParsedFunction):
        for call in function.calls:
            if call.resolution == "unresolved":
                await session.run(
                    """
                    MATCH (caller:Function {qualified_name: $caller_qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (target:UnresolvedCall {name: $target_name, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (caller)-[:CALLS {resolution: "unresolved"}]->(target)
                    """,
                    repo_id=self.repository_id, caller_qname=function.qualified_name, target_name=call.raw_name,
                    snapshot_id=self.snapshot_id
                )
            else:
                # Inferred or Exact
                await session.run(
                    """
                    MATCH (caller:Function {qualified_name: $caller_qname, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (target:Function {qualified_name: $target_name, repository_id: $repo_id, snapshot_id: $snapshot_id})
                    MERGE (caller)-[:CALLS {resolution: $resolution}]->(target)
                    """,
                    repo_id=self.repository_id, 
                    caller_qname=function.qualified_name, 
                    target_name=call.raw_name, # We use raw_name since we didn't fully resolve it
                    resolution=call.resolution,
                    snapshot_id=self.snapshot_id
                )
