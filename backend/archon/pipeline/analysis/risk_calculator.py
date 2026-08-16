"""
Archon Risk Heuristic v1 — Risk Calculator

Computes the final composite risk score for each file, now that all three
required components are available:
  - normalized_complexity  (from Slice 2, function-level → averaged to file)
  - normalized_coupling    (from Slice 2, module-level)
  - normalized_churn       (from Slice 5, file-level — NEW)

Formula (Archon Risk Heuristic v1):
  risk_score = 0.40 × normalized_complexity
             + 0.30 × normalized_coupling
             + 0.30 × normalized_churn

Risk classification:
  0.00 – 0.30  → LOW
  0.30 – 0.60  → MODERATE
  0.60 – 0.80  → HIGH
  0.80 – 1.00  → CRITICAL

IMPORTANT semantics:
  This score is a deterministic engineering heuristic.
  It is NOT a probability of failure.
  It is NOT a code quality score.
  It is NOT a developer performance metric.
  It combines complexity, coupling, and historical churn as equal signals.

Churn inheritance:
  Git churn is a file-level metric.
  When computing risk for a Function or Class, the churn component is inherited
  from the containing file. This is explicitly documented and labeled in the output.
  We do NOT claim the function itself has "churn" — only its file does.

Metric source:
  - Input metrics (complexity, coupling, churn): metric_source = 'deterministic'
  - Risk score output:                           metric_source = 'archon_heuristic_v1'
"""
import uuid
from typing import Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from archon.config import settings
from archon.db.session import async_session_factory
from archon.models.metrics import EntityMetric
from archon.models.git import GitFileChurn

logger = structlog.get_logger(__name__)

# Risk thresholds
LOW_THRESHOLD      = settings.RISK_THRESHOLD_LOW       # 0.30
MODERATE_THRESHOLD = settings.RISK_THRESHOLD_MODERATE  # 0.60
HIGH_THRESHOLD     = settings.RISK_THRESHOLD_HIGH      # 0.80

# Risk weights (sum to 1.0)
W_COMPLEXITY = settings.RISK_WEIGHT_COMPLEXITY  # 0.40
W_COUPLING   = settings.RISK_WEIGHT_COUPLING    # 0.30
W_CHURN      = settings.RISK_WEIGHT_CHURN       # 0.30


def classify_risk(score: float) -> str:
    """Returns the risk classification label for a given score."""
    if score >= HIGH_THRESHOLD:
        return "CRITICAL"
    elif score >= MODERATE_THRESHOLD:
        return "HIGH"
    elif score >= LOW_THRESHOLD:
        return "MODERATE"
    return "LOW"


class RiskCalculator:
    """
    Calculates Archon Risk Heuristic v1 for all files in a snapshot.

    Reads:
      - normalized_complexity from entity_metrics (function-level, averaged per file)
      - normalized_coupling   from entity_metrics (module-level)
      - normalized_churn      from git_file_churn (file-level)

    Writes:
      - EntityMetric rows with metric_source = 'archon_heuristic_v1'
    """

    def __init__(self, snapshot_id: uuid.UUID):
        self.snapshot_id = snapshot_id

    async def calculate(self):
        """Run the full risk calculation pipeline."""
        async with async_session_factory() as db:
            complexity_by_file = await self._get_avg_complexity_by_file(db)
            coupling_by_module = await self._get_coupling_by_module(db)
            churn_by_file = await self._get_churn_by_file(db)

            # Collect all files/modules that have at least one signal
            all_paths = set(complexity_by_file) | set(churn_by_file)

            risk_metrics: List[EntityMetric] = []

            for file_path in all_paths:
                norm_complexity = complexity_by_file.get(file_path, 0.0)
                norm_churn      = churn_by_file.get(file_path, 0.0)
                # Use module coupling if available, otherwise 0.0
                # Match by file path prefix (simplified for MVP)
                module_key = file_path.replace("/", ".").replace(".py", "")
                norm_coupling = coupling_by_module.get(module_key, 0.0)

                risk_score = (
                    W_COMPLEXITY * norm_complexity
                    + W_COUPLING * norm_coupling
                    + W_CHURN    * norm_churn
                )

                label = classify_risk(risk_score)

                # Store risk score
                risk_metrics.append(EntityMetric(
                    snapshot_id=str(self.snapshot_id),
                    entity_type="File",
                    entity_name=file_path,
                    metric_name="risk_score",
                    metric_value=round(risk_score, 4),
                    metric_source="archon_heuristic_v1",
                ))
                # Store risk label as a separate metric for easy querying
                risk_metrics.append(EntityMetric(
                    snapshot_id=str(self.snapshot_id),
                    entity_type="File",
                    entity_name=file_path,
                    metric_name="risk_label",
                    # Encode label as float: LOW=0, MODERATE=1, HIGH=2, CRITICAL=3
                    metric_value=float({"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}[label]),
                    metric_source="archon_heuristic_v1",
                ))

            db.add_all(risk_metrics)
            await db.commit()

            logger.info(
                "risk_calculation_complete",
                snapshot_id=str(self.snapshot_id),
                files_scored=len(all_paths),
            )

    async def _get_avg_complexity_by_file(self, db: AsyncSession) -> Dict[str, float]:
        """
        Averages normalized_complexity across all functions in a file.
        Function-to-file mapping is done via entity_name prefix (module path).
        Returns {file_path: avg_normalized_complexity}
        """
        result = await db.execute(
            select(
                EntityMetric.entity_name,
                func.avg(EntityMetric.metric_value).label("avg_cc"),
            )
            .where(EntityMetric.snapshot_id == str(self.snapshot_id))
            .where(EntityMetric.metric_name == "normalized_complexity")
            .group_by(EntityMetric.entity_name)
        )
        rows = result.all()
        # entity_name is a qualified_name like "module.ClassName.method_name"
        # Map it to a file path by taking the first component as the module path
        # This is a simplified MVP heuristic — will be improved with explicit CONTAINS edges
        complexity: Dict[str, float] = {}
        for row in rows:
            qname = row.entity_name
            # e.g., "payment.service.process_payment" → "payment/service.py"
            parts = qname.split(".")
            if len(parts) >= 2:
                file_path = "/".join(parts[:-1]) + ".py"
                complexity[file_path] = max(complexity.get(file_path, 0.0), float(row.avg_cc))
        return complexity

    async def _get_coupling_by_module(self, db: AsyncSession) -> Dict[str, float]:
        """Returns {module_name: normalized_coupling}"""
        result = await db.execute(
            select(EntityMetric.entity_name, EntityMetric.metric_value)
            .where(EntityMetric.snapshot_id == str(self.snapshot_id))
            .where(EntityMetric.metric_name == "normalized_coupling")
        )
        return {row.entity_name: row.metric_value for row in result.all()}

    async def _get_churn_by_file(self, db: AsyncSession) -> Dict[str, float]:
        """Returns {file_path: normalized_churn}"""
        result = await db.execute(
            select(GitFileChurn.file_path, GitFileChurn.normalized_churn)
            .where(GitFileChurn.snapshot_id == self.snapshot_id)
        )
        return {row.file_path: row.normalized_churn for row in result.all()}
