class ArchonException(Exception):
    """Base exception for all Archon errors."""
    pass

class PathTraversalError(ArchonException):
    """Raised when an attempt is made to access a file outside the allowed repository boundary."""
    pass

class RepositoryNotFoundError(ArchonException):
    """Raised when a repository is not found."""
    pass

class JobExecutionError(ArchonException):
    """Raised when an analysis job fails fatally."""
    pass

class ParseError(ArchonException):
    """Raised when a file cannot be parsed."""
    pass
