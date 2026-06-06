"""Gov data transformer — all business logic for gov_data.

Reads raw staged parquets (original snake_case columns) and applies:
  1. Gemini column mapping  → TARGET_SCHEMA per file
  2. DB enrichment          → fill developer_name, city, snapshot_date, regon
  3. Normalize              → city_norm, status_norm
  4. Type casting           → comma-decimal → Float64
  5. LAG                    → prev_price, prev_status_norm
  6. Flags                  → is_price_changed, is_status_changed, is_price_drop
  7. Computed               → price_per_m2_pln, change_amount_pln, unit_value_pln
  8. Filter                 → keep only rows where is_price_changed OR is_status_changed
"""

from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import DeveloperFile
from src.api.staging.column_mapper import map_columns
from src.api.staging.schema import TARGET_COLUMNS, TARGET_SCHEMA

from .base import BaseTransformer

_LAG_GROUP = ["developer_name", "investment_id", "unit_id"]
_TECHNICAL_COLS = {"batch_id", "loaded_at", "source_file", "download_url"}

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
    "mieszkanie": "AVAILABLE",
    "dom": "AVAILABLE",
}


@dataclass
class _FileMeta:
    developer_name: str | None
    institution_city: str | None
    data_date: str | None
    regon: str | None


def _fetch_metadata(download_url: str, config: Config) -> _FileMeta | None:
    engine = build_engine(config.database_url)
    init_db(engine)
    with get_session(engine) as session:
        row: DeveloperFile | None = (
            session.query(DeveloperFile)
            .filter(DeveloperFile.download_url == download_url)
            .first()
        )
        if row is None:
            return None
        return _FileMeta(
            developer_name=row.developer_name,
            institution_city=row.institution_city,
            data_date=row.data_date,
            regon=row.regon,
        )


def _build_status_norm_expr() -> pl.Expr:
    lowered = pl.col("unit_status").str.to_lowercase().str.strip_chars()
    expr = pl.lit("UNKNOWN")
    for src, tgt in _STATUS_MAP.items():
        expr = pl.when(lowered == src).then(pl.lit(tgt)).otherwise(expr)
    null_case = pl.when(pl.col("unit_status").is_null()).then(pl.lit("UNKNOWN"))
    return null_case.otherwise(expr)


class GovDataTransformer(BaseTransformer):
    def __init__(self, *args, config: Config | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._config = config or Config()

    @property
    def source_name(self) -> str:
        return "gov_data"

    # ── Read: per-file Gemini mapping + enrichment, then combine ─────────────

    def read(self) -> pl.LazyFrame:
        # Collect each file eagerly so corrupt data (not just corrupt schema)
        # is caught inside the try-except before frames are concatenated.
        dfs: list[pl.DataFrame] = []
        for parquet_file in sorted(self._source_path.glob("*.parquet")):
            try:
                lf = pl.scan_parquet(parquet_file)
                lf = self._apply_gemini_mapping(lf)
                lf = self._enrich_from_db(lf)
                dfs.append(lf.collect())
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skipping corrupt parquet {}: {}", parquet_file.name, exc
                )
        if not dfs:
            return pl.DataFrame(schema=TARGET_SCHEMA).lazy()
        return pl.concat(dfs, how="diagonal_relaxed").lazy()

    def _apply_gemini_mapping(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        all_cols = lf.collect_schema().names()
        source_cols = [c for c in all_cols if c not in _TECHNICAL_COLS]

        mapping = map_columns(
            source_cols,
            self._config.gemini_api_key,
            database_url=self._config.database_url,
        )
        rename: dict[str, str] = {
            src: tgt for tgt, src in mapping.items() if src is not None
        }
        mapped_count = sum(v is not None for v in mapping.values())
        logger.info("Mapped {}/{} target columns", mapped_count, len(TARGET_COLUMNS))

        lf = lf.rename(rename)

        existing = set(lf.collect_schema().names())
        null_cols = [
            pl.lit(None).cast(TARGET_SCHEMA[col]).alias(col)
            for col in TARGET_COLUMNS
            if col not in existing
        ]
        if null_cols:
            lf = lf.with_columns(null_cols)

        # Always add enrichment columns so _filter_valid can reference them
        lf = lf.with_columns(
            pl.lit(None, dtype=pl.String).alias("snapshot_date"),
            pl.lit(None, dtype=pl.String).alias("regon"),
        )

        after_rename = existing | set(rename.values())
        keep = (
            TARGET_COLUMNS
            + ["snapshot_date", "regon"]
            + [c for c in _TECHNICAL_COLS if c in after_rename]
        )
        return lf.select(keep)

    def _enrich_from_db(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        schema_names = set(lf.collect_schema().names())
        if "download_url" not in schema_names:
            return lf

        download_url = lf.select("download_url").collect().item(0, 0)
        if not download_url:
            return lf

        meta = _fetch_metadata(download_url, self._config)
        if meta is None:
            logger.warning("No metadata for URL: {}", download_url)
            return lf

        # Values treated as "no data" in source CSVs
        placeholders = {"x", "-", "n/a", "nd", "brak", ""}

        fills: list[pl.Expr] = []
        if meta.developer_name:
            fills.append(
                pl.col("developer_name").fill_null(pl.lit(meta.developer_name))
            )
        if meta.institution_city:
            # Replace null OR placeholder values (e.g. 'X') with institution_city
            city_lower = pl.col("city").str.to_lowercase().str.strip_chars()
            fills.append(
                pl.when(pl.col("city").is_null() | city_lower.is_in(list(placeholders)))
                .then(pl.lit(meta.institution_city))
                .otherwise(pl.col("city"))
                .alias("city")
            )

        fills.append(pl.lit(meta.data_date).alias("snapshot_date"))
        fills.append(pl.lit(meta.regon).alias("regon"))

        logger.debug(
            "Enriched: developer={!r} city={!r} snapshot={}",
            meta.developer_name,
            meta.institution_city,
            meta.data_date,
        )
        return lf.with_columns(fills)

    # ── Transform pipeline ────────────────────────────────────────────────────

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        df = self._cast_types(df)
        df = self._normalize_prices(df)
        df = self._filter_valid(df)
        df = self._normalize(df)
        df = self._lag(df)
        df = self._flags(df)
        df = self._computed(df)
        return self._filter_changes(df)

    def _filter_valid(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(
            pl.col("unit_id").is_not_null()
            & pl.col("total_price_gross").is_not_null()
            & (pl.col("total_price_gross") > 0)
            & pl.col("snapshot_date").is_not_null()
        )

    def _cast_types(self, df: pl.LazyFrame) -> pl.LazyFrame:
        numeric = ["total_price_gross", "usable_area_m2"]
        return df.with_columns(
            pl.col(c)
            .cast(pl.String)
            .str.replace(",", ".")
            .cast(pl.Float64, strict=False)
            for c in numeric
        )

    def _normalize_prices(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Fix files where total_price_gross was published as price/m².

        Heuristic: if computed price/m² < 1 000 PLN/m² the value is
        suspiciously low for any Polish city — assume the column contains
        price per m² and multiply by usable_area_m2 to get the total.
        Typical range in major Polish cities: 5 000–30 000 PLN/m².
        """
        implied_per_m2 = pl.col("total_price_gross") / pl.col("usable_area_m2")
        looks_like_per_m2 = (
            implied_per_m2.is_not_null()
            & (implied_per_m2 < 1_000)
            & pl.col("usable_area_m2").is_not_null()
            & (pl.col("usable_area_m2") > 0)
        )
        return df.with_columns(
            pl.when(looks_like_per_m2)
            .then(pl.col("total_price_gross") * pl.col("usable_area_m2"))
            .otherwise(pl.col("total_price_gross"))
            .alias("total_price_gross")
        )

    def _normalize(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            pl.col("city").str.strip_chars().str.to_titlecase().alias("city_norm"),
            _build_status_norm_expr().alias("status_norm"),
        )

    def _lag(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.sort([*_LAG_GROUP, "snapshot_date"]).with_columns(
            pl.col("total_price_gross").shift(1).over(_LAG_GROUP).alias("prev_price"),
            pl.col("status_norm").shift(1).over(_LAG_GROUP).alias("prev_status_norm"),
        )

    def _flags(self, df: pl.LazyFrame) -> pl.LazyFrame:
        has_prev = pl.col("prev_price").is_not_null()
        is_first = pl.col("prev_price").is_null() & pl.col("prev_status_norm").is_null()
        return df.with_columns(
            is_first.alias("is_first_snapshot"),
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

    def _filter_changes(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(
            pl.col("is_first_snapshot")
            | pl.col("is_price_changed")
            | pl.col("is_status_changed")
        )

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
