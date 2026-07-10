import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from bi_governance_lab.db import get_session
from bi_governance_lab.models import GovernanceFinding
from bi_governance_lab.rules import run_rules
from bi_governance_lab.schemas import FindingRead, RuleResultRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/governance", tags=["governance"])


@router.post("/rules/run", response_model=list[RuleResultRead])
def run_governance_rules(session: Session = Depends(get_session)) -> list[RuleResultRead]:
    """Evaluate all governance rules and persist the resulting findings."""
    try:
        results = run_rules(session)
    except SQLAlchemyError as exc:
        logger.exception("Failed to run governance rules")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to run governance rules.",
        ) from exc
    return [RuleResultRead.from_rule_result(result) for result in results]


@router.get("/findings", response_model=list[FindingRead])
def list_governance_findings(
    rule_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[FindingRead]:
    """List persisted governance findings with optional filters and pagination."""
    statement = select(GovernanceFinding)
    if rule_id is not None:
        statement = statement.where(GovernanceFinding.rule_id == rule_id)
    if category is not None:
        statement = statement.where(GovernanceFinding.category == category)
    if severity is not None:
        statement = statement.where(GovernanceFinding.severity == severity)

    statement = (
        statement.order_by(GovernanceFinding.severity, GovernanceFinding.rule_id)
        .limit(limit)
        .offset(offset)
    )
    findings = session.scalars(statement).all()
    return [FindingRead.from_orm_finding(finding) for finding in findings]
