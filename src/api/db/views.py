"""KPI SQL views — applied on init_db after tables exist."""

from pathlib import Path

from sqlalchemy import Engine, text

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_VIEWS_SQL_PATH = _PROJECT_ROOT / "config" / "postgres" / "views" / "kpi_views.sql"

KPI_VIEW_NAMES: tuple[str, ...] = (
    "vw_dev_latest_unit",
    "vw_kpi_01_avg_offer_price_m2",
    "vw_kpi_02_offer_vs_nbp_deviation",
    "vw_kpi_03_housing_affordability",
    "vw_kpi_04_flood_risk_listings",
    "vw_kpi_05_flood_price_premium",
    "vw_kpi_06_sales_velocity",
    "vw_kpi_07_sold_reserved_value",
    "vw_kpi_08_price_drops",
    "vw_kpi_09_primary_market_share",
    "vw_kpi_10_amenity_premium",
    "vw_dashboard_listing_detail",
)


def drop_kpi_views(engine: Engine) -> None:
    """Drop KPI views (required before table drop_all in tests)."""
    with engine.begin() as conn:
        for view in reversed(KPI_VIEW_NAMES):
            conn.execute(text(f'DROP VIEW IF EXISTS "{view}" CASCADE'))


def ensure_kpi_views(engine: Engine) -> None:
    """Create or replace all KPI dashboard views."""
    sql = _VIEWS_SQL_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))
