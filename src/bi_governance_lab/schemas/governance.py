from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from bi_governance_lab.models import GovernanceFinding
from bi_governance_lab.rules import RuleResult

logger = logging.getLogger(__name__)


class RuleResultRead(BaseModel):
    """Serializable API representation of a rule-engine result."""

    rule_id: str
    asset_id: int
    asset_type: str
    severity: str
    category: str
    finding: str
    recommendation: str
    evidence: dict[str, Any]

    @classmethod
    def from_rule_result(cls, result: RuleResult) -> RuleResultRead:
        """Create an API response model from an in-memory rule result."""
        return cls(**result.model_dump())


class FindingRead(RuleResultRead):
    """Serializable API representation of a persisted governance finding."""

    model_config = ConfigDict(from_attributes=True)

    evaluated_at: datetime

    @classmethod
    def from_orm_finding(cls, finding: GovernanceFinding) -> FindingRead:
        """Create an API response model from a persisted finding row."""
        try:
            evidence = json.loads(finding.evidence)
        except json.JSONDecodeError:
            logger.warning("Finding %s has invalid JSON evidence", finding.id)
            evidence = {"raw": finding.evidence}

        return cls(
            rule_id=finding.rule_id,
            asset_id=finding.asset_id,
            asset_type=finding.asset_type,
            severity=finding.severity,
            category=finding.category,
            finding=finding.finding,
            recommendation=finding.recommendation,
            evidence=evidence,
            evaluated_at=finding.evaluated_at,
        )
