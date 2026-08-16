from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ResolvedCall:
    raw_name: str
    target_qualified_name: Optional[str]
    resolution: str  # "exact", "inferred", "unresolved"
    resolution_note: Optional[str] = None

@dataclass
class ParsedParameter:
    name: str
    type_annotation: Optional[str] = None

@dataclass
class ParsedFunction:
    name: str
    qualified_name: str
    parameters: List[ParsedParameter]
    decorators: List[str]
    return_annotation: Optional[str]
    is_method: bool
    is_async: bool
    cyclomatic_complexity: int
    nesting_depth: int
    line_count: int
    end_line: int
    docstring: Optional[str]
    calls: List[ResolvedCall] = field(default_factory=list)

@dataclass
class ParsedClass:
    name: str
    qualified_name: str
    base_classes: List[str]
    methods: List[ParsedFunction]
    line_count: int
    end_line: int
    docstring: Optional[str]

@dataclass
class ParsedImport:
    name: str
    alias: Optional[str]
    is_from_import: bool
    module: Optional[str]

@dataclass
class ParsedFile:
    path: str
    language: str
    total_lines: int
    docstring: Optional[str]
    classes: List[ParsedClass]
    functions: List[ParsedFunction]  # module-level functions
    imports: List[ParsedImport]
    parse_errors: List[str] = field(default_factory=list)

class LanguageParser(ABC):
    @property
    @abstractmethod
    def language(self) -> str:
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        pass

    @abstractmethod
    def parse_file(self, path: str, content: str) -> ParsedFile:
        """Parses source code into a ParsedFile. Must catch errors and put them in parse_errors."""
        pass
