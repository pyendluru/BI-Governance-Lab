from __future__ import annotations

import json
import logging
from argparse import ArgumentParser
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session, joinedload

from bi_governance_lab.models import (
    GovernanceCheck,
    GovernanceFinding,
    GovernanceResult,
    Permission,
    RefreshEvent,
    Report,
    SemanticModel,
    User,
    Workspace,
)
from bi_governance_lab.time import utc_now

logger = logging.getLogger(__name__)
RULE_IDS = {f"R{number:03d}" for number in range(1, 11)}


class RuleResult(BaseModel):
    """Normalized output produced by one governance rule for one asset."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    asset_id: int
    severity: str
    category: str
    finding: str
    recommendation: str
    evidence: dict[str, Any]
    asset_type: str

    def to_finding(self, evaluated_at: datetime) -> GovernanceFinding:
        """Convert this in-memory result to a persisted finding row."""
        return GovernanceFinding(
            rule_id=self.rule_id,
            asset_type=self.asset_type,
            asset_id=self.asset_id,
            severity=self.severity,
            category=self.category,
            finding=self.finding,
            recommendation=self.recommendation,
            evidence=json.dumps(self.evidence, sort_keys=True),
            evaluated_at=evaluated_at,
        )


def evaluate_rules(session: Session, as_of: datetime | None = None) -> list[RuleResult]:
    """Evaluate every governance rule and return non-persisted findings."""
    evaluation_time = as_of or utc_now()
    results: list[RuleResult] = []

    results.extend(_reports_without_active_owner(session))
    results.extend(_stale_reports(session, evaluation_time))
    results.extend(_models_with_high_refresh_failure_rate(session))
    results.extend(_models_not_refreshed_recently(session, evaluation_time))
    results.extend(_workspaces_with_too_many_admins(session))
    results.extend(_workspaces_with_too_few_admins(session))
    results.extend(_reports_missing_descriptions(session))
    results.extend(_reports_using_uncertified_models(session))
    results.extend(_low_category_scores(session, "accessibility", "R009", "high"))
    results.extend(_low_category_scores(session, "style", "R010", "medium"))

    return results


def run_rules(
    session: Session,
    as_of: datetime | None = None,
    replace_existing: bool = True,
) -> list[RuleResult]:
    """Evaluate governance rules and persist the resulting findings."""
    evaluation_time = as_of or utc_now()
    results = evaluate_rules(session, evaluation_time)

    if replace_existing:
        session.execute(delete(GovernanceFinding).where(GovernanceFinding.rule_id.in_(RULE_IDS)))

    session.add_all(result.to_finding(evaluation_time) for result in results)
    session.commit()
    logger.info("Stored %s governance findings", len(results))
    return results


def main() -> None:
    """Run the governance rules command-line entry point."""
    parser = ArgumentParser(description="Run BI Governance Lab rules.")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append findings instead of replacing existing rule-engine findings.",
    )
    args = parser.parse_args()

    from bi_governance_lab import db

    db.create_tables()
    with db.SessionLocal() as session:
        results = run_rules(session, replace_existing=not args.append)
    print(f"Stored {len(results)} governance findings.")


def _reports_without_active_owner(session: Session) -> list[RuleResult]:
    active_owners = {
        name.strip().casefold()
        for name in session.scalars(select(User.display_name))
        if name and name.strip()
    }
    findings = []
    for report in session.scalars(select(Report)).all():
        owner_key = report.owner.strip().casefold() if report.owner else ""
        if owner_key in active_owners:
            continue
        findings.append(
            RuleResult(
                rule_id="R001",
                asset_type="report",
                asset_id=report.id,
                severity="high",
                category="ownership",
                finding=f"Report '{report.name}' has no active owner.",
                recommendation="Assign ownership to an active BI user.",
                evidence={"owner": report.owner},
            )
        )
    return findings


def _stale_reports(session: Session, as_of: datetime) -> list[RuleResult]:
    cutoff = as_of - timedelta(days=90)
    findings = []
    for report in session.scalars(select(Report).where(Report.last_viewed_at < cutoff)).all():
        days_unused = (as_of - report.last_viewed_at).days if report.last_viewed_at else None
        findings.append(
            RuleResult(
                rule_id="R002",
                asset_type="report",
                asset_id=report.id,
                severity="medium",
                category="usage",
                finding=f"Report '{report.name}' has not been viewed in 90 days.",
                recommendation="Confirm whether the report is still needed or archive it.",
                evidence={
                    "last_viewed_at": report.last_viewed_at.isoformat()
                    if report.last_viewed_at
                    else None,
                    "days_unused": days_unused,
                },
            )
        )
    return findings


def _models_with_high_refresh_failure_rate(session: Session) -> list[RuleResult]:
    findings = []
    refresh_rows = session.execute(
        select(
            SemanticModel.id,
            SemanticModel.name,
            func.count(RefreshEvent.id),
            func.sum(case((RefreshEvent.status == "failed", 1), else_=0)),
        )
        .join(RefreshEvent)
        .group_by(SemanticModel.id, SemanticModel.name)
    )
    for model_id, model_name, total_count, failed_count in refresh_rows:
        failure_rate = failed_count / total_count
        if failure_rate <= 0.10:
            continue
        findings.append(
            RuleResult(
                rule_id="R003",
                asset_type="semantic_model",
                asset_id=model_id,
                severity="high",
                category="refresh",
                finding=f"Semantic model '{model_name}' refresh failure rate exceeds 10%.",
                recommendation="Investigate failing refresh jobs and upstream data dependencies.",
                evidence={
                    "failed_refreshes": failed_count,
                    "total_refreshes": total_count,
                    "failure_rate": round(failure_rate, 4),
                },
            )
        )
    return findings


def _models_not_refreshed_recently(session: Session, as_of: datetime) -> list[RuleResult]:
    cutoff = as_of - timedelta(hours=48)
    findings = []
    refresh_rows = session.execute(
        select(
            SemanticModel.id,
            SemanticModel.name,
            func.max(func.coalesce(RefreshEvent.completed_at, RefreshEvent.started_at)),
        )
        .outerjoin(RefreshEvent)
        .group_by(SemanticModel.id, SemanticModel.name)
    )
    for model_id, model_name, latest_refresh in refresh_rows:
        if latest_refresh is not None and latest_refresh >= cutoff:
            continue
        findings.append(
            RuleResult(
                rule_id="R004",
                asset_type="semantic_model",
                asset_id=model_id,
                severity="high",
                category="refresh",
                finding=f"Semantic model '{model_name}' has not refreshed in 48 hours.",
                recommendation="Restore the refresh schedule or document why it is paused.",
                evidence={
                    "last_refresh_at": latest_refresh.isoformat() if latest_refresh else None,
                    "threshold_hours": 48,
                },
            )
        )
    return findings


def _workspaces_with_too_many_admins(session: Session) -> list[RuleResult]:
    return _workspace_admin_findings(
        session=session,
        rule_id="R005",
        severity="high",
        predicate=lambda count: count > 5,
        finding_template="Workspace '{name}' has more than five administrators.",
        recommendation="Review workspace administrators and remove unnecessary admin access.",
    )


def _workspaces_with_too_few_admins(session: Session) -> list[RuleResult]:
    return _workspace_admin_findings(
        session=session,
        rule_id="R006",
        severity="medium",
        predicate=lambda count: count < 2,
        finding_template="Workspace '{name}' has fewer than two administrators.",
        recommendation="Assign at least two accountable workspace administrators.",
    )


def _workspace_admin_findings(
    session: Session,
    rule_id: str,
    severity: str,
    predicate: Callable[[int], bool],
    finding_template: str,
    recommendation: str,
) -> list[RuleResult]:
    admin_counts = defaultdict(int)
    admin_rows = session.execute(
        select(Permission.workspace_id, func.count(Permission.id))
        .where(Permission.access_level == "admin", Permission.workspace_id.is_not(None))
        .group_by(Permission.workspace_id)
    )
    for workspace_id, count in admin_rows:
        admin_counts[workspace_id] = count

    findings = []
    for workspace in session.scalars(select(Workspace)).all():
        admin_count = admin_counts[workspace.id]
        if not predicate(admin_count):
            continue
        findings.append(
            RuleResult(
                rule_id=rule_id,
                asset_type="workspace",
                asset_id=workspace.id,
                severity=severity,
                category="permissions",
                finding=finding_template.format(name=workspace.name),
                recommendation=recommendation,
                evidence={"admin_count": admin_count},
            )
        )
    return findings


def _reports_missing_descriptions(session: Session) -> list[RuleResult]:
    reports = session.scalars(
        select(Report).where((Report.description.is_(None)) | (Report.description == ""))
    ).all()
    return [
        RuleResult(
            rule_id="R007",
            asset_type="report",
            asset_id=report.id,
            severity="low",
            category="metadata",
            finding=f"Report '{report.name}' description is missing.",
            recommendation="Add a concise description that explains audience and purpose.",
            evidence={"description": report.description},
        )
        for report in reports
    ]


def _reports_using_uncertified_models(session: Session) -> list[RuleResult]:
    reports = session.scalars(
        select(Report)
        .join(SemanticModel)
        .options(joinedload(Report.semantic_model))
        .where(~SemanticModel.certified)
    ).all()
    return [
        RuleResult(
            rule_id="R008",
            asset_type="report",
            asset_id=report.id,
            severity="medium",
            category="certification",
            finding=f"Report '{report.name}' uses an uncertified semantic model.",
            recommendation="Certify the semantic model or move the report to a certified model.",
            evidence={
                "semantic_model_id": report.semantic_model.id,
                "semantic_model_name": report.semantic_model.name,
                "certified": report.semantic_model.certified,
            },
        )
        for report in reports
    ]


def _low_category_scores(
    session: Session, category: str, rule_id: str, severity: str
) -> list[RuleResult]:
    findings = []
    score_rows = session.execute(
        select(Report.id, Report.name, func.min(GovernanceResult.score))
        .join(GovernanceResult)
        .join(GovernanceCheck)
        .where(GovernanceCheck.category == category)
        .group_by(Report.id, Report.name)
    )
    for report_id, report_name, min_score in score_rows:
        if min_score >= 80:
            continue
        findings.append(
            RuleResult(
                rule_id=rule_id,
                asset_type="report",
                asset_id=report_id,
                severity=severity,
                category=category,
                finding=f"Report '{report_name}' {category} score is below 80.",
                recommendation=f"Remediate failed {category} checks and reassess the report.",
                evidence={
                    "min_score": min_score,
                    "threshold": 80,
                },
            )
        )
    return findings
