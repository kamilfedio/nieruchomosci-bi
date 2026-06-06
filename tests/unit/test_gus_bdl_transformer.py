"""Unit tests for GUSBDLTransformer and _clean_city helper."""

import json
from pathlib import Path

import polars as pl
import pytest
from src.api.transformers.gus_bdl_transformer import GUSBDLTransformer, _clean_city

# ── _clean_city ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Powiat m. st. Warszawa", "warszawa"),
        ("Powiat m. Kraków", "kraków"),
        ("M. Łódź", "łódź"),
        ("Wrocław", "wrocław"),
        ("  Gdańsk  ", "gdańsk"),
        ("Powiat m. st. Szczecin extra", "szczecin extra"),
    ],
)
def test_clean_city(raw, expected):
    assert _clean_city(raw) == expected


# ── fixtures ──────────────────────────────────────────────────────────────────


def _write_indicator(path: Path, name: str, data: list[dict]) -> None:
    (path / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False))


def _city_entry(city_name: str, unit_id: str, years: list[tuple[int, float]]) -> dict:
    return {
        "id": unit_id,
        "name": city_name,
        "values": [{"year": y, "val": v} for y, v in years],
    }


def _setup_raw_dir(tmp_path: Path) -> Path:
    """Write minimal indicator JSON files for 2 cities."""
    raw_dir = tmp_path / "batch_20240115"
    raw_dir.mkdir()
    cities = [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2022, 1_800_000), (2023, 1_820_000)]),
        _city_entry("Powiat m. Kraków", "011212161011", [(2022, 780_000), (2023, 800_000)]),
    ]
    _write_indicator(raw_dir, "population", cities)
    _write_indicator(raw_dir, "avg_gross_salary", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2022, 8_500.0), (2023, 9_200.0)]),
        _city_entry("Powiat m. Kraków", "011212161011", [(2022, 6_100.0), (2023, 6_800.0)]),
    ])
    _write_indicator(raw_dir, "unemployment_rate", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2022, 2.1), (2023, 1.9)]),
        _city_entry("Powiat m. Kraków", "011212161011", [(2022, 3.5), (2023, 3.1)]),
    ])
    _write_indicator(raw_dir, "migration_balance", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2022, 5_000), (2023, 4_800)]),
        _city_entry("Powiat m. Kraków", "011212161011", [(2022, 1_200), (2023, 900)]),
    ])
    _write_indicator(raw_dir, "working_age_population", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2022, 1_200_000), (2023, 1_190_000)]),
        _city_entry("Powiat m. Kraków", "011212161011", [(2022, 500_000), (2023, 510_000)]),
    ])
    return raw_dir


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_produces_parquet(tmp_path):
    raw_dir = _setup_raw_dir(tmp_path)
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    assert out.exists()
    assert out.suffix == ".parquet"


def test_run_wide_format_columns(tmp_path):
    raw_dir = _setup_raw_dir(tmp_path)
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    df = pl.read_parquet(out)
    for col in ("population", "avg_gross_salary", "unemployment_rate",
                "migration_balance", "working_age_population", "city", "year"):
        assert col in df.columns, f"Missing column: {col}"


def test_run_filters_to_config_cities(tmp_path):
    raw_dir = tmp_path / "batch_20240115"
    raw_dir.mkdir()
    # Only Warszawa is in cities config; Gdańsk is unknown
    cities = [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2023, 1_820_000)]),
        _city_entry("Gdańsk_Nieznane", "XX", [(2023, 400_000)]),
    ]
    _write_indicator(raw_dir, "population", cities)
    for ind in ("avg_gross_salary", "unemployment_rate", "migration_balance", "working_age_population"):
        _write_indicator(raw_dir, ind, [])
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    df = pl.read_parquet(out)
    assert all(c == "warszawa" for c in df["city"].to_list())


def test_run_validates_population_zero(tmp_path):
    """Rows with population=0 should be nulled out."""
    raw_dir = tmp_path / "batch_val"
    raw_dir.mkdir()
    _write_indicator(raw_dir, "population", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2023, 0)])
    ])
    for ind in ("avg_gross_salary", "unemployment_rate", "migration_balance", "working_age_population"):
        _write_indicator(raw_dir, ind, [])
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    df = pl.read_parquet(out)
    assert df["population"][0] is None


def test_run_validates_unemployment_out_of_range(tmp_path):
    raw_dir = tmp_path / "batch_unemp"
    raw_dir.mkdir()
    _write_indicator(raw_dir, "population", [])
    _write_indicator(raw_dir, "avg_gross_salary", [])
    _write_indicator(raw_dir, "unemployment_rate", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2023, 150.0)])
    ])
    _write_indicator(raw_dir, "migration_balance", [])
    _write_indicator(raw_dir, "working_age_population", [])
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    df = pl.read_parquet(out)
    assert df["unemployment_rate"][0] is None


def test_run_migration_balance_can_be_negative(tmp_path):
    raw_dir = tmp_path / "batch_mig"
    raw_dir.mkdir()
    for ind in ("population", "avg_gross_salary", "unemployment_rate", "working_age_population"):
        _write_indicator(raw_dir, ind, [])
    _write_indicator(raw_dir, "migration_balance", [
        _city_entry("Powiat m. st. Warszawa", "071412865000", [(2023, -3_000)])
    ])
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    df = pl.read_parquet(out)
    assert df["migration_balance"][0] == -3_000


def test_run_empty_indicator_files_returns_empty_parquet(tmp_path):
    raw_dir = tmp_path / "batch_empty"
    raw_dir.mkdir()
    for ind in ("population", "avg_gross_salary", "unemployment_rate",
                "migration_balance", "working_age_population"):
        _write_indicator(raw_dir, ind, [])
    t = GUSBDLTransformer(source_path=raw_dir, processed_dir=tmp_path / "processed")
    out = t.run()
    df = pl.read_parquet(out)
    assert df.is_empty()
