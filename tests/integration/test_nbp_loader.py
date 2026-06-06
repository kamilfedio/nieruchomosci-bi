"""Integration tests for NBPLoader."""

from pathlib import Path

import polars as pl
import pytest

from src.api.db.connection import get_session
from src.api.db.models import DimTime, FactBenchmarkNbp
from src.api.loaders.nbp_loader import NBPLoader


def _make_processed(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "nbp_processed.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _base_row(**overrides) -> dict:
    row = {
        "year": 2023,
        "quarter": 1,
        "city": "Warszawa",
        "market": "primary",
        "avg_offer_price_m2_pln": 12_000.0,
        "avg_transaction_price_m2_pln": 11_500.0,
        "hedonic_index": 1.02,
    }
    row.update(overrides)
    return row


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_inserts_fact_benchmark(tmp_path, test_config, seeded_locations, seeded_market_types):
    path = _make_processed(tmp_path, [_base_row()])
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 1

    with get_session(seeded_locations) as session:
        rows = session.query(FactBenchmarkNbp).all()
        assert len(rows) == 1
        assert rows[0].avg_offer_price_m2_pln == pytest.approx(12_000.0)


def test_load_skips_city_not_in_dim_location(tmp_path, test_config, seeded_locations, seeded_market_types):
    path = _make_processed(tmp_path, [_base_row(city="Nieznane")])
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_skips_market_not_in_dim_market_type(tmp_path, test_config, seeded_locations):
    """Without Dim_Market_Type seeded, rows should be skipped."""
    path = _make_processed(tmp_path, [_base_row()])
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_creates_dim_time(tmp_path, test_config, seeded_locations, seeded_market_types):
    path = _make_processed(tmp_path, [_base_row(year=2022, quarter=3)])
    NBPLoader(source_path=path, config=test_config).load()

    with get_session(seeded_locations) as session:
        t = session.query(DimTime).filter(DimTime.id == 20220701).first()
        assert t is not None
        assert t.year == 2022
        assert t.month == 7


def test_load_is_idempotent(tmp_path, test_config, seeded_locations, seeded_market_types):
    path = _make_processed(tmp_path, [_base_row()])
    loader = NBPLoader(source_path=path, config=test_config)
    loader.load()
    loader.load()

    # Only one row in DB regardless of how many times load() is called
    with get_session(seeded_locations) as session:
        assert session.query(FactBenchmarkNbp).count() == 1


def test_load_multiple_city_quarter_combinations(tmp_path, test_config, seeded_locations, seeded_market_types):
    rows = [
        _base_row(city="Warszawa", quarter=1),
        _base_row(city="Kraków", quarter=1),
        _base_row(city="Warszawa", quarter=2),
    ]
    path = _make_processed(tmp_path, rows)
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 3


def test_load_both_markets(tmp_path, test_config, seeded_locations, seeded_market_types):
    rows = [
        _base_row(market="primary"),
        _base_row(market="secondary"),
    ]
    path = _make_processed(tmp_path, rows)
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 2


def test_load_empty_parquet_returns_zero(tmp_path, test_config, seeded_locations, seeded_market_types):
    path = _make_processed(tmp_path, [])
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 0


def test_load_skips_missing_year_or_quarter(tmp_path, test_config, seeded_locations, seeded_market_types):
    rows = [
        {"year": None, "quarter": 1, "city": "Warszawa", "market": "primary",
         "avg_offer_price_m2_pln": 12_000.0, "avg_transaction_price_m2_pln": None,
         "hedonic_index": None},
    ]
    path = _make_processed(tmp_path, rows)
    count = NBPLoader(source_path=path, config=test_config).load()
    assert count == 0
