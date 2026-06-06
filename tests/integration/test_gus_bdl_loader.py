"""Integration tests for GUSBDLLoader — verifies upsert behavior."""

from pathlib import Path

import polars as pl
import pytest

from src.api.db.connection import get_session
from src.api.db.models import DimDemographics
from src.api.loaders.gus_bdl_loader import GUSBDLLoader


def _make_processed(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "gus_bdl_processed.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _base_row(**overrides) -> dict:
    row = {
        "teryt": "071412865000",
        "year": 2023,
        "city": "warszawa",
        "population": 1_800_000,
        "avg_gross_salary": 9_500.0,
        "unemployment_rate": 2.1,
        "migration_balance": 5_000,
        "working_age_population": 1_200_000,
    }
    row.update(overrides)
    return row


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_inserts_dim_demographics(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row()])
    count = GUSBDLLoader(source_path=path, config=test_config).load()
    assert count == 1

    with get_session(db_engine) as session:
        rows = session.query(DimDemographics).all()
        assert len(rows) == 1
        assert rows[0].city == "warszawa"
        assert rows[0].population == 1_800_000


def test_load_upserts_on_conflict(tmp_path, test_config, db_engine):
    """Second run with updated values should update the existing row, not duplicate."""
    path1 = _make_processed(tmp_path, [_base_row(avg_gross_salary=9_000.0)])
    GUSBDLLoader(source_path=path1, config=test_config).load()

    path2 = _make_processed(tmp_path, [_base_row(avg_gross_salary=10_000.0)])
    GUSBDLLoader(source_path=path2, config=test_config).load()

    with get_session(db_engine) as session:
        rows = session.query(DimDemographics).all()
        assert len(rows) == 1
        assert rows[0].avg_gross_salary == pytest.approx(10_000.0)


def test_load_multiple_city_year_rows(tmp_path, test_config, db_engine):
    rows = [
        _base_row(teryt="071412865000", city="warszawa", year=2022),
        _base_row(teryt="071412865000", city="warszawa", year=2023),
        _base_row(teryt="011212161011", city="kraków", year=2023),
    ]
    path = _make_processed(tmp_path, rows)
    count = GUSBDLLoader(source_path=path, config=test_config).load()
    assert count == 3


def test_load_allows_null_columns(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(population=None, migration_balance=None)])
    count = GUSBDLLoader(source_path=path, config=test_config).load()
    assert count == 1

    with get_session(db_engine) as session:
        row = session.query(DimDemographics).first()
        assert row is not None
        assert row.population is None
        assert row.migration_balance is None


def test_load_negative_migration_balance(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(migration_balance=-3_000)])
    GUSBDLLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        row = session.query(DimDemographics).first()
        assert row is not None
        assert row.migration_balance == -3_000


def test_load_empty_parquet_returns_zero(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [])
    count = GUSBDLLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_is_idempotent(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row()])
    loader = GUSBDLLoader(source_path=path, config=test_config)
    loader.load()
    count2 = loader.load()
    assert count2 == 1  # upsert returns full batch size

    with get_session(db_engine) as session:
        assert session.query(DimDemographics).count() == 1
