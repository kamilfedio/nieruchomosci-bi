"""Data quality rules — one DQRule per check, grouped by source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl


@dataclass
class DQRule:
    """A single data-quality check.

    predicate: pl.Expr that evaluates to True for VALID rows.
    severity:
      ERROR   — failing rows are dropped from the pipeline and saved to
                stg_rejected_records.
      WARNING — failing rows stay in the pipeline but are also saved to
                stg_rejected_records.
    """

    name: str
    description: str
    severity: Literal["ERROR", "WARNING"]
    predicate: pl.Expr


def kaggle_rules() -> list[DQRule]:
    return [
        DQRule(
            name="price_positive",
            description="price must be non-null and > 0",
            severity="ERROR",
            predicate=pl.col("price").is_not_null() & (pl.col("price") > 0),
        ),
        DQRule(
            name="area_positive",
            description="square_meters must be non-null and > 0",
            severity="ERROR",
            predicate=pl.col("square_meters").is_not_null()
            & (pl.col("square_meters") > 0),
        ),
        DQRule(
            name="id_not_null",
            description="listing id must not be null",
            severity="ERROR",
            predicate=pl.col("id").is_not_null(),
        ),
        DQRule(
            name="build_year_range",
            description="build_year must be in [1900, 2026] when present",
            severity="WARNING",
            predicate=pl.col("build_year").is_null()
            | ((pl.col("build_year") >= 1900) & (pl.col("build_year") <= 2026)),
        ),
    ]


def gov_data_rules() -> list[DQRule]:
    return [
        DQRule(
            name="unit_id_not_null",
            description="unit_id must not be null",
            severity="ERROR",
            predicate=pl.col("unit_id").is_not_null(),
        ),
        DQRule(
            name="price_positive",
            description="total_price_gross must be non-null and > 0",
            severity="ERROR",
            predicate=pl.col("total_price_gross").is_not_null()
            & (pl.col("total_price_gross") > 0),
        ),
        DQRule(
            name="snapshot_date_not_null",
            description="snapshot_date must not be null",
            severity="ERROR",
            predicate=pl.col("snapshot_date").is_not_null(),
        ),
    ]


def nbp_rules() -> list[DQRule]:
    return [
        DQRule(
            name="year_not_null",
            description="year must not be null",
            severity="ERROR",
            predicate=pl.col("year").is_not_null(),
        ),
        DQRule(
            name="quarter_not_null",
            description="quarter must not be null",
            severity="ERROR",
            predicate=pl.col("quarter").is_not_null(),
        ),
        DQRule(
            name="offer_price_positive",
            description="avg_offer_price_m2_pln must be > 0 when present",
            severity="WARNING",
            predicate=pl.col("avg_offer_price_m2_pln").is_null()
            | (pl.col("avg_offer_price_m2_pln") > 0),
        ),
        DQRule(
            name="transaction_price_positive",
            description="avg_transaction_price_m2_pln must be > 0 when present",
            severity="WARNING",
            predicate=pl.col("avg_transaction_price_m2_pln").is_null()
            | (pl.col("avg_transaction_price_m2_pln") > 0),
        ),
    ]


def gus_bdl_rules() -> list[DQRule]:
    return [
        DQRule(
            name="city_not_null",
            description="city must not be null",
            severity="ERROR",
            predicate=pl.col("city").is_not_null(),
        ),
        DQRule(
            name="year_not_null",
            description="year must not be null",
            severity="ERROR",
            predicate=pl.col("year").is_not_null(),
        ),
        DQRule(
            name="population_positive",
            description="population must be > 0 when present",
            severity="WARNING",
            predicate=pl.col("population").is_null() | (pl.col("population") > 0),
        ),
        DQRule(
            name="salary_positive",
            description="avg_gross_salary must be > 0 when present",
            severity="WARNING",
            predicate=pl.col("avg_gross_salary").is_null()
            | (pl.col("avg_gross_salary") > 0),
        ),
    ]
