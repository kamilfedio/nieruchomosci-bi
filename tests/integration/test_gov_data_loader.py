"""Integration tests for GovDataLoader — writes to an isolated SQLite DB."""

from pathlib import Path

import polars as pl
import pytest

from src.api.db.connection import get_session
from src.api.db.models import DimLocation, DimTime, FactChange
from src.api.loaders.gov_data_loader import GovDataLoader


def _make_processed(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "gov_data_processed.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _base_row(**overrides) -> dict:
    row = {
        "unit_id": "U-001",
        "developer_name": "Deweloper S.A.",
        "investment_id": "INV-1",
        "city": "Warszawa",
        "city_norm": "Warszawa",
        "street": "ul. Testowa 1",
        "regon": "123456789",
        "unit_status": "dostępny",
        "status_norm": "AVAILABLE",
        "snapshot_date": "2024-01-15",
        "total_price_gross": 500_000.0,
        "usable_area_m2": 50.0,
        "unit_value_pln": 500_000.0,
        "prev_price": None,
        "change_amount_pln": None,
        "price_per_m2_pln": 10_000.0,
        "is_first_snapshot": True,
        "is_price_changed": False,
        "is_status_changed": False,
        "is_price_drop": False,
        "download_url": "http://example.com/file.csv",
    }
    row.update(overrides)
    return row


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_inserts_fact_change_row(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row()])
    count = GovDataLoader(source_path=path, config=test_config).load()
    assert count == 1

    with get_session(db_engine) as session:
        rows = session.query(FactChange).all()
        assert len(rows) == 1
        assert rows[0].unit_id == "U-001"


def test_load_creates_dim_location(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(city_norm="Kraków")])
    GovDataLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        loc = session.query(DimLocation).filter(DimLocation.city_norm == "Kraków").first()
        assert loc is not None


def test_load_creates_dim_time(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(snapshot_date="2024-03-01")])
    GovDataLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        t = session.query(DimTime).filter(DimTime.id == 20240301).first()
        assert t is not None
        assert t.year == 2024
        assert t.quarter == 1


def test_load_skips_city_not_in_config(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(city_norm="Nieznane Miasto")])
    count = GovDataLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_skips_invalid_snapshot_date(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(snapshot_date=None)])
    count = GovDataLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_is_idempotent(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row()])
    loader = GovDataLoader(source_path=path, config=test_config)
    loader.load()
    loader.load()

    # Only one row in DB regardless of how many times load() is called
    with get_session(db_engine) as session:
        assert session.query(FactChange).count() == 1


def test_load_multiple_rows(tmp_path, test_config, db_engine):
    rows = [
        _base_row(unit_id="U-001", download_url="http://a.com/f1.csv"),
        _base_row(unit_id="U-002", download_url="http://a.com/f1.csv"),
    ]
    path = _make_processed(tmp_path, rows)
    count = GovDataLoader(source_path=path, config=test_config).load()
    assert count == 2


def test_load_empty_parquet_returns_zero(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [])
    count = GovDataLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_date_formats(tmp_path, test_config, db_engine):
    """Loader must parse d.m.Y format as well as Y-m-d."""
    path = _make_processed(tmp_path, [_base_row(snapshot_date="15.01.2024", unit_id="U-003")])
    count = GovDataLoader(source_path=path, config=test_config).load()
    assert count == 1
