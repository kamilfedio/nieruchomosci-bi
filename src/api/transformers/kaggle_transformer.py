"""Kaggle transformer — normalization of apartment listings."""

import polars as pl

from .base import BaseTransformer

_MARKET_TYPE_MAP = {
    "apartmentBuilding": "primary",
    "blockOfFlats": "secondary",
    "tenement": "secondary",
}

_MATERIAL_VALID = {"brick", "concrete", "wood", "other"}

_CONDITION_MAP = {
    "high": "high",
    "medium": "medium",
    "low": "low",
}

_BOOL_COLS = [
    "has_parking_space",
    "has_balcony",
    "has_elevator",
    "has_storage_room",
]

_INT_COLS = ["rooms", "floor", "floor_count", "build_year"]


def _bool_expr(col: str) -> pl.Expr:
    lower = pl.col(col).cast(pl.String).str.to_lowercase().str.strip_chars()
    return (
        pl.when(lower == "yes")
        .then(True)
        .when(lower == "no")
        .then(False)
        .otherwise(None)
    )


class KaggleTransformer(BaseTransformer):
    @property
    def source_name(self) -> str:
        return "kaggle"

    def read(self) -> pl.LazyFrame:
        return pl.scan_parquet(self._source_path)

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        from src.api.config import Config
        from src.api.quality.checker import DQChecker
        from src.api.quality.rules import kaggle_rules

        df = self._cast(df)

        checker = DQChecker(
            source=self.source_name,
            batch_id=self._source_path.stem,
            rules=kaggle_rules(),
        )
        df, rejected = checker.check(df)
        checker.save_rejected(rejected, Config().database_url)

        df = self._filter_valid(df)
        df = self._normalize(df)
        df = self._computed(df)
        return df

    def _cast(self, df: pl.LazyFrame) -> pl.LazyFrame:
        int_exprs = [pl.col(c).cast(pl.Int32, strict=False).alias(c) for c in _INT_COLS]
        return df.with_columns(
            pl.col("price").cast(pl.Float64, strict=False),
            pl.col("square_meters").cast(pl.Float64, strict=False),
            pl.col("latitude").cast(pl.Float64, strict=False),
            pl.col("longitude").cast(pl.Float64, strict=False),
            *int_exprs,
        )

    def _filter_valid(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(
            pl.col("price").is_not_null()
            & (pl.col("price") > 0)
            & pl.col("square_meters").is_not_null()
            & (pl.col("square_meters") > 0)
            & pl.col("id").is_not_null()
        )

    def _normalize(self, df: pl.LazyFrame) -> pl.LazyFrame:
        city_lower = pl.col("city").str.to_lowercase().str.strip_chars()

        market_type_expr = pl.lit("unknown")
        for src, tgt in _MARKET_TYPE_MAP.items():
            market_type_expr = (
                pl.when(pl.col("type") == src)
                .then(pl.lit(tgt))
                .otherwise(market_type_expr)
            )

        material_lower = (
            pl.col("building_material").str.to_lowercase().str.strip_chars()
        )
        material_norm = (
            pl.when(material_lower.is_in(list(_MATERIAL_VALID)))
            .then(material_lower)
            .when(pl.col("building_material").is_null())
            .then(pl.lit("unknown"))
            .otherwise(pl.lit("other"))
        )

        condition_norm = pl.lit("unknown")
        for src, tgt in _CONDITION_MAP.items():
            condition_norm = (
                pl.when(pl.col("condition").str.to_lowercase() == src)
                .then(pl.lit(tgt))
                .otherwise(condition_norm)
            )

        build_year = (
            pl.when(
                pl.col("build_year").is_not_null()
                & (pl.col("build_year") >= 1900)
                & (pl.col("build_year") <= 2026)
            )
            .then(pl.col("build_year"))
            .otherwise(None)
        )

        floor = (
            pl.when(pl.col("floor").is_not_null() & (pl.col("floor") >= 0))
            .then(pl.col("floor"))
            .otherwise(None)
        )

        rooms = (
            pl.when(pl.col("rooms").is_not_null() & (pl.col("rooms") > 0))
            .then(pl.col("rooms"))
            .otherwise(None)
        )

        floor_count = (
            pl.when(pl.col("floor_count").is_not_null() & (pl.col("floor_count") > 0))
            .then(pl.col("floor_count"))
            .otherwise(None)
        )

        snapshot_date = (
            pl.col("source_file")
            .str.extract(r"(\d{8})_\d{6}", 1)
            .str.strptime(pl.Date, "%Y%m%d", strict=False)
        )

        bool_exprs = [_bool_expr(c).alias(c) for c in _BOOL_COLS]

        return df.with_columns(
            city_lower.alias("city_norm"),
            market_type_expr.alias("market_type"),
            material_norm.alias("building_material_norm"),
            condition_norm.alias("condition_norm"),
            build_year.alias("build_year"),
            floor.alias("floor"),
            rooms.alias("rooms"),
            floor_count.alias("floor_count"),
            snapshot_date.alias("snapshot_date"),
            *bool_exprs,
        )

    def _computed(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            (pl.col("price") / pl.col("square_meters")).alias("price_per_m2_pln"),
        )
