"""Unit tests for GovDataTransformer — pure logic, no DB/Gemini."""

import polars as pl
import pytest
from src.api.transformers.gov_data_transformer import (
    GovDataTransformer,
    _build_status_norm_expr,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _base_df(**overrides) -> pl.LazyFrame:
    """Minimal valid row after Gemini mapping + enrichment."""
    row: dict = {
        "unit_id": "U1",
        "total_price_gross": 500_000.0,
        "usable_area_m2": 50.0,
        "developer_name": "Dev S.A.",
        "investment_id": "INV-1",
        "city": "Warszawa",
        "unit_status": "dostępny",
        "snapshot_date": "2024-01-15",
        "regon": "123456789",
        "street": "ul. Testowa 1",
        "download_url": "http://example.com/file.csv",
    }
    row.update(overrides)
    return pl.DataFrame(row).lazy()


def _transformer(tmp_path) -> GovDataTransformer:
    from src.api.config import Config

    cfg = Config(
        database_url="postgresql+psycopg2://airflow:airflow@localhost:5432/nieruchomosci_test",
        gemini_api_key="",
        bdl_api_key="",
    )
    return GovDataTransformer(source_path=tmp_path, config=cfg)


# ── _cast_types ───────────────────────────────────────────────────────────────


def test_cast_types_converts_comma_decimal(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "total_price_gross": ["450 000,00"],
            "usable_area_m2": ["62,5"],
        }
    ).lazy()
    result = t._cast_types(lf).collect()
    # comma → dot → Float64; space is NOT removed (polars strict=False → null)
    # actual behaviour: "450 000,00" → "450 000.00" → strict=False → null
    assert result["usable_area_m2"][0] == pytest.approx(62.5)


def test_cast_types_plain_float_unchanged(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {"total_price_gross": ["550000.0"], "usable_area_m2": ["45.0"]}
    ).lazy()
    result = t._cast_types(lf).collect()
    assert result["total_price_gross"][0] == pytest.approx(550_000.0)
    assert result["usable_area_m2"][0] == pytest.approx(45.0)


# ── _normalize_prices ─────────────────────────────────────────────────────────


def test_normalize_prices_fixes_per_m2_value(tmp_path):
    """price=500, area=50 → implied 10 PLN/m² (< 1000) → multiply → 25_000."""
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {"total_price_gross": [500.0], "usable_area_m2": [50.0]}
    ).lazy()
    result = t._normalize_prices(lf).collect()
    assert result["total_price_gross"][0] == pytest.approx(25_000.0)


def test_normalize_prices_leaves_correct_total_unchanged(tmp_path):
    """price=500_000, area=50 → implied 10_000 PLN/m² (> 1000) → unchanged."""
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {"total_price_gross": [500_000.0], "usable_area_m2": [50.0]}
    ).lazy()
    result = t._normalize_prices(lf).collect()
    assert result["total_price_gross"][0] == pytest.approx(500_000.0)


def test_normalize_prices_skips_null_area(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {"total_price_gross": [800.0], "usable_area_m2": [None]}
    ).lazy()
    result = t._normalize_prices(lf).collect()
    assert result["total_price_gross"][0] == pytest.approx(800.0)


# ── _filter_valid ─────────────────────────────────────────────────────────────


def test_filter_valid_removes_null_unit_id(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "unit_id": [None, "U2"],
            "total_price_gross": [500_000.0, 400_000.0],
            "snapshot_date": ["2024-01-01", "2024-01-01"],
        }
    ).lazy()
    result = t._filter_valid(lf).collect()
    assert len(result) == 1
    assert result["unit_id"][0] == "U2"


def test_filter_valid_removes_zero_price(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "unit_id": ["U1", "U2"],
            "total_price_gross": [0.0, 300_000.0],
            "snapshot_date": ["2024-01-01", "2024-01-01"],
        }
    ).lazy()
    result = t._filter_valid(lf).collect()
    assert len(result) == 1


def test_filter_valid_removes_null_snapshot_date(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "unit_id": ["U1"],
            "total_price_gross": [500_000.0],
            "snapshot_date": [None],
        }
    ).lazy()
    result = t._filter_valid(lf).collect()
    assert result.is_empty()


# ── _build_status_norm_expr ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("dostępny", "AVAILABLE"),
        ("DOSTĘPNY", "AVAILABLE"),
        ("wolny", "AVAILABLE"),
        ("w sprzedaży", "AVAILABLE"),
        ("zarezerwowany", "RESERVED"),
        ("sprzedany", "SOLD"),
        ("wycofany", "WITHDRAWN"),
        ("sold", "SOLD"),
        ("nieznany_status", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_status_norm(raw, expected):
    df = pl.DataFrame({"unit_status": pl.Series([raw], dtype=pl.String)})
    result = df.with_columns(_build_status_norm_expr().alias("status_norm"))
    assert result["status_norm"][0] == expected


# ── _lag ──────────────────────────────────────────────────────────────────────


def test_lag_computes_prev_price_within_unit(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "developer_name": ["Dev", "Dev"],
            "investment_id": ["INV", "INV"],
            "unit_id": ["U1", "U1"],
            "snapshot_date": ["2024-01-01", "2024-02-01"],
            "total_price_gross": [500_000.0, 520_000.0],
            "status_norm": ["AVAILABLE", "AVAILABLE"],
        }
    ).lazy()
    result = t._lag(lf).collect().sort("snapshot_date")
    assert result["prev_price"][0] is None
    assert result["prev_price"][1] == pytest.approx(500_000.0)


def test_lag_does_not_mix_different_units(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "developer_name": ["Dev", "Dev"],
            "investment_id": ["INV", "INV"],
            "unit_id": ["U1", "U2"],
            "snapshot_date": ["2024-01-01", "2024-01-01"],
            "total_price_gross": [500_000.0, 600_000.0],
            "status_norm": ["AVAILABLE", "AVAILABLE"],
        }
    ).lazy()
    result = t._lag(lf).collect()
    assert all(v is None for v in result["prev_price"].to_list())


# ── _flags ────────────────────────────────────────────────────────────────────


def test_flags_first_snapshot_when_no_prev(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "total_price_gross": [500_000.0],
            "prev_price": [None],
            "status_norm": ["AVAILABLE"],
            "prev_status_norm": [None],
        }
    ).lazy()
    result = t._flags(lf).collect()
    assert result["is_first_snapshot"][0] is True
    assert result["is_price_changed"][0] is False
    assert result["is_status_changed"][0] is False


def test_flags_price_changed(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "total_price_gross": [520_000.0],
            "prev_price": [500_000.0],
            "status_norm": ["AVAILABLE"],
            "prev_status_norm": ["AVAILABLE"],
        }
    ).lazy()
    result = t._flags(lf).collect()
    assert result["is_price_changed"][0] is True
    assert result["is_price_drop"][0] is False
    assert result["is_first_snapshot"][0] is False


def test_flags_price_drop(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "total_price_gross": [480_000.0],
            "prev_price": [500_000.0],
            "status_norm": ["AVAILABLE"],
            "prev_status_norm": ["AVAILABLE"],
        }
    ).lazy()
    result = t._flags(lf).collect()
    assert result["is_price_drop"][0] is True
    assert result["is_price_changed"][0] is True


def test_flags_status_changed(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "total_price_gross": [500_000.0],
            "prev_price": [500_000.0],
            "status_norm": ["SOLD"],
            "prev_status_norm": ["AVAILABLE"],
        }
    ).lazy()
    result = t._flags(lf).collect()
    assert result["is_status_changed"][0] is True
    assert result["is_price_changed"][0] is False


# ── _filter_changes ───────────────────────────────────────────────────────────


def test_filter_changes_drops_unchanged_rows(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "is_first_snapshot": [False, True, False],
            "is_price_changed": [False, False, True],
            "is_status_changed": [False, False, False],
        }
    ).lazy()
    result = t._filter_changes(lf).collect()
    assert len(result) == 2


# ── _computed ─────────────────────────────────────────────────────────────────


def test_computed_price_per_m2(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame(
        {
            "total_price_gross": [500_000.0],
            "usable_area_m2": [50.0],
            "prev_price": [None],
        }
    ).lazy()
    result = t._computed(lf).collect()
    assert result["price_per_m2_pln"][0] == pytest.approx(10_000.0)
    assert result["unit_value_pln"][0] == pytest.approx(500_000.0)
