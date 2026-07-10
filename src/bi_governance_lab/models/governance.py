from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bi_governance_lab.db import Base
from bi_governance_lab.time import utc_now


class Workspace(Base):
    """Business intelligence workspace containing users, reports, and permissions."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    reports: Mapped[list["Report"]] = relationship(
        back_populates="workspace",
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class User(Base):
    """Fictional enterprise user with a home workspace and access grants."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[str] = mapped_column(String(50), default="viewer")
    workspace: Mapped[Workspace] = relationship(back_populates="users")
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class DataSource(Base):
    """Upstream source system used by one or more semantic models."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    source_type: Mapped[str] = mapped_column(String(50))
    connection_summary: Mapped[str] = mapped_column(String(500))
    semantic_models: Mapped[list["SemanticModel"]] = relationship(back_populates="data_source")


class SemanticModel(Base):
    """Reusable semantic model that powers one or more BI reports."""

    __tablename__ = "semantic_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    certified: Mapped[bool] = mapped_column(Boolean, default=False)
    data_source: Mapped[DataSource] = relationship(back_populates="semantic_models")
    reports: Mapped[list["Report"]] = relationship(back_populates="semantic_model")
    refresh_events: Mapped[list["RefreshEvent"]] = relationship(
        back_populates="semantic_model", cascade="all, delete-orphan"
    )


class Report(Base):
    """Business intelligence report with ownership, usage, and compliance metadata."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    semantic_model_id: Mapped[int] = mapped_column(ForeignKey("semantic_models.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(200))
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    style_compliant: Mapped[bool] = mapped_column(Boolean, default=False)
    accessibility_compliant: Mapped[bool] = mapped_column(Boolean, default=False)
    workspace: Mapped[Workspace | None] = relationship(back_populates="reports")
    semantic_model: Mapped[SemanticModel] = relationship(back_populates="reports")
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )
    governance_results: Mapped[list["GovernanceResult"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class RefreshEvent(Base):
    """Refresh execution event for a semantic model."""

    __tablename__ = "refresh_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    semantic_model_id: Mapped[int] = mapped_column(ForeignKey("semantic_models.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30))
    message: Mapped[str | None] = mapped_column(Text)
    semantic_model: Mapped[SemanticModel] = relationship(back_populates="refresh_events")


class Permission(Base):
    """User permission grant scoped to either a workspace or a report."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), index=True)
    access_level: Mapped[str] = mapped_column(String(30))
    user: Mapped[User] = relationship(back_populates="permissions")
    workspace: Mapped[Workspace | None] = relationship(back_populates="permissions")
    report: Mapped[Report] = relationship(back_populates="permissions")


class GovernanceCheck(Base):
    """Reusable assessment check for style or accessibility scoring."""

    __tablename__ = "governance_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    results: Mapped[list["GovernanceResult"]] = relationship(
        back_populates="check", cascade="all, delete-orphan"
    )


class GovernanceResult(Base):
    """Assessment result for a report and governance check."""

    __tablename__ = "governance_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("governance_checks.id"), index=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[int] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    report: Mapped[Report] = relationship(back_populates="governance_results")
    check: Mapped[GovernanceCheck] = relationship(back_populates="results")


class GovernanceFinding(Base):
    """Persisted rule-engine finding for an evaluated BI asset."""

    __tablename__ = "governance_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), index=True)
    asset_type: Mapped[str] = mapped_column(String(50), index=True)
    asset_id: Mapped[int] = mapped_column(Integer, index=True)
    severity: Mapped[str] = mapped_column(String(30))
    category: Mapped[str] = mapped_column(String(50), index=True)
    finding: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
