"""Integration tests for KaggleLoader."""

import datetime
from pathlib import Path

import polars as pl
import pytest

from src.api.db.connection import get_session
from src.api.db.models import FactListing
from src.api.loaders.kaggle_loader import KaggleLoader


def _make_processed(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "kaggle_processed.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _base_row(**overrides) -> dict:
    row = {
        "id": "listing-001",
        "price": 500_000.0,
        "square_meters": 50.0,
        "city": "Warszawa",
        "city_norm": "warszawa",
        "latitude": 52.23,
        "longitude": 21.01,
        "snapshot_date": datetime.date(2024, 1, 15),
        "market_type": "primary",
        "rooms": 3,
        "floor": 2,
        "floor_count": 10,
        "build_year": 2010,
        "building_material_norm": "brick",
        "condition_norm": "high",
        "has_balcony": True,
        "has_elevator": False,
        "has_parking_space": True,
        "has_storage_room": False,
        "price_per_m2_pln": 10_000.0,
        "fk_flood_risk": 0,
    }
    row.update(overrides)
    return row


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_inserts_fact_listing(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row()])
    count = KaggleLoader(source_path=path, config=test_config).load()
    assert count == 1

    with get_session(db_engine) as session:
        rows = session.query(FactListing).all()
        assert len(rows) == 1
        assert rows[0].listing_id == "listing-001"
        assert rows[0].total_price_pln == pytest.approx(500_000.0)
        assert rows[0].area_m2 == pytest.approx(50.0)


def test_load_creates_dim_geo_location(tmp_path, test_config, db_engine):
    from src.api.db.models import DimGeoLocation

    path = _make_processed(tmp_path, [_base_row()])
    KaggleLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        geo = session.query(DimGeoLocation).filter(DimGeoLocation.city == "warszawa").first()
        assert geo is not None
        assert geo.lat_r == pytest.approx(52.23, abs=0.001)


def test_load_creates_dim_market_type(tmp_path, test_config, db_engine):
    from src.api.db.models import DimMarketType

    path = _make_processed(tmp_path, [_base_row(market_type="secondary")])
    KaggleLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        mkt = session.query(DimMarketType).filter(DimMarketType.market_code == "secondary").first()
        assert mkt is not None


def test_load_resolves_fk_demographics(tmp_path, test_config, seeded_demographics):
    """fk_demographics should be set when matching (city_norm, year) exists."""
    path = _make_processed(tmp_path, [_base_row(snapshot_date=datetime.date(2023, 6, 1))])
    KaggleLoader(source_path=path, config=test_config).load()

    with get_session(seeded_demographics) as session:
        row = session.query(FactListing).first()
        assert row is not None
        assert row.fk_demographics is not None


def test_load_resolves_fk_demographics_year_minus_1(tmp_path, test_config, seeded_demographics):
    """fk_demographics fallback: year-1 when current year has no record."""
    path = _make_processed(tmp_path, [_base_row(snapshot_date=datetime.date(2024, 3, 1))])
    KaggleLoader(source_path=path, config=test_config).load()

    with get_session(seeded_demographics) as session:
        row = session.query(FactListing).first()
        assert row is not None
        # year=2024 not in DB → fallback to year=2023 which IS in DB
        assert row.fk_demographics is not None


def test_load_fk_demographics_null_when_no_match(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(city_norm="gdańsk")])
    KaggleLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        row = session.query(FactListing).first()
        assert row is not None
        assert row.fk_demographics is None


def test_load_skips_null_price(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(price=None)])
    count = KaggleLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_is_idempotent(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row()])
    loader = KaggleLoader(source_path=path, config=test_config)
    loader.load()
    loader.load()

    # Only one row in DB regardless of how many times load() is called
    with get_session(db_engine) as session:
        assert session.query(FactListing).count() == 1


def test_load_multiple_listings(tmp_path, test_config, db_engine):
    rows = [
        _base_row(id="L-001", latitude=52.20),
        _base_row(id="L-002", latitude=52.25),
    ]
    path = _make_processed(tmp_path, rows)
    count = KaggleLoader(source_path=path, config=test_config).load()
    assert count == 2


def test_load_empty_parquet_returns_zero(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [])
    count = KaggleLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_stores_price_per_m2(tmp_path, test_config, db_engine):
    path = _make_processed(tmp_path, [_base_row(price_per_m2_pln=9_800.0)])
    KaggleLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        row = session.query(FactListing).first()
        assert row is not None
        assert row.price_per_m2_pln == pytest.approx(9_800.0)
