"""SQLAlchemy engine and session management"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Inspector, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def build_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def _migrate(engine: Engine) -> None:
    """Apply additive schema changes to an existing database."""
    insp: Inspector = inspect(engine)
    if "developer_files" in insp.get_table_names():
        existing = {col["name"] for col in insp.get_columns("developer_files")}
        with engine.begin() as conn:
            if "status" not in existing:
                conn.execute(
                    text(
                        "ALTER TABLE developer_files"
                        " ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_developer_files_status"
                        " ON developer_files (status)"
                    )
                )
            if "raw_path" not in existing:
                conn.execute(
                    text("ALTER TABLE developer_files ADD COLUMN raw_path TEXT")
                )
    if "Fact_Change" in insp.get_table_names():
        existing_fc = {col["name"] for col in insp.get_columns("Fact_Change")}
        with engine.begin() as conn:
            if "is_first_snapshot" not in existing_fc:
                conn.execute(
                    text(
                        "ALTER TABLE Fact_Change"
                        " ADD COLUMN is_first_snapshot INTEGER NOT NULL DEFAULT 0"
                    )
                )
    if "Fact_Listing" in insp.get_table_names():
        existing_fl = {col["name"] for col in insp.get_columns("Fact_Listing")}
        with engine.begin() as conn:
            if "fk_flood_risk" not in existing_fl:
                conn.execute(
                    text("ALTER TABLE Fact_Listing ADD COLUMN fk_flood_risk INTEGER")
                )


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _migrate(engine)


@contextmanager
def get_session(engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
