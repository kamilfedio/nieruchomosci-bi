"""Gov data transformer — steps 1-5 (pure Polars, no DB).

Steps:
  1. Normalize  → city_norm, status_norm
  2. LAG        → prev_price, prev_status_norm  (sorted by snapshot_date within unit)
  3. Flags      → is_price_changed, is_status_changed, is_price_drop
  4. Computed   → price_per_m2_pln, change_amount_pln, unit_value_pln
  5. Filter     → keep only rows where is_price_changed OR is_status_changed
"""

from pathlib import Path

import polars as pl
from loguru import logger

from .base import BaseTransformer

_LAG_GROUP = ["developer_name", "investment_id", "unit_id"]

_STATUS_MAP: dict[str, str] = {
    "dostępny": "AVAILABLE",
    "dostepny": "AVAILABLE",
    "wolny": "AVAILABLE",
    "w sprzedaży": "AVAILABLE",
    "w sprzedazy": "AVAILABLE",
    "available": "AVAILABLE",
    "zarezerwowany": "RESERVED",
    "rezerwacja": "RESERVED",
    "reserved": "RESERVED",
    "sprzedany": "SOLD",
    "sprzedane": "SOLD",
    "sold": "SOLD",
    "wycofany": "WITHDRAWN",
    "withdrawn": "WITHDRAWN",
    "mieszkanie": "AVAILABLE",  # 6-col files encode type, not status
    "dom": "AVAILABLE",
}


def _build_status_norm_expr() -> pl.Expr:
    lowered = pl.col("unit_status").str.to_lowercase().str.strip_chars()
    expr = pl.lit("UNKNOWN")
    for src, tgt in _STATUS_MAP.items():
        expr = pl.when(lowered == src).then(pl.lit(tgt)).otherwise(expr)
    null_case = pl.when(pl.col("unit_status").is_null()).then(pl.lit("UNKNOWN"))
    return null_case.otherwise(expr)


class GovDataTransformer(BaseTransformer):
    """Reads all staged gov_data parquets, produces change-only fact rows."""

    @property
    def source_name(self) -> str:
        return "gov_data"

    def read(self) -> pl.LazyFrame:
        return pl.scan_parquet(str(self._source_path / "*.parquet"))

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        df = self._filter_valid(df)
        df = self._normalize(df)  # step 1
        df = self._lag(df)  # step 2
        df = self._flags(df)  # step 3
        df = self._computed(df)  # step 4
        df = self._filter_changes(df)  # step 5
        return df

    # ── Step 0: drop garbage rows ────────────────────────────────────────────

    def _filter_valid(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(
            pl.col("unit_id").is_not_null()
            & pl.col("total_price_gross").is_not_null()
            & pl.col("snapshot_date").is_not_null()
        )

    # ── Step 1: Normalize ────────────────────────────────────────────────────

    def _normalize(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            pl.col("city").str.strip_chars().str.to_titlecase().alias("city_norm"),
            _build_status_norm_expr().alias("status_norm"),
        )

    # ── Step 2: LAG ──────────────────────────────────────────────────────────

    def _lag(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.sort([*_LAG_GROUP, "snapshot_date"]).with_columns(
            pl.col("total_price_gross").shift(1).over(_LAG_GROUP).alias("prev_price"),
            pl.col("status_norm").shift(1).over(_LAG_GROUP).alias("prev_status_norm"),
        )

    # ── Step 3: Flags ────────────────────────────────────────────────────────

    def _flags(self, df: pl.LazyFrame) -> pl.LazyFrame:
        has_prev = pl.col("prev_price").is_not_null()
        return df.with_columns(
            (has_prev & (pl.col("total_price_gross") != pl.col("prev_price"))).alias(
                "is_price_changed"
            ),
            (
                pl.col("prev_status_norm").is_not_null()
                & (pl.col("status_norm") != pl.col("prev_status_norm"))
            ).alias("is_status_changed"),
            (has_prev & (pl.col("total_price_gross") < pl.col("prev_price"))).alias(
                "is_price_drop"
            ),
        )

    # ── Step 4: Computed ─────────────────────────────────────────────────────

    def _computed(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            (pl.col("total_price_gross") / pl.col("usable_area_m2")).alias(
                "price_per_m2_pln"
            ),
            (pl.col("total_price_gross") - pl.col("prev_price")).alias(
                "change_amount_pln"
            ),
            pl.col("total_price_gross").alias("unit_value_pln"),
        )

    # ── Step 5: Filter ───────────────────────────────────────────────────────

    def _filter_changes(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(pl.col("is_price_changed") | pl.col("is_status_changed"))

    # ── Override run — window functions require collect, not streaming ────────

    def run(self) -> Path:
        logger.info("Starting gov_data transformation from '{}'", self._source_path)
        lf = self.read()
        lf = self.transform(lf)
        df = lf.collect()
        logger.info("Transformation complete: {} change rows", len(df))
        path = self.save(df)
        logger.info("Saved to '{}'", path)
        return path


if __name__ == "__main__":
    staging_dir = Path("data/staging/gov_data")
    transformer = GovDataTransformer(source_path=staging_dir)
    transformer.run()
