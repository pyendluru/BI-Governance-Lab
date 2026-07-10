import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bi_governance_lab.db import Base


@pytest.fixture
def configured_temp_db(monkeypatch, tmp_path):
    database_path = tmp_path / "test.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("BI_GOVERNANCE_DATABASE_URL", database_url)

    import bi_governance_lab.db as db

    db.settings = db.get_settings.cache_clear() or db.get_settings()
    db.engine = create_engine(database_url, connect_args={"check_same_thread": False})
    db.SessionLocal = sessionmaker(
        bind=db.engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    return db.SessionLocal


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db_session:
        yield db_session
    Base.metadata.drop_all(engine)
