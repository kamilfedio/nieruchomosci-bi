"""Data layer — SQL reads, filtering, KPI aggregations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.engine import Engine
from src.api.config import Config
from src.api.db.connection import build_engine, init_db
from src.api.db.views import KPI_VIEW_NAMES

from .constants import (
    CITIES,
    CITY_COORDS,
    CITY_DISPLAY,
    DEFAULT_PERIOD_END,
    DEFAULT_PERIOD_START,
)

Period = tuple[int, int]  # (year, quarter)

_MZP_GEOJSON_PATH = Path("data/processed/mzp/flood_zones.geojson")


@dataclass
class DashboardFilters:
    cities: list[str]
    market: str | None
    period_start: Period
    period_end: Period
    flood_scenarios: list[str]
    rooms_min: int
    rooms_max: int
    district: str | None = field(default=None)


ListingPriceKind = str  # "sale" | "rent"


@dataclass
class KpiMetrics:
    price_kind: ListingPriceKind
    avg_price_m2: float | None
    avg_price_m2_delta: float | None
    nbp_deviation_pct: float | None
    nbp_deviation_delta: float | None
    affordability_months: float | None
    affordability_delta: float | None
    flood_listing_count: int | None
    flood_listing_delta: int | None
    sales_velocity: int | None
    sales_velocity_delta: int | None
    drop_count: int | None
    drop_count_delta: int | None
    avg_drop_amount: float | None


def get_engine() -> Engine:
    return build_engine(Config().database_url)


def period_label(year: int, quarter: int) -> str:
    return f"{year} Q{quarter}"


def parse_period_label(label: str) -> Period:
    year_str, q_str = label.split(" Q")
    return int(year_str), int(q_str)


def period_range(start: Period, end: Period) -> list[Period]:
    periods: list[Period] = []
    year, quarter = start
    while (year, quarter) <= end:
        periods.append((year, quarter))
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1
    return periods


def all_period_labels(
    start: Period = DEFAULT_PERIOD_START,
    end: Period = DEFAULT_PERIOD_END,
) -> list[str]:
    return [period_label(y, q) for y, q in period_range(start, end)]


def period_bounds_from_df(df: pd.DataFrame) -> tuple[Period, Period] | None:
    if df.empty or "year" not in df.columns:
        return None
    years = df["year"].astype(int)
    if "quarter" in df.columns:
        keys = years * 10 + df["quarter"].astype(int)
    else:
        keys = years * 10 + 1
    min_key, max_key = int(keys.min()), int(keys.max())
    return (min_key // 10, min_key % 10), (max_key // 10, max_key % 10)


def period_bounds_from_weeks(df: pd.DataFrame) -> tuple[Period, Period] | None:
    if df.empty or "week_start" not in df.columns:
        return None
    weeks = pd.to_datetime(df["week_start"])
    start = weeks.min()
    end = weeks.max()

    def to_period(ts: pd.Timestamp) -> Period:
        return int(ts.year), (int(ts.month) - 1) // 3 + 1

    return to_period(start), to_period(end)


def period_bounds_from_data(data: dict[str, pd.DataFrame]) -> tuple[Period, Period]:
    candidates: list[tuple[Period, Period]] = []
    for key in (
        "vw_dashboard_listing_detail",
        "vw_kpi_08_price_drops",
        "vw_kpi_02_offer_vs_nbp_deviation",
        "vw_kpi_09_primary_market_share",
    ):
        bounds = period_bounds_from_df(data.get(key, pd.DataFrame()))
        if bounds is not None:
            candidates.append(bounds)
    week_bounds = period_bounds_from_weeks(
        data.get("vw_kpi_06_sales_velocity", pd.DataFrame())
    )
    if week_bounds is not None:
        candidates.append(week_bounds)
    if not candidates:
        return DEFAULT_PERIOD_START, DEFAULT_PERIOD_END
    start = min(item[0] for item in candidates)
    end = max(item[1] for item in candidates)
    return start, end


def detect_listing_price_kind(df: pd.DataFrame) -> ListingPriceKind:
    """Rent listings in Kaggle are monthly totals — ~30–150 PLN/m²."""
    if df.empty or "price_per_m2_pln" not in df.columns:
        return "sale"
    median_m2 = float(df["price_per_m2_pln"].median())  # type: ignore[arg-type]
    median_total = (
        float(df["total_price_pln"].median())  # type: ignore[arg-type]
        if "total_price_pln" in df.columns
        else 0.0
    )
    if median_m2 < 500 and median_total < 25_000:
        return "rent"
    return "sale"


def city_key(city: str) -> str:
    return city.strip().lower()


_POLISH_TO_ASCII = str.maketrans(
    "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "acelnoszzACELNOSZZ",
)


def _city_to_db(name: str) -> str:
    """Convert any city name form to ASCII lowercase as stored in DB (e.g. Kraków → krakow)."""
    return name.strip().lower().translate(_POLISH_TO_ASCII)


def city_display(city: str) -> str:
    return CITY_DISPLAY.get(city_key(city), city.strip().title())


def _selected_city_keys(cities: list[str]) -> set[str]:
    keys: set[str] = set()
    for city in cities:
        keys.add(city_key(city))
        keys.add(city_key(CITY_DISPLAY.get(city_key(city), city)))
    return keys


def filter_cities(df: pd.DataFrame, col: str, cities: list[str]) -> pd.DataFrame:
    if df.empty or len(cities) >= len(CITIES):
        return df
    keys = _selected_city_keys(cities)
    return df[df[col].map(city_key).isin(list(keys))].copy()  # type: ignore[return-value]


def filter_period(
    df: pd.DataFrame,
    start: Period,
    end: Period,
    year_col: str = "year",
    quarter_col: str = "quarter",
) -> pd.DataFrame:
    if df.empty:
        return df
    has_year = year_col in df.columns
    has_quarter = quarter_col in df.columns
    if has_year and has_quarter:
        period_key = df[year_col].astype(int) * 10 + df[quarter_col].astype(int)
        start_key = start[0] * 10 + start[1]
        end_key = end[0] * 10 + end[1]
        return df[(period_key >= start_key) & (period_key <= end_key)].copy()  # type: ignore[return-value]
    if has_year:
        years = df[year_col].astype(int)
        return df[years.between(start[0], end[0])].copy()  # type: ignore[return-value]
    return df.copy()


def filter_period_weeks(
    df: pd.DataFrame,
    start: Period,
    end: Period,
    week_col: str = "week_start",
) -> pd.DataFrame:
    if df.empty or week_col not in df.columns:
        return df
    weeks = pd.to_datetime(df[week_col])
    start_date = pd.Timestamp(year=start[0], month=(start[1] - 1) * 3 + 1, day=1)
    end_month = end[1] * 3
    end_date = pd.Timestamp(year=end[0], month=end_month, day=1) + pd.offsets.MonthEnd(
        0
    )
    return df[(weeks >= start_date) & (weeks <= end_date)].copy()  # type: ignore[return-value]


def filter_listings(df: pd.DataFrame, flt: DashboardFilters) -> pd.DataFrame:
    if df.empty:
        return df
    out = filter_cities(df, "city", flt.cities)
    out = filter_period(out, flt.period_start, flt.period_end)
    if flt.market:
        out = out[out["market_code"] == flt.market]
    if flt.flood_scenarios:
        out = out[out["flood_scenario"].isin(flt.flood_scenarios)]  # type: ignore[return-value]
    rooms_col: pd.Series = out["rooms"]  # type: ignore[assignment]
    if flt.rooms_max >= 5:
        room_mask = (rooms_col >= flt.rooms_min) | rooms_col.isna()
    else:
        room_mask = rooms_col.between(flt.rooms_min, flt.rooms_max) | rooms_col.isna()
    return out[room_mask]  # type: ignore[return-value]


def _delta_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _delta_pp(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _delta_absolute(current: int | None, previous: int | None) -> int | None:
    if current is None or previous is None:
        return None
    return current - previous


@st.cache_resource
def ensure_database_schema(_db_url: str) -> None:
    """Create tables and KPI views if missing (idempotent)."""
    init_db(build_engine(_db_url))


@st.cache_data(ttl=300)
def load_kpi_views(_db_url: str) -> dict[str, pd.DataFrame]:
    ensure_database_schema(_db_url)
    engine = build_engine(_db_url)
    data: dict[str, pd.DataFrame] = {}
    with engine.connect() as conn:
        for view in KPI_VIEW_NAMES:
            data[view] = pd.read_sql(text(f'SELECT * FROM "{view}"'), conn)
    return data


@st.cache_data(ttl=300)
def load_nbp_benchmark(_db_url: str) -> pd.DataFrame:
    ensure_database_schema(_db_url)
    engine = build_engine(_db_url)
    sql = """
        SELECT
            loc.city_norm AS city,
            t.year,
            t.quarter,
            mt.market_code,
            nbp.avg_offer_price_m2_pln,
            nbp.avg_transaction_price_m2_pln,
            nbp.hedonic_index
        FROM "Fact_Benchmark_NBP" nbp
        JOIN "Dim_Location" loc ON nbp.fk_location = loc.id
        JOIN "Dim_Time" t ON nbp.fk_time = t.id
        JOIN "Dim_Market_Type" mt ON nbp.fk_market_type = mt.id
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=300)
def load_price_drops_detail(_db_url: str) -> pd.DataFrame:
    ensure_database_schema(_db_url)
    engine = build_engine(_db_url)
    sql = """
        SELECT
            inv.developer_name,
            inv.investment_id,
            inv.city,
            loc.city_norm,
            t.date AS drop_date,
            t.year,
            t.quarter,
            fc.change_amount_pln,
            fc.unit_value_pln,
            fc.price_per_m2_pln
        FROM "Fact_Change" fc
        JOIN "Dim_Time" t ON fc.fk_time = t.id
        JOIN "Dim_Location" loc ON fc.fk_location = loc.id
        LEFT JOIN "Dim_Investment" inv ON fc.fk_investment = inv.id
        WHERE fc.is_price_drop AND fc.change_amount_pln IS NOT NULL
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=300)
def load_demographics(_db_url: str) -> pd.DataFrame:
    ensure_database_schema(_db_url)
    engine = build_engine(_db_url)
    sql = """
        SELECT city, year, avg_gross_salary
        FROM "Dim_Demographics"
        WHERE avg_gross_salary IS NOT NULL AND avg_gross_salary > 0
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


@st.cache_data(ttl=300)
def load_pipeline_stats(_db_url: str) -> pd.DataFrame:
    ensure_database_schema(_db_url)
    engine = build_engine(_db_url)
    sql = """
        SELECT 'Fact_Listing' AS source, COUNT(*)::bigint AS row_count FROM "Fact_Listing"
        UNION ALL
        SELECT 'Fact_Change', COUNT(*) FROM "Fact_Change"
        UNION ALL
        SELECT 'Fact_Benchmark_NBP', COUNT(*) FROM "Fact_Benchmark_NBP"
        UNION ALL
        SELECT 'Dim_Demographics', COUNT(*) FROM "Dim_Demographics"
        UNION ALL
        SELECT 'flood_zones', COUNT(*) FROM flood_zones
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def kaggle_nbp_deviation(
    listings: pd.DataFrame,
    nbp: pd.DataFrame,
    flt: DashboardFilters,
) -> pd.DataFrame:
    if listings.empty or nbp.empty:
        return pd.DataFrame()

    offer = listings.groupby(["city", "year", "quarter"], as_index=False).agg(
        avg_offer_m2_pln=("price_per_m2_pln", "mean")
    )
    offer["city_display"] = offer["city"].map(city_display)  # type: ignore[index,call-overload]

    nbp_f = filter_cities(nbp, "city", flt.cities)
    nbp_f = filter_period(nbp_f, flt.period_start, flt.period_end)
    nbp_f = nbp_f[nbp_f["market_code"] == (flt.market or "primary")]

    merged = offer.merge(
        nbp_f,
        left_on=["city_display", "year", "quarter"],
        right_on=["city", "year", "quarter"],
        how="inner",
    )
    if merged.empty:
        return merged

    merged["deviation_from_transaction_pct"] = (
        (merged["avg_offer_m2_pln"] - merged["avg_transaction_price_m2_pln"])
        / merged["avg_transaction_price_m2_pln"]
        * 100
    )
    return merged


def compute_kpi_metrics(
    data: dict[str, pd.DataFrame],
    nbp: pd.DataFrame,
    flt: DashboardFilters,
    demographics: pd.DataFrame,
) -> KpiMetrics:
    listings = filter_listings(data["vw_dashboard_listing_detail"], flt)
    price_kind = detect_listing_price_kind(listings)
    prev_start, prev_end = _previous_period(flt.period_end)

    prev_flt = DashboardFilters(
        cities=flt.cities,
        market=flt.market,
        period_start=prev_start,
        period_end=prev_end,
        flood_scenarios=flt.flood_scenarios,
        rooms_min=flt.rooms_min,
        rooms_max=flt.rooms_max,
    )
    prev_listings = filter_listings(data["vw_dashboard_listing_detail"], prev_flt)

    avg_price = _safe_mean(listings, "price_per_m2_pln")
    prev_avg_price = _safe_mean(prev_listings, "price_per_m2_pln")

    deviation_df = kaggle_nbp_deviation(listings, nbp, flt)
    prev_deviation_df = kaggle_nbp_deviation(prev_listings, nbp, prev_flt)
    deviation = _safe_mean(deviation_df, "deviation_from_transaction_pct")
    prev_deviation = _safe_mean(prev_deviation_df, "deviation_from_transaction_pct")

    if price_kind == "rent":
        affordability = None
        prev_affordability = None
    else:
        affordability = _affordability(listings, demographics)
        prev_affordability = _affordability(prev_listings, demographics)

    flood_count = _flood_listing_count(listings)
    prev_flood = _flood_listing_count(prev_listings)

    kpi06 = filter_cities(data["vw_kpi_06_sales_velocity"], "city", flt.cities)
    kpi06 = filter_period_weeks(kpi06, flt.period_start, flt.period_end)
    prev_kpi06 = filter_cities(data["vw_kpi_06_sales_velocity"], "city", flt.cities)
    prev_kpi06 = filter_period_weeks(prev_kpi06, prev_start, prev_end)
    sales = int(kpi06["units_sold_or_reserved"].sum()) if not kpi06.empty else None  # type: ignore[arg-type]
    prev_sales = (
        int(prev_kpi06["units_sold_or_reserved"].sum())
        if not prev_kpi06.empty
        else None
    )  # type: ignore[arg-type]

    kpi08 = _filter_kpi_view(data["vw_kpi_08_price_drops"], flt, city_col="city")
    prev_kpi08 = _filter_kpi_view(
        data["vw_kpi_08_price_drops"], prev_flt, city_col="city"
    )
    drop_count = int(kpi08["drop_count"].sum()) if not kpi08.empty else None  # type: ignore[arg-type]
    prev_drop = int(prev_kpi08["drop_count"].sum()) if not prev_kpi08.empty else None  # type: ignore[arg-type]
    avg_drop = _weighted_avg(kpi08, "avg_drop_amount_pln", "drop_count")

    return KpiMetrics(
        price_kind=price_kind,
        avg_price_m2=avg_price,
        avg_price_m2_delta=_delta_pct(avg_price, prev_avg_price),
        nbp_deviation_pct=deviation,
        nbp_deviation_delta=_delta_pp(deviation, prev_deviation),
        affordability_months=affordability,
        affordability_delta=_delta_pct(affordability, prev_affordability),
        flood_listing_count=flood_count,
        flood_listing_delta=_delta_absolute(flood_count, prev_flood),
        sales_velocity=sales,
        sales_velocity_delta=_delta_absolute(sales, prev_sales),
        drop_count=drop_count,
        drop_count_delta=_delta_absolute(drop_count, prev_drop),
        avg_drop_amount=avg_drop,
    )


def _previous_period(end: Period) -> tuple[Period, Period]:
    year, quarter = end
    quarter -= 1
    if quarter < 1:
        quarter = 4
        year -= 1
    p = (year, quarter)
    return p, p


def _safe_mean(df: pd.DataFrame, col: str) -> float | None:
    if df.empty or col not in df.columns:
        return None
    val = df[col].mean()
    return None if pd.isna(val) else float(val)  # type: ignore[arg-type]


def _latest_salary_by_city(demographics: pd.DataFrame) -> dict[str, float]:
    if demographics.empty:
        return {}
    demo = demographics.copy()
    demo["city_key"] = demo["city"].map(city_key)
    demo = demo.sort_values("year")
    latest = demo.groupby("city_key", as_index=False).last()
    return dict(zip(latest["city_key"], latest["avg_gross_salary"], strict=True))


def _affordability(listings: pd.DataFrame, demographics: pd.DataFrame) -> float | None:
    if listings.empty:
        return None
    salary_map = _latest_salary_by_city(demographics)
    if not salary_map:
        return None

    rows: list[float] = []
    for _, row in listings.iterrows():
        price_m2 = row.get("price_per_m2_pln")
        if price_m2 is None or pd.isna(price_m2):
            continue
        salary = row.get("avg_gross_salary")
        if salary is None or pd.isna(salary) or salary <= 0:
            salary = salary_map.get(city_key(str(row.get("city", ""))))
        if salary is None or salary <= 0:
            continue
        rows.append(float(price_m2) / float(salary))
    if not rows:
        return None
    return float(sum(rows) / len(rows))


def _weighted_avg(df: pd.DataFrame, val_col: str, weight_col: str) -> float | None:
    if df.empty:
        return None
    weights = df[weight_col].sum()
    if weights == 0:
        return None
    return float((df[val_col] * df[weight_col]).sum() / weights)


_FLOOD_RISK_SCENARIOS = frozenset({"Q10%", "Q1%", "Q0.2%"})


def _flood_listing_count(listings: pd.DataFrame) -> int | None:
    if listings.empty or "flood_scenario" not in listings.columns:
        return None
    risky = listings[listings["flood_scenario"].isin(list(_FLOOD_RISK_SCENARIOS))]
    return int(len(risky))


def _filter_kpi_rooms(df: pd.DataFrame, flt: DashboardFilters) -> pd.DataFrame:
    if df.empty or "rooms" not in df.columns:
        return df
    rooms: pd.Series = df["rooms"]  # type: ignore[assignment]
    if flt.rooms_max >= 5:
        return df[(rooms >= flt.rooms_min) | rooms.isna()]  # type: ignore[return-value]
    return df[rooms.between(flt.rooms_min, flt.rooms_max) | rooms.isna()]  # type: ignore[return-value]


def _filter_kpi_view(
    df: pd.DataFrame,
    flt: DashboardFilters,
    city_col: str = "city",
    *,
    apply_period: bool = True,
) -> pd.DataFrame:
    out = filter_cities(df, city_col, flt.cities)
    if apply_period:
        if "week_start" in out.columns:
            out = filter_period_weeks(out, flt.period_start, flt.period_end)
        elif "year" in out.columns or "quarter" in out.columns:
            out = filter_period(out, flt.period_start, flt.period_end)
    if "scenario" in out.columns and flt.flood_scenarios:
        out = out[out["scenario"].isin(flt.flood_scenarios)]  # type: ignore[assignment]
    if "risk_scenario" in out.columns and flt.flood_scenarios:
        out = out[out["risk_scenario"].isin(flt.flood_scenarios)]  # type: ignore[assignment]
    return out  # type: ignore[return-value]


def format_pln(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f} PLN".replace(",", " ").replace(".", ",")


def format_price_m2(value: float | None, kind: ListingPriceKind) -> str:
    if value is None:
        return "—"
    unit = "PLN/m²/mies." if kind == "rent" else "PLN/m²"
    formatted = f"{value:,.1f}".replace(",", " ").replace(".", ",")
    return f"{formatted} {unit}"


def format_delta_count(value: int | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    sign = "+" if value > 0 else ""
    return f"{sign}{value}"


def format_pct(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def format_delta(value: float | None, suffix: str = "%") -> str | None:
    if value is None:
        return None
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}{suffix}"


def has_data(data: dict[str, pd.DataFrame]) -> bool:
    return any(not df.empty for df in data.values())


def filter_price_drops_detail(df: pd.DataFrame, flt: DashboardFilters) -> pd.DataFrame:
    out = filter_cities(df, "city_norm", flt.cities)
    out = filter_period(out, flt.period_start, flt.period_end)
    if out.empty:
        return out
    return out.sort_values("change_amount_pln").head(50)


def ranking_table(
    data: dict[str, pd.DataFrame],
    nbp: pd.DataFrame,
    flt: DashboardFilters,
) -> pd.DataFrame:
    listings = filter_listings(data["vw_dashboard_listing_detail"], flt)
    if listings.empty:
        return pd.DataFrame()

    price = listings.groupby(listings["city"].map(city_display), as_index=False).agg(
        avg_price_m2_pln=("price_per_m2_pln", "mean")
    )
    aff_rows: list[dict[str, Any]] = []
    for city_name, group in listings.groupby(listings["city"].map(city_display)):
        valid = group.dropna(subset=["avg_gross_salary"])
        if valid.empty or valid["avg_gross_salary"].mean() <= 0:
            continue
        aff_rows.append(
            {
                "city": city_name,
                "months_salary_per_m2": float(
                    valid["price_per_m2_pln"].mean() / valid["avg_gross_salary"].mean()
                ),
            }
        )
    aff = pd.DataFrame(aff_rows)
    dev = kaggle_nbp_deviation(listings, nbp, flt)
    if not dev.empty:
        dev_agg = (
            dev.groupby("city_display", as_index=False)
            .agg(deviation_pct=("deviation_from_transaction_pct", "mean"))
            .rename(columns={"city_display": "city"})  # type: ignore[call-overload]
        )
    else:
        dev_agg = pd.DataFrame(columns=["city", "deviation_pct"])

    result = price.rename(columns={"city": "city"})  # type: ignore[call-overload]
    if not aff.empty:
        result = result.merge(aff, on="city", how="left")
    if not dev_agg.empty:
        result = result.merge(dev_agg, on="city", how="left")
    return result.sort_values("avg_price_m2_pln", ascending=False)


def trend_data(
    data: dict[str, pd.DataFrame],
    nbp: pd.DataFrame,
    flt: DashboardFilters,
) -> pd.DataFrame:
    listings = filter_listings(data["vw_dashboard_listing_detail"], flt)
    if listings.empty:
        return pd.DataFrame()

    offer = listings.groupby(["year", "quarter"], as_index=False).agg(
        avg_offer_m2_pln=("price_per_m2_pln", "mean")
    )
    offer["period"] = offer.apply(
        lambda r: period_label(int(r["year"]), int(r["quarter"])), axis=1
    )  # type: ignore[index,call-overload]

    nbp_f = filter_cities(nbp, "city", flt.cities)
    nbp_f = filter_period(nbp_f, flt.period_start, flt.period_end)
    nbp_f = nbp_f[nbp_f["market_code"] == (flt.market or "primary")]
    nbp_agg = nbp_f.groupby(["year", "quarter"], as_index=False).agg(
        avg_transaction_m2_pln=("avg_transaction_price_m2_pln", "mean")
    )
    nbp_agg["period"] = nbp_agg.apply(  # type: ignore[index,call-overload]
        lambda r: period_label(int(r["year"]), int(r["quarter"])), axis=1
    )

    merged = offer.merge(
        nbp_agg, on=["year", "quarter", "period"], how="outer"
    ).sort_values(  # type: ignore[arg-type]
        ["year", "quarter"]
    )
    if merged.empty:
        return merged
    merged["deviation_pct"] = (
        (merged["avg_offer_m2_pln"] - merged["avg_transaction_m2_pln"])
        / merged["avg_transaction_m2_pln"]
        * 100
    )
    return merged


def get_filtered_views(
    data: dict[str, pd.DataFrame], flt: DashboardFilters
) -> dict[str, Any]:
    return {
        "kpi02": _filter_kpi_view(
            data["vw_kpi_02_offer_vs_nbp_deviation"], flt, city_col="city"
        ),
        "kpi03": _filter_kpi_view(data["vw_kpi_03_housing_affordability"], flt),
        "kpi04": _filter_kpi_view(
            data["vw_kpi_04_flood_risk_listings"], flt, city_col="city"
        ),
        "kpi05": _filter_kpi_view(data["vw_kpi_05_flood_price_premium"], flt),
        "kpi06": filter_period_weeks(
            filter_cities(data["vw_kpi_06_sales_velocity"], "city", flt.cities),
            flt.period_start,
            flt.period_end,
        ),
        "kpi07": filter_period_weeks(
            filter_cities(data["vw_kpi_07_sold_reserved_value"], "city", flt.cities),
            flt.period_start,
            flt.period_end,
        ),
        "kpi08": _filter_kpi_view(data["vw_kpi_08_price_drops"], flt, city_col="city"),
        "kpi09": _filter_kpi_view(data["vw_kpi_09_primary_market_share"], flt),
        "kpi10": _filter_kpi_rooms(
            _filter_kpi_view(data["vw_kpi_10_amenity_premium"], flt), flt
        ),
        "listings": filter_listings(data["vw_dashboard_listing_detail"], flt),
    }


# ── Map-specific data helpers ─────────────────────────────────────────────────


@st.cache_data(ttl=3600)
def load_mzp_geojson(_path: str = str(_MZP_GEOJSON_PATH)) -> dict:
    """Load MZP flood-zone GeoJSON once per session (613 polygons, ~static data)."""
    p = Path(_path)
    if not p.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(p.read_text(encoding="utf-8"))


@st.cache_data(ttl=3600)
def load_mzp_from_db(_db_url: str, tolerance: float = 0.005) -> dict:
    """Load flood zone polygons from PostGIS with geometry simplification.

    ST_SimplifyPreserveTopology at tolerance=0.005° (~500 m) shrinks the
    384 MB flat file to a few MB, preventing WebSocket timeouts on render.
    """
    engine = build_engine(_db_url)
    sql = text("""
        SELECT scenario,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tol)) AS geom_json
        FROM flood_zones
        WHERE geom IS NOT NULL
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"tol": tolerance}).fetchall()

    features: list[dict] = []
    for scenario, geom_json in rows:
        if geom_json:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"scenario": scenario},
                    "geometry": json.loads(geom_json),
                }
            )
    return {"type": "FeatureCollection", "features": features}


@st.cache_data(ttl=300)
def load_map_points(
    _db_url: str,
    city_filter: tuple[str, ...],
    year_start: int,
    year_end: int,
    max_points: int = 3000,
) -> pd.DataFrame:
    """Sample listing points with lat/lon for the map scatter layer."""
    engine = build_engine(_db_url)
    city_clause = "AND city = ANY(:cities)" if city_filter else ""
    sql = text(
        f"""
        SELECT listing_id, city, district,
               lat, lon,
               price_per_m2_pln, area_m2, rooms,
               flood_scenario, market_code, snapshot_date
        FROM vw_dashboard_listing_detail
        WHERE lat IS NOT NULL AND lon IS NOT NULL
          AND year BETWEEN :y1 AND :y2
          AND random() < 0.5
          {city_clause}
        LIMIT :lim
        """
    )
    params: dict = {"y1": year_start, "y2": year_end, "lim": max_points}
    if city_filter:
        params["cities"] = [_city_to_db(c) for c in city_filter]
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    # Kaggle dataset uses district-level centroids — add ±50 m jitter so
    # stacked points spread out visually instead of piling into one blob.
    if not df.empty:
        rng = np.random.default_rng(seed=42)
        # 0.0005° ≈ 55 m at Polish latitudes
        df["lat"] = df["lat"] + rng.uniform(-0.0005, 0.0005, size=len(df))
        df["lon"] = df["lon"] + rng.uniform(-0.0005, 0.0005, size=len(df))

    return df


@st.cache_data(ttl=300)
def load_developer_map_points(
    _db_url: str, city_filter: tuple[str, ...]
) -> pd.DataFrame:
    """Developer investments with geocoded coordinates from geocoding_cache."""
    engine = build_engine(_db_url)
    city_clause = "AND lower(inv.city) = ANY(:cities)" if city_filter else ""
    sql = text(f"""
        SELECT
            inv.id            AS investment_pk,
            inv.city,
            inv.street,
            inv.developer_name,
            inv.investment_name,
            gc.latitude        AS lat,
            gc.longitude       AS lon,
            COUNT(fc.id)                       AS unit_count,
            AVG(fc.price_per_m2_pln)           AS avg_price_m2_pln
        FROM "Dim_Investment" inv
        JOIN geocoding_cache gc
          ON gc.cache_key = md5(lower(trim(inv.street) || ', ' || trim(inv.city) || ', polska'))
        LEFT JOIN "Fact_Change" fc
          ON fc.fk_investment = inv.id
         AND fc.price_per_m2_pln IS NOT NULL
        WHERE gc.latitude IS NOT NULL
          {city_clause}
        GROUP BY inv.id, inv.city, inv.street, inv.developer_name, inv.investment_name,
                 gc.latitude, gc.longitude
    """)
    params: dict = {}
    if city_filter:
        # Dim_Investment.city stores Polish names; lower() match suffices here
        params["cities"] = [c.strip().lower() for c in city_filter]
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


@st.cache_data(ttl=300)
def load_material_price_data(_db_url: str) -> pd.DataFrame:
    """Avg price/m² per building material and city."""
    engine = build_engine(_db_url)
    sql = text("""
        SELECT
            g.city,
            ut.building_material,
            AVG(fl.price_per_m2_pln) AS avg_price_m2_pln,
            COUNT(*) AS listing_count
        FROM "Fact_Listing" fl
        JOIN "Dim_Geo_Location" g  ON fl.fk_geo_location = g.id
        JOIN "Dim_Unit_Type"    ut ON fl.fk_unit_type    = ut.id
        WHERE fl.price_per_m2_pln IS NOT NULL
          AND ut.building_material IS NOT NULL
        GROUP BY g.city, ut.building_material
    """)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)


@st.cache_data(ttl=300)
def load_developer_summary(_db_url: str, city_filter: tuple[str, ...]) -> pd.DataFrame:
    """Top developers ranked by total sold/reserved unit value."""
    engine = build_engine(_db_url)
    city_clause = "AND lower(inv.city) = ANY(:cities)" if city_filter else ""
    sql = text(f"""
        SELECT
            inv.developer_name,
            lower(inv.city) AS city,
            COUNT(DISTINCT fc.unit_id)   AS unit_count,
            SUM(fc.unit_value_pln)       AS total_value_pln,
            AVG(fc.price_per_m2_pln)     AS avg_price_m2_pln
        FROM "Fact_Change" fc
        JOIN "Dim_Investment" inv ON fc.fk_investment = inv.id
        WHERE fc.unit_value_pln IS NOT NULL
          AND inv.developer_name IS NOT NULL
          {city_clause}
        GROUP BY inv.developer_name, lower(inv.city)
        ORDER BY total_value_pln DESC
        LIMIT 20
    """)
    params: dict = {}
    if city_filter:
        params["cities"] = [c.strip().lower() for c in city_filter]
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def build_city_kpi(
    kpi_data: dict[str, pd.DataFrame],
    kpi_col: str,
    flt: DashboardFilters,
) -> pd.DataFrame:
    """Aggregate selected KPI per city from pre-loaded views. Returns city + kpi_value + listing_count + lat + lon."""
    view_map = {
        "avg_price_m2": ("vw_kpi_01_avg_offer_price_m2", "avg_price_m2_pln", "city"),
        "months_salary_per_m2": (
            "vw_kpi_03_housing_affordability",
            "months_salary_per_m2",
            "city",
        ),
        "deviation_pct": (
            "vw_kpi_02_offer_vs_nbp_deviation",
            "deviation_from_transaction_pct",
            "city",
        ),
        "flood_premium_pct": (
            "vw_kpi_05_flood_price_premium",
            "flood_premium_pct",
            "city",
        ),
    }
    if kpi_col not in view_map:
        return pd.DataFrame()

    view_name, metric_col, city_col = view_map[kpi_col]
    df = kpi_data.get(view_name, pd.DataFrame())
    if df.empty or metric_col not in df.columns:
        return pd.DataFrame()

    df = filter_cities(df, city_col, flt.cities)
    df = filter_period(df, flt.period_start, flt.period_end)

    agg = (
        df.groupby(city_col, as_index=False)
        .agg(
            kpi_value=(metric_col, "mean"),
            listing_count=(metric_col, "count"),
        )
        .rename(columns={city_col: "city"})  # type: ignore[call-overload]
    )

    # Attach city centre coordinates
    agg["lat"] = agg["city"].map(
        lambda c: CITY_COORDS.get(city_key(c), (None, None))[0]
    )
    agg["lon"] = agg["city"].map(
        lambda c: CITY_COORDS.get(city_key(c), (None, None))[1]
    )
    return agg.dropna(subset=["lat", "lon"])


@st.cache_data(ttl=600)
def load_dimension_stats(_db_url: str) -> dict[str, pd.DataFrame]:
    """Aggregated describe-style statistics for each dimension table."""
    engine = build_engine(_db_url)

    queries: dict[str, str] = {
        "geo": """
            SELECT
                city,
                COUNT(*)                        AS lokalizacje,
                COUNT(DISTINCT district)        AS dzielnice,
                ROUND(AVG(lat_r)::numeric, 3)   AS avg_lat,
                ROUND(AVG(lon_r)::numeric, 3)   AS avg_lon,
                ROUND(MIN(lat_r)::numeric, 3)   AS min_lat,
                ROUND(MAX(lat_r)::numeric, 3)   AS max_lat
            FROM "Dim_Geo_Location"
            WHERE lat_r IS NOT NULL
            GROUP BY city
            ORDER BY lokalizacje DESC
        """,
        "unit_type": """
            SELECT
                rooms                                            AS pokoje,
                COUNT(*)                                         AS count,
                ROUND(AVG(floor)::numeric, 1)                   AS avg_pietro,
                ROUND(AVG(build_year)::numeric)                 AS avg_rok_budowy,
                ROUND(100.0 * COUNT(*) FILTER (WHERE has_balcony)   / COUNT(*), 1) AS pct_balkon,
                ROUND(100.0 * COUNT(*) FILTER (WHERE has_elevator)  / COUNT(*), 1) AS pct_winda,
                ROUND(100.0 * COUNT(*) FILTER (WHERE has_parking)   / COUNT(*), 1) AS pct_parking,
                ROUND(100.0 * COUNT(*) FILTER (WHERE has_security)  / COUNT(*), 1) AS pct_ochrona
            FROM "Dim_Unit_Type"
            WHERE rooms IS NOT NULL
            GROUP BY rooms
            ORDER BY rooms
        """,
        "demographics": """
            SELECT
                city                                            AS miasto,
                MIN(year)                                       AS rok_od,
                MAX(year)                                       AS rok_do,
                ROUND(AVG(avg_gross_salary)::numeric)           AS avg_wynagrodzenie,
                MAX(population)                                 AS max_ludnosc,
                ROUND(AVG(unemployment_rate)::numeric, 1)       AS avg_bezrobocie_pct
            FROM "Dim_Demographics"
            GROUP BY city
            ORDER BY avg_wynagrodzenie DESC NULLS LAST
        """,
        "investment": """
            SELECT
                lower(city)                             AS miasto,
                COUNT(DISTINCT developer_name)          AS deweloperzy,
                COUNT(DISTINCT investment_id)           AS inwestycje,
                COUNT(*)                                AS wiersze_scd2
            FROM "Dim_Investment"
            WHERE city IS NOT NULL
            GROUP BY lower(city)
            ORDER BY deweloperzy DESC
        """,
        "time_range": """
            SELECT
                MIN(date)::text     AS min_date,
                MAX(date)::text     AS max_date,
                COUNT(*)            AS day_count,
                MIN(year)           AS min_year,
                MAX(year)           AS max_year
            FROM "Dim_Time"
        """,
        "flood_risk": """
            SELECT
                fr.scenario,
                fr.risk_class,
                fr.numeric_risk_class,
                ROUND(fr.depth_m::numeric, 2)   AS avg_depth_m,
                COUNT(fz.id)                     AS polygon_count
            FROM "Dim_Flood_Risk" fr
            LEFT JOIN flood_zones fz ON fz.fk_flood_risk = fr.id
            GROUP BY fr.scenario, fr.risk_class, fr.numeric_risk_class, fr.depth_m
            ORDER BY fr.numeric_risk_class
        """,
    }

    result: dict[str, pd.DataFrame] = {}
    with engine.connect() as conn:
        for key, sql in queries.items():
            try:
                result[key] = pd.read_sql(text(sql), conn)
            except Exception:  # noqa: BLE001
                result[key] = pd.DataFrame()
    return result
