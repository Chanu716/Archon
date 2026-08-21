"""
Archon Cross-Language Resolution Engine (Slice ML-4 / ML-10)
"""

from archon.pipeline.resolution.models import (
    ResolutionResult, ResolutionCandidate, ResolutionType, ResolutionConfidence
)
from archon.pipeline.resolution.base import BaseResolver
from archon.pipeline.resolution.imports import ModuleAndSymbolResolver, ModuleSymbolIndex
from archon.pipeline.resolution.type_index import RepositoryTypeIndex, TypeFact, DependencyFact, DIBindingFact
from archon.pipeline.resolution.dependency_extractor import DependencyExtractor
from archon.pipeline.resolution.dependency_resolver import DependencyAwareCallResolver
from archon.pipeline.resolution.endpoints import EndpointResolver, BackendRoute, FrontendHttpCall
from archon.pipeline.resolution.resolver import CrossLanguageResolver

__all__ = [
    "CrossLanguageResolver",
    "ModuleAndSymbolResolver",
    "ModuleSymbolIndex",
    "RepositoryTypeIndex",
    "TypeFact",
    "DependencyFact",
    "DIBindingFact",
    "DependencyExtractor",
    "DependencyAwareCallResolver",
    "EndpointResolver",
    "ResolutionResult",
    "ResolutionCandidate",
    "ResolutionType",
    "ResolutionConfidence",
    "BackendRoute",
    "FrontendHttpCall",
]
