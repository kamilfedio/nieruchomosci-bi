"""Shared pytest fixtures."""

import os

import polars as pl
import pytest

from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import Base, DimDemographics
from src.api.db.repositories.dimensions import (
    DimDemographicsRepository,
    DimLocationRepository,
    DimMarketTypeRepository,
)

_DEFAULT_TEST_URL = (
    "postgresql+psycopg2://airflow:airflow@localhost:5432/nieruchomosci_test"
)


@pytest.fixture
def test_config() -> Config:
    """Config pointing at isolated test DB (requires PostGIS postgres)."""
    return Config(
        database_url=os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_URL),
        gemini_api_key="",
        bdl_api_key="",
        scrape_limit=None,
        cities=[
            "Warszawa",
            "Kraków",
            "Wrocław",
            "Gdańsk",
            "Poznań",
            "Łódź",
            "Katowice",
            "Lublin",
            "Szczecin",
            "Bydgoszcz",
        ],
    )


@pytest.fixture
def db_engine(test_config: Config):
    engine = build_engine(test_config.database_url)
    Base.metadata.drop_all(engine)
    init_db(engine)
    return engine


@pytest.fixture
def seeded_locations(db_engine, test_config: Config):
    """Pre-populate Dim_Location with project cities."""
    with get_session(db_engine) as session:
        repo = DimLocationRepository(session)
        for city in test_config.cities:
            repo.get_or_create_id(city)
    return db_engine


@pytest.fixture
def seeded_market_types(db_engine):
    """Pre-populate Dim_Market_Type with primary/secondary/unknown."""
    with get_session(db_engine) as session:
        repo = DimMarketTypeRepository(session)
        for code in ("primary", "secondary", "unknown"):
            repo.get_or_create_id(code)
    return db_engine


@pytest.fixture
def seeded_demographics(db_engine):
    """Pre-populate Dim_Demographics for Warszawa 2023."""
    with get_session(db_engine) as session:
        repo = DimDemographicsRepository(session)
        repo.upsert_batch(
            [
                DimDemographics(
                    teryt="071412865000",
                    year=2023,
                    city="warszawa",
                    population=1800000,
                    avg_gross_salary=9500.0,
                    unemployment_rate=2.1,
                    migration_balance=5000,
                    working_age_population=1200000,
                )
            ]
        )
    return db_engine


def make_processed_parquet(tmp_path, name: str, data: dict):
    """Write a minimal processed Parquet file and return its path."""
    path = tmp_path / f"{name}.parquet"
    pl.DataFrame(data).write_parquet(path)
    return path
