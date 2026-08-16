from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from archon.models.base import Base

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # "github", "local"
    source_url = Column(String, nullable=False, index=True)
    managed_path = Column(String, nullable=False)
    detected_languages = Column(JSON, nullable=True)
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    last_analyzed_commit = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    jobs = relationship("AnalysisJob", back_populates="repository", cascade="all, delete-orphan")
    snapshots = relationship("AnalysisSnapshot", back_populates="repository", cascade="all, delete-orphan")

class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_job_id = Column(UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=False)
    commit_sha = Column(String, nullable=True)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    archon_version = Column(String, nullable=False)
    parser_version = Column(String, nullable=False)
    is_latest = Column(Boolean, default=True, nullable=False, index=True)

    repository = relationship("Repository", back_populates="snapshots")
    job = relationship("AnalysisJob", foreign_keys=[analysis_job_id])
