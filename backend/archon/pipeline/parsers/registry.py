"""
Parser Registry — Language-Neutral Router (ML-1)

Maps file extensions to registered LanguageParser implementations.
The registry is the single source of truth for which files are parseable.

Usage:
    registry.register(PythonParser())
    parser = registry.get_parser(".py")       # -> PythonParser instance or None
    lang   = registry.detect_language(".py")  # -> "python" or None
    exts   = registry.supported_extensions()  # -> {".py", ...}
"""

from typing import Dict, Optional, Set
from archon.pipeline.parsers.base import LanguageParser
import structlog

logger = structlog.get_logger(__name__)


class ParserRegistry:
    """
    Deterministic, extension-keyed router for language parsers.

    Rules:
      - One parser per extension (last register wins; warn on override).
      - Returns None for unsupported extensions — never raises.
      - Consumers must treat None as a skip signal, not an error.
    """

    def __init__(self):
        self._parsers: Dict[str, LanguageParser] = {}

    def register(self, parser: LanguageParser) -> None:
        """Register a parser for all extensions it declares."""
        for ext in parser.file_extensions:
            if ext in self._parsers:
                existing = self._parsers[ext].language
                logger.warning(
                    "parser_override",
                    extension=ext,
                    previous_language=existing,
                    new_language=parser.language,
                )
            self._parsers[ext] = parser
            logger.debug("parser_registered", extension=ext, language=parser.language)

    def get_parser(self, extension: str) -> Optional[LanguageParser]:
        """
        Return the registered parser for a file extension, or None.

        Args:
            extension: File extension including leading dot (e.g., '.py', '.ts')

        Returns:
            LanguageParser if registered, None otherwise.
        """
        return self._parsers.get(extension)

    def detect_language(self, extension: str) -> Optional[str]:
        """
        Return the canonical language name for a file extension, or None.

        This is the language-detection entry point for consumers that need
        to know the language without invoking the parser.

        Args:
            extension: File extension including leading dot (e.g., '.py', '.ts')

        Returns:
            Language string (e.g., 'python', 'typescript'), or None if unsupported.
        """
        parser = self._parsers.get(extension)
        return parser.language if parser is not None else None

    def supported_extensions(self) -> Set[str]:
        """
        Return the set of all currently registered file extensions.

        Used by the scanner to determine which files are parseable without
        hardcoding extensions in scanning logic.
        """
        return set(self._parsers.keys())


# Global singleton registry — parsers self-register at import time.
registry = ParserRegistry()
