"""NBP BaRN transformer.

Input: two staging parquets (*_prices, *_hedonic).
Output: one row per (year, quarter, city, market) with offer price,
transaction price, and hedonic index (qoq).
"""

from pathlib import Path

import polars as pl
from loguru import logger

from .base import BaseTransformer

_KEEP_COLS = [
    "year",
    "quarter",
    "city",
    "market",
    "avg_offer_price_m2_pln",
    "avg_transaction_price_m2_pln",
    "hedonic_index",
]


class NBPTransformer(BaseTransformer):
    @property
    def source_name(self) -> str:
        return "nbp_data"

    def read(self) -> pl.LazyFrame:
        return pl.scan_parquet(self._source_path)

    def _hedonic_path(self) -> Path:
        return self._source_path.with_name(
            self._source_path.name.replace("_prices", "_hedonic")
        )

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # ── prices: filter aggregates, pivot price_type into columns ──────────
        _price_cols = [
            "year",
            "quarter",
            "city",
            "market",
            "price_type",
            "price_per_sqm",
        ]
        prices = (
            df.filter(~pl.col("is_aggregate"))
            .select(_price_cols)
            .collect()
            .pivot(
                on="price_type",
                index=["year", "quarter", "city", "market"],
                values="price_per_sqm",
                aggregate_function="mean",
            )
        )

        rename: dict[str, str] = {}
        if "offer" in prices.columns:
            rename["offer"] = "avg_offer_price_m2_pln"
        if "transaction" in prices.columns:
            rename["transaction"] = "avg_transaction_price_m2_pln"
        prices = prices.rename(rename)

        for col in ("avg_offer_price_m2_pln", "avg_transaction_price_m2_pln"):
            if col not in prices.columns:
                prices = prices.with_columns(pl.lit(None, dtype=pl.Float64).alias(col))

        # ── hedonic: filter aggregates, keep qoq as hedonic_index ────────────
        hedonic_path = self._hedonic_path()
        hedonic: pl.DataFrame | None = None
        if hedonic_path.exists():
            hedonic = (
                pl.read_parquet(hedonic_path)
                .filter(~pl.col("is_aggregate"))
                .select(["year", "quarter", "city", "hedonic_qoq"])
                .rename({"hedonic_qoq": "hedonic_index"})
            )
        else:
            logger.warning("Hedonic parquet not found: {}", hedonic_path)

        # ── join hedonic (city-level, no market) onto prices ─────────────────
        if hedonic is not None:
            prices = prices.join(hedonic, on=["year", "quarter", "city"], how="left")
        else:
            prices = prices.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("hedonic_index")
            )

        return prices.select(_KEEP_COLS).lazy()

    def run(self) -> Path:
        from src.api.config import Config
        from src.api.quality.checker import DQChecker
        from src.api.quality.rules import nbp_rules

        logger.info("Starting NBP transformation from '{}'", self._source_path)
        lf = self.read()
        lf = self.transform(lf)

        batch_id = self._source_path.stem.replace("_prices", "")
        checker = DQChecker(
            source=self.source_name, batch_id=batch_id, rules=nbp_rules()
        )
        lf, rejected = checker.check(lf)
        checker.save_rejected(rejected, Config().database_url)

        df = lf.collect()
        logger.info("Transformation complete: {} rows", len(df))
        path = self.save(df)
        logger.info("Saved to '{}'", path)
        return path
