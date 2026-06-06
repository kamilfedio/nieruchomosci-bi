"""Unit tests for KaggleTransformer — pure logic, no FS/DB."""

import polars as pl
import pytest

from src.api.transformers.kaggle_transformer import KaggleTransformer


def _transformer(tmp_path) -> KaggleTransformer:
    return KaggleTransformer(source_path=tmp_path / "dummy.parquet")


def _base_row(**overrides) -> dict:
    row = {
        "id": "listing-001",
        "price": 500_000.0,
        "square_meters": 50.0,
        "city": "Warszawa",
        "latitude": 52.23,
        "longitude": 21.01,
        "type": "apartmentBuilding",
        "rooms": 3,
        "floor": 2,
        "floor_count": 10,
        "build_year": 2010,
        "building_material": "brick",
        "condition": "high",
        "has_parking_space": "yes",
        "has_balcony": "yes",
        "has_elevator": "no",
        "has_storage_room": "no",
        "source_file": "data/raw/kaggle/20240115_120000.csv",
    }
    row.update(overrides)
    return row


# ── _cast ─────────────────────────────────────────────────────────────────────


def test_cast_converts_price_to_float(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame({"price": ["450000.5"], "square_meters": ["62.0"],
                        "latitude": ["52.2"], "longitude": ["21.0"],
                        "rooms": ["3"], "floor": ["1"], "floor_count": ["5"],
                        "build_year": ["2005"]}).lazy()
    result = t._cast(lf).collect()
    assert result["price"][0] == pytest.approx(450_000.5)


# ── _filter_valid ─────────────────────────────────────────────────────────────


def test_filter_valid_removes_null_price(tmp_path):
    t = _transformer(tmp_path)
    rows = [_base_row(id="A", price=None), _base_row(id="B", price=400_000.0)]
    lf = pl.DataFrame(rows).lazy()
    lf = t._cast(lf)
    result = t._filter_valid(lf).collect()
    assert len(result) == 1
    assert result["id"][0] == "B"


def test_filter_valid_removes_zero_area(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(square_meters=0.0)]).lazy()
    lf = t._cast(lf)
    result = t._filter_valid(lf).collect()
    assert result.is_empty()


def test_filter_valid_removes_null_id(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(id=None)]).lazy()
    lf = t._cast(lf)
    result = t._filter_valid(lf).collect()
    assert result.is_empty()


# ── _normalize ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw_type,expected_market",
    [
        ("apartmentBuilding", "primary"),
        ("blockOfFlats", "secondary"),
        ("tenement", "secondary"),
        ("unknown_type", "unknown"),
    ],
)
def test_normalize_market_type(tmp_path, raw_type, expected_market):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(type=raw_type)]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["market_type"][0] == expected_market


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("yes", True),
        ("no", False),
        (None, None),
        ("YES", True),
    ],
)
def test_normalize_bool_cols(tmp_path, raw, expected):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(has_balcony=raw)]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["has_balcony"][0] == expected


def test_normalize_city_lowercased(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(city="  Kraków  ")]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["city_norm"][0] == "kraków"


def test_normalize_build_year_out_of_range_becomes_null(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(build_year=1800)]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["build_year"][0] is None


def test_normalize_negative_floor_becomes_null(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(floor=-1)]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["floor"][0] is None


def test_normalize_zero_rooms_becomes_null(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(rooms=0)]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["rooms"][0] is None


def test_normalize_building_material_invalid_maps_to_other(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(building_material="steel")]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    assert result["building_material_norm"][0] == "other"


def test_normalize_snapshot_date_extracted_from_source_file(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(source_file="data/raw/kaggle/20230601_090000.csv")]).lazy()
    lf = t._cast(lf)
    result = t._normalize(lf).collect()
    d = result["snapshot_date"][0]
    import datetime
    assert d == datetime.date(2023, 6, 1)


# ── _computed ─────────────────────────────────────────────────────────────────


def test_computed_price_per_m2(tmp_path):
    t = _transformer(tmp_path)
    lf = pl.DataFrame([_base_row(price=500_000.0, square_meters=50.0)]).lazy()
    lf = t._cast(lf)
    result = t._computed(lf).collect()
    assert result["price_per_m2_pln"][0] == pytest.approx(10_000.0)


# ── _enrich_flood_risk ────────────────────────────────────────────────────────


def test_enrich_flood_risk_null_when_no_zones_file(tmp_path, monkeypatch):
    """Without flood zones file, fk_flood_risk column should be null."""
    import src.api.transformers.kaggle_transformer as kt_module

    monkeypatch.setattr(kt_module, "_FLOOD_ZONES_PATH", tmp_path / "nonexistent.geojson")
    t = KaggleTransformer(source_path=tmp_path / "dummy.parquet")
    lf = pl.DataFrame([_base_row()]).lazy()
    lf = t._cast(lf)
    result = t._enrich_flood_risk(lf).collect()
    assert "fk_flood_risk" in result.columns
    assert result["fk_flood_risk"][0] is None


def test_enrich_flood_risk_outside_zone_gets_zero(tmp_path):
    """With empty flood zones list, all points get fk_flood_risk=0."""
    import json

    zones_path = tmp_path / "flood_zones.geojson"
    zones_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

    import src.api.transformers.kaggle_transformer as kt_module

    original = kt_module._FLOOD_ZONES_PATH
    kt_module._FLOOD_ZONES_PATH = zones_path
    try:
        t = KaggleTransformer(source_path=tmp_path / "dummy.parquet")
        lf = pl.DataFrame([_base_row()]).lazy()
        lf = t._cast(lf)
        result = t._enrich_flood_risk(lf).collect()
        assert result["fk_flood_risk"][0] == 0
    finally:
        kt_module._FLOOD_ZONES_PATH = original
