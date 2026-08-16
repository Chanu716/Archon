from sqlalchemy import Column, String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from archon.models.base import Base
import uuid

class EntityMetric(Base):
    __tablename__ = "entity_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("analysis_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Entity reference: Function, Class, Module, File, Repository
    entity_type = Column(String(50), nullable=False)
    entity_name = Column(String(500), nullable=False) # e.g., qualified_name or path
    
    # The metric itself
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    
    # Where did this metric come from? (deterministic, archon_heuristic_v1, etc.)
    metric_source = Column(String(50), nullable=False, index=True)
