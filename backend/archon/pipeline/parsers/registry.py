from typing import Dict, Optional
from archon.pipeline.parsers.base import LanguageParser
import structlog

logger = structlog.get_logger(__name__)

class ParserRegistry:
    def __init__(self):
        self._parsers: Dict[str, LanguageParser] = {}

    def register(self, parser: LanguageParser) -> None:
        for ext in parser.file_extensions:
            self._parsers[ext] = parser
            logger.debug("parser_registered", extension=ext, language=parser.language)

    def get_parser(self, extension: str) -> Optional[LanguageParser]:
        return self._parsers.get(extension)

# Global registry instance
registry = ParserRegistry()
