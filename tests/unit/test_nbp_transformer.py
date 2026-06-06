"""Unit tests for NBPTransformer."""

import polars as pl
import pytest
from src.api.transformers.nbp_transformer import NBPTransformer


def _make_prices_parquet(tmp_path, rows: list[dict]) -> "tuple[object, object]":
    """Write prices + empty hedonic parquet, return (transformer, prices_path)."""
    prices_path = tmp_path / "batch_prices.parquet"
    hedonic_path = tmp_path / "batch_hedonic.parquet"
    pl.DataFrame(rows).write_parquet(prices_path)
    # Minimal hedonic with no rows so hedonic_index is always null
    pl.DataFrame(
        {
            "year": pl.Series([], dtype=pl.Int32),
            "quarter": pl.Series([], dtype=pl.Int32),
            "city": pl.Series([], dtype=pl.String),
            "hedonic_qoq": pl.Series([], dtype=pl.Float64),
            "is_aggregate": pl.Series([], dtype=pl.Boolean),
        }
    ).write_parquet(hedonic_path)
    t = NBPTransformer(source_path=prices_path)
    return t, prices_path


def _price_row(**overrides) -> dict:
    row = {
        "year": 2023,
        "quarter": 1,
        "city": "Warszawa",
        "market": "primary",
        "price_type": "offer",
        "price_per_sqm": 12_000.0,
        "is_aggregate": False,
    }
    row.update(overrides)
    return row


# ── transform ─────────────────────────────────────────────────────────────────


def test_transform_pivots_offer_and_transaction(tmp_path):
    rows = [
        _price_row(price_type="offer", price_per_sqm=12_000.0),
        _price_row(price_type="transaction", price_per_sqm=11_500.0),
    ]
    t, _ = _make_prices_parquet(tmp_path, rows)
    lf = t.read()
    result = t.transform(lf).collect()
    assert len(result) == 1
    assert result["avg_offer_price_m2_pln"][0] == pytest.approx(12_000.0)
    assert result["avg_transaction_price_m2_pln"][0] == pytest.approx(11_500.0)


def test_transform_skips_aggregate_rows(tmp_path):
    rows = [
        _price_row(city="Warszawa", is_aggregate=False),
        _price_row(city="POLSKA", is_aggregate=True),
    ]
    t, _ = _make_prices_parquet(tmp_path, rows)
    lf = t.read()
    result = t.transform(lf).collect()
    cities = result["city"].to_list()
    assert "POLSKA" not in cities
    assert "Warszawa" in cities


def test_transform_multiple_cities_and_quarters(tmp_path):
    rows = [
        _price_row(city="Warszawa", quarter=1, price_type="offer", price_per_sqm=12_000.0),
        _price_row(city="Kraków", quarter=1, price_type="offer", price_per_sqm=9_000.0),
        _price_row(city="Warszawa", quarter=2, price_type="offer", price_per_sqm=12_500.0),
    ]
    t, _ = _make_prices_parquet(tmp_path, rows)
    lf = t.read()
    result = t.transform(lf).collect()
    assert len(result) == 3


def test_transform_missing_offer_column_is_null(tmp_path):
    """If only transaction prices exist, offer column should be null."""
    rows = [_price_row(price_type="transaction", price_per_sqm=11_000.0)]
    t, _ = _make_prices_parquet(tmp_path, rows)
    lf = t.read()
    result = t.transform(lf).collect()
    assert "avg_offer_price_m2_pln" in result.columns
    assert result["avg_offer_price_m2_pln"][0] is None


def test_transform_hedonic_joined_when_file_exists(tmp_path):
    prices_path = tmp_path / "run_prices.parquet"
    hedonic_path = tmp_path / "run_hedonic.parquet"
    pl.DataFrame([_price_row()]).write_parquet(prices_path)
    pl.DataFrame(
        [{"year": 2023, "quarter": 1, "city": "Warszawa",
          "hedonic_qoq": 1.02, "is_aggregate": False}]
    ).write_parquet(hedonic_path)
    t = NBPTransformer(source_path=prices_path)
    lf = t.read()
    result = t.transform(lf).collect()
    assert result["hedonic_index"][0] == pytest.approx(1.02)


def test_transform_output_columns(tmp_path):
    t, _ = _make_prices_parquet(tmp_path, [_price_row()])
    lf = t.read()
    result = t.transform(lf).collect()
    expected = {
        "year", "quarter", "city", "market",
        "avg_offer_price_m2_pln", "avg_transaction_price_m2_pln", "hedonic_index",
    }
    assert expected.issubset(set(result.columns))
