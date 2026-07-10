import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bi_governance_lab.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def _engine_kwargs(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def create_tables() -> None:
    """Create all configured database tables."""
    from bi_governance_lab.models import governance  # noqa: F401

    logger.info("Creating database tables")
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependency injection."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        logger.exception("Database session rolled back after an unhandled error")
        raise
    finally:
        session.close()
