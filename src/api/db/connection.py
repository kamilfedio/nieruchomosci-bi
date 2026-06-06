"""SQLAlchemy engine and session management"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def build_engine(database_url: str) -> Engine:
    return create_engine(database_url, echo=False, pool_pre_ping=True)


def ensure_postgis(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))


def init_db(engine: Engine) -> None:
    ensure_postgis(engine)
    Base.metadata.create_all(engine)
    _ensure_gist_index(engine)


def _ensure_gist_index(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_flood_zones_geom "
                "ON flood_zones USING GIST (geom)"
            )
        )


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
