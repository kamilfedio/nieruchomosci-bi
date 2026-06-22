"""Smoke tests for dashboard data layer."""

import pandas as pd
from src.dashboard.data import (
    DashboardFilters,
    _flood_listing_count,
    compute_kpi_metrics,
    detect_listing_price_kind,
    filter_listings,
    filter_period,
    format_delta_count,
    has_data,
    kaggle_nbp_deviation,
    period_bounds_from_data,
)


def _empty_kpi_data() -> dict[str, pd.DataFrame]:
    return {name: pd.DataFrame() for name in [
        "vw_dashboard_listing_detail",
        "vw_kpi_04_flood_risk_listings",
        "vw_kpi_06_sales_velocity",
        "vw_kpi_08_price_drops",
    ]}


def test_has_data_empty():
    assert has_data(_empty_kpi_data()) is False


def test_has_data_nonempty():
    data = _empty_kpi_data()
    data["vw_dashboard_listing_detail"] = pd.DataFrame({"city": ["warszawa"]})
    assert has_data(data) is True


def test_filter_period():
    df = pd.DataFrame({"year": [2023, 2024], "quarter": [1, 2], "val": [1, 2]})
    out = filter_period(df, (2023, 1), (2023, 4))
    assert len(out) == 1


def test_filter_period_without_time_columns():
    df = pd.DataFrame({"city": ["warszawa"], "listing_count": [10]})
    out = filter_period(df, (2023, 1), (2024, 4))
    assert len(out) == 1


def test_period_bounds_from_data():
    data = {
        "vw_dashboard_listing_detail": pd.DataFrame(
            {"year": [2026, 2026], "quarter": [1, 2]}
        ),
    }
    start, end = period_bounds_from_data(data)
    assert start == (2026, 1)
    assert end == (2026, 2)


def test_flood_listing_count():
    df = pd.DataFrame(
        {
            "flood_scenario": ["Q10%", "none", "Q1%"],
        }
    )
    assert _flood_listing_count(df) == 2


def test_filter_listings_empty():
    flt = DashboardFilters(
        cities=["Warszawa"],
        market=None,
        period_start=(2023, 1),
        period_end=(2024, 4),
        flood_scenarios=["none"],
        rooms_min=1,
        rooms_max=5,
    )
    out = filter_listings(pd.DataFrame(), flt)
    assert out.empty


def test_compute_kpi_metrics_empty():
    flt = DashboardFilters(
        cities=["Warszawa"],
        market=None,
        period_start=(2023, 1),
        period_end=(2024, 4),
        flood_scenarios=["Q10%", "Q1%", "Q0.2%", "none"],
        rooms_min=1,
        rooms_max=5,
    )
    metrics = compute_kpi_metrics(_empty_kpi_data(), pd.DataFrame(), flt, pd.DataFrame())
    assert metrics.avg_price_m2 is None
    assert metrics.drop_count is None


def test_detect_rent_prices():
    df = pd.DataFrame(
        {"price_per_m2_pln": [80.0, 90.0], "total_price_pln": [2500.0, 3000.0]}
    )
    assert detect_listing_price_kind(df) == "rent"


def test_format_delta_count():
    assert format_delta_count(9) == "+9"
    assert format_delta_count(-3) == "-3"
    assert format_delta_count(0) == "0"


def test_kaggle_nbp_deviation_empty():
    flt = DashboardFilters(
        cities=["Warszawa"],
        market="primary",
        period_start=(2023, 1),
        period_end=(2024, 4),
        flood_scenarios=["none"],
        rooms_min=1,
        rooms_max=5,
    )
    result = kaggle_nbp_deviation(pd.DataFrame(), pd.DataFrame(), flt)
    assert result.empty
