"""Shared fixtures for PostgreSQL integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from email_dedup.db.session import create_session_factory
from email_dedup.settings import Settings

EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"


@pytest.fixture(scope="session")
def database_url() -> str:
    return Settings.from_environment().database_url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Engine:
    eng = create_engine(database_url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not available: {exc}")
    return eng


@pytest.fixture(scope="session")
def migrated_engine(engine: Engine) -> Engine:
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture
def session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        session.execute(
            text(
                "TRUNCATE ingestion_jobs, raw_documents, canonical_threads "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.commit()
    return factory


def read_eval(name: str) -> str:
    return (EVAL_DIR / name).read_text(encoding="utf-8")
