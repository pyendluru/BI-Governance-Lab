from datetime import timedelta

from sqlalchemy import func, select

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
from bi_governance_lab.seed import NOW, seed


def test_seed_creates_expected_record_counts(configured_temp_db):
    seed()

    import bi_governance_lab.db as db

    with db.SessionLocal() as session:
        assert _count(session, Workspace) == 15
        assert _count(session, User) == 40
        assert _count(session, Report) == 60
        assert _count(session, SemanticModel) == 25
        assert _count(session, DataSource) == 12
        assert _count(session, RefreshEvent) == 300
        assert _count(session, GovernanceCheck) == 4
        assert _count(session, GovernanceResult) == 240


def test_seed_includes_intended_governance_problems(configured_temp_db):
    seed()

    import bi_governance_lab.db as db

    stale_cutoff = NOW - timedelta(days=90)
    with db.SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Report).where(Report.workspace_id.is_(None))
            )
            > 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(RefreshEvent)
                .where(RefreshEvent.status == "failed")
            )
            > 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(Report).where(Report.last_viewed_at < stale_cutoff)
            )
            > 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(SemanticModel)
                .where(SemanticModel.description.is_(None))
            )
            > 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(Report).where(Report.description.is_(None))
            )
            > 0
        )
        assert _overlapping_source_count(session) > 0
        assert _excessive_admin_user_count(session) > 0
        assert _failed_result_count(session, "style") > 0
        assert _failed_result_count(session, "accessibility") > 0


def test_seed_is_idempotent(configured_temp_db):
    seed()
    seed()

    import bi_governance_lab.db as db

    with db.SessionLocal() as session:
        assert _count(session, Workspace) == 15
        assert _count(session, Report) == 60


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def _overlapping_source_count(session) -> int:
    grouped_sources = (
        select(SemanticModel.data_source_id)
        .group_by(SemanticModel.data_source_id)
        .having(func.count(SemanticModel.id) > 1)
        .subquery()
    )
    return session.scalar(select(func.count()).select_from(grouped_sources))


def _excessive_admin_user_count(session) -> int:
    grouped_admins = (
        select(Permission.user_id)
        .where(Permission.access_level == "admin")
        .group_by(Permission.user_id)
        .having(func.count(Permission.id) > 8)
        .subquery()
    )
    return session.scalar(select(func.count()).select_from(grouped_admins))


def _failed_result_count(session, category: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(GovernanceResult)
        .join(GovernanceCheck)
        .where(GovernanceCheck.category == category, GovernanceResult.passed.is_(False))
    )
