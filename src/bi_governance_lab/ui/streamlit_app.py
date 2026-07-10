from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from bi_governance_lab import db
from bi_governance_lab.models import (
    DataSource,
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
from bi_governance_lab.rules import run_rules
from bi_governance_lab.seed import seed
from bi_governance_lab.time import utc_now

PAGE_TITLE = "BI Governance Lab"


@dataclass(frozen=True)
class NavigationPage:
    """Sidebar navigation item for a Streamlit page."""

    label: str
    renderer: Callable[[Session], None]


def main() -> None:
    """Run the Streamlit governance interface."""
    st.set_page_config(page_title=PAGE_TITLE, page_icon="BI", layout="wide")
    _apply_theme()
    _ensure_demo_data()

    pages = [
        NavigationPage("Executive Dashboard", render_executive_dashboard),
        NavigationPage("Asset Catalog", render_asset_catalog),
        NavigationPage("Governance Findings", render_governance_findings),
        NavigationPage("Accessibility Review", render_accessibility_review),
        NavigationPage("Style Guide Compliance", render_style_guide_compliance),
        NavigationPage("Refresh Health", render_refresh_health),
        NavigationPage("Workspace Explorer", render_workspace_explorer),
    ]

    with st.sidebar:
        st.title("BI Governance Lab")
        selected_page = st.radio("Navigation", [page.label for page in pages])
        st.caption("Local fictional data only")
        if st.button("Run governance rules", use_container_width=True):
            with db.SessionLocal() as session:
                run_rules(session)
            st.success("Governance findings refreshed.")

    with db.SessionLocal() as session:
        for page in pages:
            if page.label == selected_page:
                page.renderer(session)
                break


def render_executive_dashboard(session: Session) -> None:
    """Render portfolio-level KPIs, charts, and risk indicators."""
    st.header("Executive Dashboard")
    st.caption("Portfolio health across reports, models, workspaces, refreshes, and findings.")

    counts = _portfolio_counts(session)
    findings = _findings_frame(session)
    reports = _reports_frame(session)

    columns = st.columns(5)
    columns[0].metric("Workspaces", counts["workspaces"])
    columns[1].metric("Reports", counts["reports"])
    columns[2].metric("Semantic Models", counts["semantic_models"])
    columns[3].metric("Findings", counts["findings"])
    columns[4].metric("Failed Refreshes", counts["failed_refreshes"])

    if findings.empty:
        st.info("No findings stored yet. Run governance rules from the sidebar.")
        return

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Findings by severity")
        st.bar_chart(findings.groupby("severity").size())
    with right:
        st.subheader("Findings by category")
        st.bar_chart(findings.groupby("category").size())

    st.subheader("Governance posture")
    compliant_reports = reports[
        (reports["style_compliant"] == "Yes") & (reports["accessibility_compliant"] == "Yes")
    ]
    compliance_ratio = len(compliant_reports) / len(reports) if len(reports) else 0
    st.progress(
        compliance_ratio, text=f"{compliance_ratio:.0%} reports pass style and accessibility flags"
    )

    st.subheader("Most urgent findings")
    urgent = _filter_frame(findings, severity=["high"]).head(10)
    st.dataframe(urgent, use_container_width=True, hide_index=True)


def render_asset_catalog(session: Session) -> None:
    """Render searchable and sortable catalogs for core BI assets."""
    st.header("Asset Catalog")
    asset_type = st.sidebar.selectbox(
        "Asset type", ["Reports", "Semantic Models", "Data Sources", "Users", "Workspaces"]
    )
    search = st.sidebar.text_input("Search assets")

    frame_loaders: dict[str, Callable[[Session], pd.DataFrame]] = {
        "Reports": _reports_frame,
        "Semantic Models": _semantic_models_frame,
        "Data Sources": _data_sources_frame,
        "Users": _users_frame,
        "Workspaces": _workspaces_frame,
    }
    frame = _search_frame(frame_loaders[asset_type](session), search)
    sort_column = st.sidebar.selectbox("Sort by", list(frame.columns))
    ascending = st.sidebar.toggle("Ascending", value=True)
    frame = frame.sort_values(sort_column, ascending=ascending)

    st.dataframe(frame, use_container_width=True, hide_index=True)
    _render_drilldown(frame, asset_type)


def render_governance_findings(session: Session) -> None:
    """Render filterable governance findings with drill-down evidence."""
    st.header("Governance Findings")
    findings = _findings_frame(session)
    if findings.empty:
        st.info("No findings stored yet. Run governance rules from the sidebar.")
        return

    filtered = _interactive_findings_filter(findings)
    st.metric("Visible findings", len(filtered))
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    _render_finding_drilldown(filtered)


def render_accessibility_review(session: Session) -> None:
    """Render accessibility scores, failures, and remediation detail."""
    st.header("Accessibility Review")
    frame = _score_frame(session, "accessibility")
    _render_score_page(frame, "accessibility", "Accessibility")


def render_style_guide_compliance(session: Session) -> None:
    """Render style guide scores, failures, and remediation detail."""
    st.header("Style Guide Compliance")
    frame = _score_frame(session, "style")
    _render_score_page(frame, "style", "Style")


def render_refresh_health(session: Session) -> None:
    """Render semantic model refresh health and failure trends."""
    st.header("Refresh Health")
    frame = _refresh_health_frame(session)
    if frame.empty:
        st.info("No refresh events are available.")
        return

    unhealthy = frame[frame["failure_rate"] > 0.10]
    columns = st.columns(3)
    columns[0].metric("Models monitored", len(frame))
    columns[1].metric("Models above 10% failure", len(unhealthy))
    columns[2].metric("Average failure rate", f"{frame['failure_rate'].mean():.1%}")

    st.subheader("Failure rate by semantic model")
    st.bar_chart(frame.set_index("semantic_model")["failure_rate"])

    search = st.sidebar.text_input("Search models")
    filtered = _search_frame(frame, search)
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    _render_drilldown(filtered, "Refresh Health")


def render_workspace_explorer(session: Session) -> None:
    """Render workspace users, reports, permissions, and risk signals."""
    st.header("Workspace Explorer")
    workspaces = session.scalars(select(Workspace).order_by(Workspace.name)).all()
    selected = st.sidebar.selectbox("Workspace", [workspace.name for workspace in workspaces])
    workspace = next(workspace for workspace in workspaces if workspace.name == selected)

    admin_count = session.scalar(
        select(func.count(Permission.id)).where(
            Permission.workspace_id == workspace.id, Permission.access_level == "admin"
        )
    )
    report_count = session.scalar(
        select(func.count(Report.id)).where(Report.workspace_id == workspace.id)
    )
    user_count = session.scalar(
        select(func.count(User.id)).where(User.workspace_id == workspace.id)
    )

    columns = st.columns(3)
    columns[0].metric("Reports", report_count)
    columns[1].metric("Users", user_count)
    columns[2].metric("Admins", admin_count)

    if admin_count < 2:
        st.warning("This workspace has fewer than two administrators.")
    elif admin_count > 5:
        st.error("This workspace has excessive administrator permissions.")
    else:
        st.success("Administrator coverage is within policy.")

    tabs = st.tabs(["Reports", "Users", "Permissions"])
    with tabs[0]:
        st.dataframe(
            _reports_frame(session).query("workspace == @selected"),
            use_container_width=True,
            hide_index=True,
        )
    with tabs[1]:
        st.dataframe(
            _users_frame(session).query("workspace == @selected"),
            use_container_width=True,
            hide_index=True,
        )
    with tabs[2]:
        st.dataframe(
            _permissions_frame(session, workspace.id), use_container_width=True, hide_index=True
        )


def _ensure_demo_data() -> None:
    db.create_tables()
    with db.SessionLocal() as session:
        has_workspace = session.scalar(select(Workspace.id).limit(1)) is not None
        has_findings = session.scalar(select(GovernanceFinding.id).limit(1)) is not None
    if not has_workspace:
        seed()
    if not has_findings:
        with db.SessionLocal() as session:
            run_rules(session)


def _portfolio_counts(session: Session) -> dict[str, int]:
    return {
        "workspaces": session.scalar(select(func.count()).select_from(Workspace)),
        "reports": session.scalar(select(func.count()).select_from(Report)),
        "semantic_models": session.scalar(select(func.count()).select_from(SemanticModel)),
        "findings": session.scalar(select(func.count()).select_from(GovernanceFinding)),
        "failed_refreshes": session.scalar(
            select(func.count()).select_from(RefreshEvent).where(RefreshEvent.status == "failed")
        ),
    }


def _reports_frame(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(
            Report.id,
            Report.name,
            Report.owner,
            Report.description,
            Report.last_viewed_at,
            Report.style_compliant,
            Report.accessibility_compliant,
            Workspace.name,
            SemanticModel.name,
        )
        .join(SemanticModel)
        .outerjoin(Workspace)
        .order_by(Report.name)
    )
    return pd.DataFrame(
        [
            {
                "id": row[0],
                "name": row[1],
                "owner": row[2],
                "description": row[3] or "Missing",
                "last_viewed_at": row[4],
                "style_compliant": _yes_no(row[5]),
                "accessibility_compliant": _yes_no(row[6]),
                "workspace": row[7] or "Orphaned",
                "semantic_model": row[8],
            }
            for row in rows
        ]
    )


def _semantic_models_frame(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(
            SemanticModel.id,
            SemanticModel.name,
            SemanticModel.description,
            SemanticModel.certified,
            DataSource.name,
            func.count(Report.id),
        )
        .join(DataSource)
        .outerjoin(Report)
        .group_by(SemanticModel.id, SemanticModel.name, DataSource.name)
        .order_by(SemanticModel.name)
    )
    return pd.DataFrame(
        [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2] or "Missing",
                "certified": _yes_no(row[3]),
                "data_source": row[4],
                "report_count": row[5],
            }
            for row in rows
        ]
    )


def _data_sources_frame(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(
            DataSource.id,
            DataSource.name,
            DataSource.source_type,
            DataSource.connection_summary,
            func.count(SemanticModel.id),
        )
        .outerjoin(SemanticModel)
        .group_by(DataSource.id, DataSource.name)
        .order_by(DataSource.name)
    )
    return pd.DataFrame(
        [
            {
                "id": row[0],
                "name": row[1],
                "source_type": row[2],
                "connection_summary": row[3],
                "semantic_model_count": row[4],
            }
            for row in rows
        ]
    )


def _users_frame(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(User.id, User.display_name, User.email, User.role, Workspace.name)
        .join(Workspace)
        .order_by(User.display_name)
    )
    return pd.DataFrame(
        [
            {
                "id": row[0],
                "display_name": row[1],
                "email": row[2],
                "role": row[3],
                "workspace": row[4],
            }
            for row in rows
        ]
    )


def _workspaces_frame(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(
            Workspace.id,
            Workspace.name,
            Workspace.description,
            Workspace.is_active,
            func.count(Report.id),
        )
        .outerjoin(Report)
        .group_by(Workspace.id, Workspace.name)
        .order_by(Workspace.name)
    )
    return pd.DataFrame(
        [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2] or "Missing",
                "active": _yes_no(row[3]),
                "report_count": row[4],
            }
            for row in rows
        ]
    )


def _findings_frame(session: Session) -> pd.DataFrame:
    findings = session.scalars(select(GovernanceFinding).order_by(GovernanceFinding.rule_id)).all()
    return pd.DataFrame(
        [
            {
                "rule_id": finding.rule_id,
                "asset_type": finding.asset_type,
                "asset_id": finding.asset_id,
                "severity": finding.severity,
                "category": finding.category,
                "finding": finding.finding,
                "recommendation": finding.recommendation,
                "evidence": _parse_evidence(finding.evidence),
                "evaluated_at": finding.evaluated_at,
            }
            for finding in findings
        ]
    )


def _score_frame(session: Session, category: str) -> pd.DataFrame:
    rows = session.execute(
        select(Report.name, GovernanceCheck.name, GovernanceResult.score, GovernanceResult.passed)
        .join(GovernanceResult)
        .join(GovernanceCheck)
        .where(GovernanceCheck.category == category)
        .order_by(Report.name)
    )
    return pd.DataFrame(
        [
            {"report": row[0], "check": row[1], "score": row[2], "passed": _yes_no(row[3])}
            for row in rows
        ]
    )


def _refresh_health_frame(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(
            SemanticModel.name,
            func.count(RefreshEvent.id),
            func.sum(case((RefreshEvent.status == "failed", 1), else_=0)),
            func.max(func.coalesce(RefreshEvent.completed_at, RefreshEvent.started_at)),
        )
        .join(RefreshEvent)
        .group_by(SemanticModel.id, SemanticModel.name)
        .order_by(SemanticModel.name)
    )
    frame = pd.DataFrame(
        [
            {
                "semantic_model": row[0],
                "total_refreshes": row[1],
                "failed_refreshes": row[2] or 0,
                "last_refresh_at": row[3],
                "failure_rate": (row[2] or 0) / row[1] if row[1] else 0,
            }
            for row in rows
        ]
    )
    if not frame.empty:
        frame["hours_since_refresh"] = frame["last_refresh_at"].apply(
            lambda value: (
                round((utc_now() - value).total_seconds() / 3600, 1) if value is not None else None
            )
        )
    return frame


def _permissions_frame(session: Session, workspace_id: int) -> pd.DataFrame:
    rows = session.execute(
        select(User.display_name, Permission.access_level, Report.name)
        .join(User)
        .outerjoin(Report)
        .where(Permission.workspace_id == workspace_id)
        .order_by(Permission.access_level, User.display_name)
    )
    return pd.DataFrame(
        [
            {
                "user": row[0],
                "access_level": row[1],
                "scope": "workspace" if row[2] is None else row[2],
            }
            for row in rows
        ]
    )


def _interactive_findings_filter(findings: pd.DataFrame) -> pd.DataFrame:
    severity = st.sidebar.multiselect("Severity", sorted(findings["severity"].unique()))
    category = st.sidebar.multiselect("Category", sorted(findings["category"].unique()))
    search = st.sidebar.text_input("Search findings")
    sort_column = st.sidebar.selectbox("Sort findings by", ["severity", "category", "rule_id"])
    filtered = _filter_frame(findings, severity=severity, category=category)
    filtered = _search_frame(filtered, search)
    return filtered.sort_values(sort_column)


def _render_score_page(frame: pd.DataFrame, category: str, label: str) -> None:
    if frame.empty:
        st.info(f"No {category} assessment results are available.")
        return

    failing = frame[frame["score"] < 80]
    columns = st.columns(3)
    columns[0].metric("Checks evaluated", len(frame))
    columns[1].metric("Failures", len(failing))
    columns[2].metric("Average score", f"{frame['score'].mean():.1f}")

    st.progress(min(frame["score"].mean() / 100, 1.0), text=f"Average {label.lower()} score")
    st.subheader(f"{label} score distribution")
    st.bar_chart(frame.groupby("check")["score"].mean())

    search = st.sidebar.text_input(f"Search {label.lower()} results")
    filtered = _search_frame(frame, search)
    st.dataframe(filtered.sort_values("score"), use_container_width=True, hide_index=True)
    _render_drilldown(filtered, f"{label} Review")


def _render_drilldown(frame: pd.DataFrame, label: str) -> None:
    if frame.empty:
        return
    st.subheader("Drill-down")
    selected_index = st.selectbox(
        f"Select {label.lower()} row",
        range(len(frame)),
        format_func=lambda index: _row_label(frame.iloc[index]),
    )
    st.json(_to_jsonable(frame.iloc[selected_index].to_dict()))


def _render_finding_drilldown(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    st.subheader("Finding drill-down")
    selected_index = st.selectbox(
        "Select finding",
        range(len(frame)),
        format_func=lambda index: (
            f"{frame.iloc[index]['rule_id']} - {frame.iloc[index]['finding']}"
        ),
    )
    row = frame.iloc[selected_index].to_dict()
    st.write(row["finding"])
    st.info(row["recommendation"])
    st.json(_to_jsonable(row["evidence"]))


def _filter_frame(
    frame: pd.DataFrame,
    severity: list[str] | None = None,
    category: list[str] | None = None,
) -> pd.DataFrame:
    filtered = frame
    if severity:
        filtered = filtered[filtered["severity"].isin(severity)]
    if category:
        filtered = filtered[filtered["category"].isin(category)]
    return filtered


def _search_frame(frame: pd.DataFrame, search: str) -> pd.DataFrame:
    if not search:
        return frame
    needle = search.casefold()
    return frame[
        frame.apply(
            lambda row: needle in " ".join(str(value).casefold() for value in row.values),
            axis=1,
        )
    ]


def _parse_evidence(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


def _row_label(row: pd.Series) -> str:
    for key in ("name", "finding", "report", "semantic_model", "display_name"):
        if key in row and pd.notna(row[key]):
            return str(row[key])
    return str(row.iloc[0])


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _apply_theme() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; }
        [data-testid="stMetricValue"] { font-size: 1.75rem; }
        [data-testid="stSidebar"] { border-right: 1px solid #e6eaf0; }
        div[data-testid="stDataFrame"] { border: 1px solid #e6eaf0; border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
