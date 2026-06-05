"""Target schema for unified gov_data staging output"""

import polars as pl

# Minimum required columns after normalization.
# All other source columns are dropped.
TARGET_SCHEMA: dict[str, pl.DataType] = {
    "unit_id": pl.String(),
    "investment_id": pl.String(),
    "developer_name": pl.String(),
    "city": pl.String(),
    "street": pl.String(),
    "total_price_gross": pl.Float64(),
    "usable_area_m2": pl.Float64(),
    "unit_status": pl.String(),
    "updated_at": pl.String(),
}

TARGET_COLUMNS = list(TARGET_SCHEMA.keys())
