from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import select

from bi_governance_lab import db
from bi_governance_lab.models import (
    DataSource,
    GovernanceCheck,
    GovernanceResult,
    Permission,
    RefreshEvent,
    Report,
    SemanticModel,
    User,
    Workspace,
)

RANDOM_SEED = 20260710
NOW = datetime(2026, 7, 10, 9, 0, 0)

DEPARTMENTS = [
    "Finance",
    "Sales",
    "Marketing",
    "People Operations",
    "Supply Chain",
    "Customer Success",
    "Product",
    "Security",
]

REPORT_TOPICS = [
    "Executive KPI Scorecard",
    "Revenue Pulse",
    "Pipeline Quality",
    "Campaign Attribution",
    "Workforce Planning",
    "Inventory Risk",
    "Renewal Forecast",
    "Feature Adoption",
    "Incident Review",
    "Vendor Spend",
    "Margin Waterfall",
    "Regional Performance",
]


def seed() -> None:
    """Create deterministic fictional BI governance data if the database is empty."""
    db.create_tables()
    with db.SessionLocal() as session:
        if session.scalar(select(Workspace).limit(1)) is not None:
            return

        rng = random.Random(RANDOM_SEED)
        workspaces = _make_workspaces()
        users = _make_users(rng, workspaces)
        data_sources = _make_data_sources()
        semantic_models = _make_semantic_models(rng, data_sources)
        reports = _make_reports(rng, workspaces, semantic_models, users)
        checks = _make_governance_checks()

        session.add_all(
            [
                *workspaces,
                *users,
                *data_sources,
                *semantic_models,
                *reports,
                *checks,
            ]
        )
        session.flush()

        session.add_all(_make_refresh_events(rng, semantic_models))
        session.add_all(_make_permissions(rng, users, workspaces, reports))
        session.add_all(_make_governance_results(rng, reports, checks))
        session.commit()


def _make_workspaces() -> list[Workspace]:
    names = [
        "Executive Insights",
        "Finance Command Center",
        "Sales Field Analytics",
        "Marketing Growth Lab",
        "People Analytics",
        "Supply Chain Control Tower",
        "Customer Success Metrics",
        "Product Telemetry",
        "Security Operations",
        "Data Quality Sandbox",
        "Regional Leadership",
        "Procurement Analytics",
        "Revenue Operations",
        "Compliance Reporting",
        "Legacy Migration Holding",
    ]
    return [
        Workspace(
            name=name,
            description=None if index in {9, 14} else f"Fictional workspace for {name}.",
            is_active=index != 14,
        )
        for index, name in enumerate(names)
    ]


def _make_users(rng: random.Random, workspaces: list[Workspace]) -> list[User]:
    first_names = [
        "Avery",
        "Blair",
        "Casey",
        "Devon",
        "Emery",
        "Finley",
        "Gray",
        "Harper",
        "Indigo",
        "Jordan",
    ]
    last_names = ["Stone", "Rivera", "Chen", "Patel", "Brooks", "Nguyen", "Reed", "Kim"]
    users = []
    for index in range(40):
        first = first_names[index % len(first_names)]
        last = last_names[index % len(last_names)]
        role = "admin" if index in {0, 1, 2, 3, 4, 5} else rng.choice(["viewer", "member"])
        users.append(
            User(
                display_name=f"{first} {last}",
                email=f"{first}.{last}.{index:02d}@example.invalid".lower(),
                role=role,
                workspace=workspaces[index % len(workspaces)],
            )
        )
    return users


def _make_data_sources() -> list[DataSource]:
    sources = [
        ("Fictional Enterprise Warehouse", "snowflake", "warehouse/analytics_core"),
        ("Acme CRM Mirror", "postgres", "crm/reporting_replica"),
        ("Northwind Finance Ledger", "sql_server", "finance/general_ledger"),
        ("Contoso Campaign Lake", "s3", "marketing/campaign_curated"),
        ("People Systems Extract", "csv", "people/monthly_secure_drop"),
        ("Supply Chain Events", "kafka", "supply_chain/events_silver"),
        ("Support Case Mart", "bigquery", "customer_success/case_mart"),
        ("Product Telemetry Lake", "delta", "product/telemetry_gold"),
        ("Security Incident Vault", "sqlite", "security/local_lab_incidents"),
        ("Vendor Spend Share", "excel", "procurement/vendor_spend.xlsx"),
        ("Regional Targets Sheet", "google_sheets", "leadership/regional_targets"),
        ("Legacy BI Extract", "access", "legacy/migration_extract"),
    ]
    return [
        DataSource(name=name, source_type=source_type, connection_summary=summary)
        for name, source_type, summary in sources
    ]


def _make_semantic_models(
    rng: random.Random, data_sources: list[DataSource]
) -> list[SemanticModel]:
    models = []
    for index in range(25):
        source = data_sources[index % len(data_sources)]
        if index in {12, 13, 14, 15}:
            source = data_sources[0]
        models.append(
            SemanticModel(
                name=f"{DEPARTMENTS[index % len(DEPARTMENTS)]} Model {index + 1:02d}",
                description=None
                if index in {3, 8, 17}
                else f"Fictional semantic model for {DEPARTMENTS[index % len(DEPARTMENTS)]}.",
                data_source=source,
                certified=False if index in {2, 6, 11, 19} else rng.random() > 0.25,
            )
        )
    return models


def _make_reports(
    rng: random.Random,
    workspaces: list[Workspace],
    semantic_models: list[SemanticModel],
    users: list[User],
) -> list[Report]:
    reports = []
    stale_indexes = {4, 11, 18, 29, 42, 53}
    orphan_indexes = {7, 26, 48}
    missing_description_indexes = {2, 7, 19, 31, 44, 55}
    style_failure_indexes = {5, 16, 27, 38, 49}
    accessibility_failure_indexes = {6, 17, 28, 39, 50, 59}
    inactive_owner_indexes = {1, 14, 27, 40, 52}

    for index in range(60):
        last_viewed_at = NOW - timedelta(days=rng.randint(1, 60))
        if index in stale_indexes:
            last_viewed_at = NOW - timedelta(days=91 + index)

        reports.append(
            Report(
                name=f"{REPORT_TOPICS[index % len(REPORT_TOPICS)]} {index + 1:02d}",
                description=None
                if index in missing_description_indexes
                else f"Fictional BI report covering {REPORT_TOPICS[index % len(REPORT_TOPICS)]}.",
                owner=f"Former Owner {index % 12 + 1:02d}"
                if index in inactive_owner_indexes
                else users[index % len(users)].display_name,
                workspace=None if index in orphan_indexes else workspaces[index % len(workspaces)],
                semantic_model=semantic_models[index % len(semantic_models)],
                last_viewed_at=last_viewed_at,
                style_compliant=index not in style_failure_indexes,
                accessibility_compliant=index not in accessibility_failure_indexes,
            )
        )
    return reports


def _make_refresh_events(
    rng: random.Random, semantic_models: list[SemanticModel]
) -> list[RefreshEvent]:
    events = []
    failed_indexes = {0, 25, 50, 75, *range(23, 300, 23)}
    for index in range(300):
        started_at = NOW - timedelta(hours=index * 3)
        failed = index in failed_indexes
        events.append(
            RefreshEvent(
                semantic_model=semantic_models[index % len(semantic_models)],
                started_at=started_at,
                completed_at=started_at + timedelta(minutes=rng.randint(4, 45)),
                status="failed" if failed else "succeeded",
                message="Synthetic gateway timeout during refresh."
                if failed
                else "Synthetic refresh completed.",
            )
        )
    return events


def _make_permissions(
    rng: random.Random,
    users: list[User],
    workspaces: list[Workspace],
    reports: list[Report],
) -> list[Permission]:
    permissions = []

    for workspace in workspaces:
        permissions.append(
            Permission(
                user=users[workspaces.index(workspace) % len(users)],
                workspace=workspace,
                access_level="admin",
            )
        )
        for offset in range(2):
            permissions.append(
                Permission(
                    user=users[(workspaces.index(workspace) + offset + 9) % len(users)],
                    workspace=workspace,
                    access_level=rng.choice(["viewer", "member"]),
                )
            )

    for user in users[1:7]:
        permissions.append(Permission(user=user, workspace=workspaces[0], access_level="admin"))

    for index, report in enumerate(reports):
        for offset in range(2):
            permissions.append(
                Permission(
                    user=users[(index + offset) % len(users)],
                    report=report,
                    access_level=rng.choice(["viewer", "member"]),
                )
            )

    for user_index in range(6):
        for report in reports[user_index::6]:
            permissions.append(
                Permission(user=users[user_index], report=report, access_level="admin")
            )

    return permissions


def _make_governance_checks() -> list[GovernanceCheck]:
    return [
        GovernanceCheck(
            name="Report has description",
            category="style",
            description="Reports should include a useful business description.",
        ),
        GovernanceCheck(
            name="Style guide compliance",
            category="style",
            description="Reports should follow the fictional BI style guide.",
        ),
        GovernanceCheck(
            name="Accessible color contrast",
            category="accessibility",
            description="Report visuals should meet fictional color contrast requirements.",
        ),
        GovernanceCheck(
            name="Keyboard navigation",
            category="accessibility",
            description="Interactive report elements should be keyboard navigable.",
        ),
    ]


def _make_governance_results(
    rng: random.Random, reports: list[Report], checks: list[GovernanceCheck]
) -> list[GovernanceResult]:
    results = []
    for report in reports:
        for check in checks:
            passed = _result_passed(report, check)
            results.append(
                GovernanceResult(
                    report=report,
                    check=check,
                    passed=passed,
                    score=rng.randint(86, 100) if passed else rng.randint(35, 74),
                    details="Synthetic assessment passed."
                    if passed
                    else f"Synthetic {check.category} issue detected.",
                    evaluated_at=NOW,
                )
            )
    return results


def _result_passed(report: Report, check: GovernanceCheck) -> bool:
    if check.name == "Report has description":
        return report.description is not None
    if check.name == "Style guide compliance":
        return report.style_compliant
    return report.accessibility_compliant


def main() -> None:
    """Run the fictional seed-data command-line entry point."""
    seed()
    print("Seeded fictional BI Governance Lab data.")


if __name__ == "__main__":
    main()
