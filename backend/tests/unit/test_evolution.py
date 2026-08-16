import pytest
import uuid
from datetime import datetime, timezone
from archon.models.evolution import SnapshotMetadata, SnapshotComparison, EntityLifecycleState, MetricDelta, MetricTrend
from archon.services.evolution_service import EvolutionService

@pytest.mark.asyncio
async def test_metric_trend_logic():
    # Test the private method for metric trend calculation
    service = EvolutionService(db=None) # type: ignore
    
    assert await service._calculate_trend([10.0, 15.0, 20.0]) == MetricTrend.INCREASING
    assert await service._calculate_trend([20.0, 15.0, 10.0]) == MetricTrend.DECREASING
    assert await service._calculate_trend([10.0, 10.0, 10.0]) == MetricTrend.STABLE
    assert await service._calculate_trend([10.0, 15.0, 12.0, 18.0]) == MetricTrend.VOLATILE
    assert await service._calculate_trend([10.0]) == MetricTrend.UNKNOWN

from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_compare_snapshots_validation():
    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db_mock.execute.return_value = result_mock
    
    service = EvolutionService(db=db_mock)
    repo_id = uuid.uuid4()
    
    with pytest.raises(ValueError, match="Snapshots not found or do not belong to the given repository"):
        await service.compare_snapshots(repo_id, uuid.uuid4(), uuid.uuid4())
