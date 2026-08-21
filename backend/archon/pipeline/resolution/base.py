"""
Cross-Language Resolution Base Classes & Interfaces (ML-4)

Defines the abstract interface for specialized resolution strategies.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from archon.pipeline.parsers.base import ParsedFile
from archon.pipeline.resolution.models import ResolutionResult


class BaseResolver(ABC):
    """
    Abstract interface for a resolution strategy.
    
    Rules:
      - Deterministic evidence only. Never guess.
      - Never execute repository code.
      - Preserve snapshot isolation.
    """

    @abstractmethod
    def resolve(self, parsed_files: List[ParsedFile], file_contents: Optional[Dict[str, str]] = None) -> List[ResolutionResult]:
        """
        Analyze the parsed repository model and emit deterministic resolution results.
        
        Args:
            parsed_files: All ParsedFile instances in the repository snapshot.
            file_contents: Optional map of relative file path -> raw file content.
            
        Returns:
            List of ResolutionResult instances.
        """
        pass
