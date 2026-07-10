import json
from datetime import timedelta

from sqlalchemy import func, select

from bi_governance_lab.models import (
    DataSource,
    GovernanceFinding,
    RefreshEvent,
    Report,
    SemanticModel,
    User,
    Workspace,
)
from bi_governance_lab.rules import evaluate_rules, run_rules
from bi_governance_lab.seed import NOW, seed

EXPECTED_RULE_IDS = {f"R{number:03d}" for number in range(1, 11)}


def test_evaluate_rules_returns_all_expected_rule_types(configured_temp_db):
    seed()

    import bi_governance_lab.db as db

    with db.SessionLocal() as session:
        results = evaluate_rules(session, as_of=NOW)

    assert EXPECTED_RULE_IDS <= {result.rule_id for result in results}
    assert all(result.asset_id for result in results)
    assert all(result.severity for result in results)
    assert all(result.category for result in results)
    assert all(result.finding for result in results)
    assert all(result.recommendation for result in results)
    assert all(result.evidence for result in results)


def test_rule_results_include_expected_evidence(configured_temp_db):
    seed()

    import bi_governance_lab.db as db

    with db.SessionLocal() as session:
        results = evaluate_rules(session, as_of=NOW)

    by_rule = {rule_id: [] for rule_id in EXPECTED_RULE_IDS}
    for result in results:
        by_rule[result.rule_id].append(result)

    assert any(result.evidence["owner"].startswith("Former Owner") for result in by_rule["R001"])
    assert all(result.evidence["days_unused"] > 90 for result in by_rule["R002"])
    assert any(result.evidence["failure_rate"] > 0.10 for result in by_rule["R003"])
    assert all(result.evidence["threshold_hours"] == 48 for result in by_rule["R004"])
    assert all(result.evidence["admin_count"] > 5 for result in by_rule["R005"])
    assert all(result.evidence["admin_count"] < 2 for result in by_rule["R006"])
    assert all(result.evidence["description"] is None for result in by_rule["R007"])
    assert all(result.evidence["certified"] is False for result in by_rule["R008"])
    assert all(result.evidence["min_score"] < 80 for result in by_rule["R009"])
    assert all(result.evidence["min_score"] < 80 for result in by_rule["R010"])


def test_run_rules_stores_findings_and_replaces_previous_results(configured_temp_db):
    seed()

    import bi_governance_lab.db as db

    with db.SessionLocal() as session:
        results = run_rules(session, as_of=NOW)
        stored_count = session.scalar(select(func.count()).select_from(GovernanceFinding))
        assert stored_count == len(results)

        stored = session.scalar(select(GovernanceFinding).limit(1))
        assert stored.rule_id in EXPECTED_RULE_IDS
        assert stored.asset_id > 0
        assert stored.severity
        assert stored.category
        assert stored.finding
        assert stored.recommendation
        assert json.loads(stored.evidence)

        second_run = run_rules(session, as_of=NOW)
        replaced_count = session.scalar(select(func.count()).select_from(GovernanceFinding))

    assert replaced_count == len(second_run)
    assert replaced_count == len(results)


def test_rule_engine_flags_missing_owner_and_stale_report(session):
    workspace = Workspace(name="Rule Test Workspace", description="Rule test")
    user = User(
        display_name="Active Owner",
        email="active.owner@example.invalid",
        role="member",
        workspace=workspace,
    )
    source = DataSource(name="Rule Test Source", source_type="sqlite", connection_summary="local")
    model = SemanticModel(
        name="Rule Test Model",
        description="Certified model",
        data_source=source,
        certified=True,
    )
    good_report = Report(
        name="Current Owned Report",
        description="Healthy report",
        owner=user.display_name,
        workspace=workspace,
        semantic_model=model,
        last_viewed_at=NOW - timedelta(days=10),
        style_compliant=True,
        accessibility_compliant=True,
    )
    stale_report = Report(
        name="Stale Former Owner Report",
        description="Stale report",
        owner="Former Owner",
        workspace=workspace,
        semantic_model=model,
        last_viewed_at=NOW - timedelta(days=120),
        style_compliant=True,
        accessibility_compliant=True,
    )
    session.add_all([good_report, stale_report])
    session.commit()

    results = evaluate_rules(session, as_of=NOW)
    stale_result_ids = {result.rule_id for result in results if result.asset_id == stale_report.id}
    good_result_ids = {result.rule_id for result in results if result.asset_id == good_report.id}

    assert {"R001", "R002"} <= stale_result_ids
    assert "R001" not in good_result_ids
    assert "R002" not in good_result_ids


def test_rule_engine_flags_refresh_failure_rate_threshold(session):
    source = DataSource(
        name="Refresh Test Source", source_type="sqlite", connection_summary="local"
    )
    model = SemanticModel(
        name="Refresh Test Model",
        description="Refresh model",
        data_source=source,
        certified=True,
    )
    session.add(model)
    session.flush()
    for index in range(20):
        started_at = NOW - timedelta(hours=index)
        session.add(
            RefreshEvent(
                semantic_model=model,
                started_at=started_at,
                completed_at=started_at + timedelta(minutes=5),
                status="failed" if index < 3 else "succeeded",
            )
        )
    session.commit()

    results = evaluate_rules(session, as_of=NOW)
    failure_rate_results = [result for result in results if result.rule_id == "R003"]

    assert len(failure_rate_results) == 1
    assert failure_rate_results[0].evidence["failure_rate"] == 0.15
