"""Integration tests for KPI SQL views."""

import datetime
from pathlib import Path

import polars as pl
import pytest
from sqlalchemy import text
from src.api.db.connection import get_session
from src.api.db.views import KPI_VIEW_NAMES
from src.api.loaders.gov_data_loader import GovDataLoader
from src.api.loaders.kaggle_loader import KaggleLoader
from src.api.loaders.nbp_loader import NBPLoader


def _make_kaggle(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "kaggle.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _make_gov(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "gov.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _make_nbp(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "nbp.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def test_kpi_views_exist_after_init(db_engine):
    with get_session(db_engine) as session:
        result = session.execute(
            text(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = 'public'"
            )
        )
        existing = {row[0] for row in result}
    assert set(KPI_VIEW_NAMES).issubset(existing)


def test_kpi_views_query_without_error(db_engine):
    with get_session(db_engine) as session:
        for view in KPI_VIEW_NAMES:
            session.execute(text(f'SELECT * FROM "{view}" LIMIT 1'))


def test_kpi_01_avg_offer_price_m2(
    tmp_path, test_config, db_engine, seeded_demographics
):
    row = {
        "id": "l-1",
        "price": 400_000.0,
        "square_meters": 40.0,
        "city": "Warszawa",
        "city_norm": "warszawa",
        "latitude": 52.23,
        "longitude": 21.01,
        "snapshot_date": datetime.date(2024, 1, 15),
        "market_type": "primary",
        "rooms": 2,
        "floor": 1,
        "floor_count": 5,
        "build_year": 2015,
        "building_material_norm": "brick",
        "condition_norm": "high",
        "has_balcony": True,
        "has_elevator": True,
        "has_parking_space": False,
        "has_storage_room": False,
        "price_per_m2_pln": 10_000.0,
    }
    KaggleLoader(source_path=_make_kaggle(tmp_path, [row]), config=test_config).load()

    with get_session(db_engine) as session:
        rows = session.execute(
            text(
                "SELECT avg_price_m2_pln, listing_count "
                'FROM "vw_kpi_01_avg_offer_price_m2" '
                "WHERE city = 'warszawa'"
            )
        ).all()
    assert len(rows) == 1
    assert rows[0][0] == pytest.approx(10_000.0)
    assert rows[0][1] == 1


def test_kpi_02_offer_vs_nbp_deviation(
    tmp_path, test_config, db_engine, seeded_locations, seeded_market_types
):
    """KPI 2 uses Fact_Listing (Kaggle offers) vs Fact_Benchmark_NBP."""
    kaggle_row = {
        "id": "l-kpi2",
        "price": 480_000.0,
        "square_meters": 40.0,
        "city": "Warszawa",
        "city_norm": "warszawa",
        "latitude": 52.23,
        "longitude": 21.01,
        "snapshot_date": datetime.date(2024, 1, 15),
        "market_type": "primary",
        "rooms": 2,
        "floor": 1,
        "floor_count": 5,
        "build_year": 2015,
        "building_material_norm": "brick",
        "condition_norm": "high",
        "has_balcony": True,
        "has_elevator": True,
        "has_parking_space": False,
        "has_storage_room": False,
        "price_per_m2_pln": 12_000.0,
    }
    nbp_row = {
        "year": 2024,
        "quarter": 1,
        "city": "Warszawa",
        "market": "primary",
        "avg_offer_price_m2_pln": 11_500.0,
        "avg_transaction_price_m2_pln": 10_000.0,
        "hedonic_index": 1.0,
    }
    KaggleLoader(
        source_path=_make_kaggle(tmp_path, [kaggle_row]), config=test_config
    ).load()
    NBPLoader(source_path=_make_nbp(tmp_path, [nbp_row]), config=test_config).load()

    with get_session(db_engine) as session:
        row = session.execute(
            text(
                "SELECT deviation_from_transaction_pct "
                'FROM "vw_kpi_02_offer_vs_nbp_deviation" '
                "WHERE city = 'warszawa' AND year = 2024 AND quarter = 1"
            )
        ).one()
    # (12 000 - 10 000) / 10 000 * 100 = 20 %
    assert row[0] == pytest.approx(20.0)


def test_kpi_06_sales_velocity(tmp_path, test_config, db_engine):
    sold_row = {
        "unit_id": "U-2",
        "developer_name": "Dev",
        "investment_id": "INV-2",
        "city": "Warszawa",
        "city_norm": "Warszawa",
        "street": "ul. Test 2",
        "regon": "123456789",
        "unit_status": "sprzedany",
        "status_norm": "SOLD",
        "snapshot_date": "2024-01-17",
        "total_price_gross": 500_000.0,
        "usable_area_m2": 50.0,
        "unit_value_pln": 500_000.0,
        "prev_price": 520_000.0,
        "change_amount_pln": -20_000.0,
        "price_per_m2_pln": 10_000.0,
        "is_first_snapshot": False,
        "is_price_changed": True,
        "is_status_changed": True,
        "is_price_drop": True,
        "download_url": "http://example.com/b.csv",
    }
    path = _make_gov(tmp_path, [sold_row])
    GovDataLoader(source_path=path, config=test_config).load()

    with get_session(db_engine) as session:
        row = session.execute(
            text(
                "SELECT units_sold_or_reserved "
                'FROM "vw_kpi_06_sales_velocity" '
                "WHERE city = 'Warszawa'"
            )
        ).one()
    assert row[0] == 1
