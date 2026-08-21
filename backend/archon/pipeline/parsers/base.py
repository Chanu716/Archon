"""
Universal Language-Neutral Parser Contract (ML-1)

This module defines the canonical intermediate representation (IR) that all
language parsers must produce. Consumers (GraphBuilder, EmbeddingGenerator, etc.)
MUST only depend on the types defined here — never on parser-specific internals.

Design rules:
  - Parsers discover structural facts. Resolvers discover relationships.
  - Every field must be computable without executing repository code.
  - All string representations must be language-neutral where possible.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# IR: Call Resolution
# ---------------------------------------------------------------------------

@dataclass
class ResolvedCall:
    """Represents a call site discovered within a function body."""
    raw_name: str
    target_qualified_name: Optional[str]
    resolution: str  # "exact" | "inferred" | "unresolved"
    resolution_note: Optional[str] = None


# ---------------------------------------------------------------------------
# IR: Parameters
# ---------------------------------------------------------------------------

@dataclass
class ParsedParameter:
    """A single parameter in a function or method signature."""
    name: str
    type_annotation: Optional[str] = None  # String representation, language-agnostic


# ---------------------------------------------------------------------------
# IR: Functions and Methods
# ---------------------------------------------------------------------------

@dataclass
class ParsedFunction:
    """
    Represents a function or method discovered in source code.

    Source range: start_line..end_line (1-indexed, inclusive).
    """
    name: str
    qualified_name: str
    parameters: List[ParsedParameter]
    decorators: List[str]
    return_annotation: Optional[str]
    is_method: bool
    is_async: bool
    cyclomatic_complexity: int
    nesting_depth: int
    start_line: int           # ML-1: explicit start line (1-indexed)
    end_line: int
    line_count: int
    docstring: Optional[str]
    calls: List[ResolvedCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IR: Classes
# ---------------------------------------------------------------------------

@dataclass
class ParsedClass:
    """
    Represents a class, struct, or equivalent type declaration.

    Source range: start_line..end_line (1-indexed, inclusive).
    """
    name: str
    qualified_name: str
    base_classes: List[str]   # Simple names; resolution is a Resolver concern
    methods: List[ParsedFunction]
    start_line: int           # ML-1: explicit start line (1-indexed)
    end_line: int
    line_count: int
    docstring: Optional[str]


# ---------------------------------------------------------------------------
# IR: Imports
# ---------------------------------------------------------------------------

@dataclass
class ParsedImport:
    """Represents a single import or using/require directive."""
    name: str
    alias: Optional[str]
    is_from_import: bool
    module: Optional[str]


# ---------------------------------------------------------------------------
# IR: File (Root of the IR Tree)
# ---------------------------------------------------------------------------

@dataclass
class ParsedFile:
    """
    The root of the parser IR tree for a single source file.

    `module_name` is the canonical, language-appropriate dotted name for the
    module or namespace this file defines. It is computed by the parser and
    must NOT be re-derived by consumers (e.g., by stripping file extensions).

    Consumers MUST use `pfile.module_name` instead of deriving names from
    `pfile.path`. If `module_name` is None, use `pfile.path` as a fallback.
    """
    path: str                            # Relative path from repository root
    language: str                        # Canonical language identifier (e.g., "python", "typescript")
    module_name: Optional[str]           # ML-1: canonical module/namespace name
    total_lines: int
    docstring: Optional[str]
    classes: List[ParsedClass]
    functions: List[ParsedFunction]      # Module-level functions only
    imports: List[ParsedImport]
    parse_errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IR: Skip Record (for unrecognized/unsupported files)
# ---------------------------------------------------------------------------

@dataclass
class SkipRecord:
    """
    Created when the scanner encounters a file that no registered parser
    can handle. Used for structured logging and diagnostics only.
    """
    path: str
    extension: str
    reason: str  # e.g., "unsupported_extension", "parse_error", "binary_file"


# ---------------------------------------------------------------------------
# Abstract Parser Contract
# ---------------------------------------------------------------------------

class LanguageParser(ABC):
    """
    Contract that every language parser implementation must satisfy.

    Implementation rules:
      1. `parse_file()` MUST never raise an exception. All errors go to
         `ParsedFile.parse_errors`.
      2. `parse_file()` MUST NOT execute any code from the repository.
      3. `parse_file()` MUST set `ParsedFile.module_name` to the canonical
         module/namespace name appropriate for the language.
      4. `parse_file()` MUST set `start_line` on all ParsedClass and
         ParsedFunction instances.
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Canonical language identifier (e.g., 'python', 'typescript')."""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """File extensions this parser handles (e.g., ['.py'], ['.ts', '.tsx'])."""
        pass

    @abstractmethod
    def parse_file(self, path: str, content: str) -> ParsedFile:
        """
        Parse the source code string into the universal IR.

        Args:
            path: Relative path from repository root (e.g., 'src/api/handler.py')
            content: Full source code as a string

        Returns:
            ParsedFile — always. Never raises. Errors go to parse_errors.
        """
        pass
