"""GUS BDL transformer — converts raw BDL JSON per indicator into a processed parquet.

Steps:
  1. Flatten each indicator JSON: unit × year → long rows
  2. Clean city names (remove GUS prefixes, lowercase)
  3. Filter to project cities
  4. Pivot: (teryt, city, year) × indicator → wide table
  5. Validate numeric ranges
  6. Save to data/processed/gus_bdl/<batch_id>.parquet
"""

from pathlib import Path

import polars as pl
from loguru import logger

from .base import BaseTransformer

_INDICATOR_FILES = [
    "population",
    "avg_gross_salary",
    "unemployment_rate",
    "migration_balance",
    "working_age_population",
]

# GUS city name prefixes — longest first so they match before shorter ones
_CITY_PREFIXES = ["Powiat m. st. ", "Powiat m. ", "M. "]


def _clean_city(raw: str) -> str:
    for pfx in _CITY_PREFIXES:
        if raw.startswith(pfx):
            raw = raw[len(pfx) :]
            break
    return raw.lower().strip()


class GUSBDLTransformer(BaseTransformer):
    """source_path = directory containing per-indicator JSON files."""

    @property
    def source_name(self) -> str:
        return "gus_bdl"

    def read(self):  # type: ignore[override]
        pass  # not used — run() handles IO directly

    def transform(self, df):  # type: ignore[override]
        pass  # not used — run() handles IO directly

    def run(self) -> Path:  # type: ignore[override]
        from src.api.config import Config

        config = Config()
        allowed = {c.lower() for c in config.cities}

        logger.info("Starting GUS BDL transformation from '{}'", self._source_path)

        long_rows: list[dict] = []
        for indicator in _INDICATOR_FILES:
            json_path = self._source_path / f"{indicator}.json"
            if not json_path.exists():
                logger.warning("Missing indicator file: {}", json_path)
                continue

            import json

            units = json.loads(json_path.read_text(encoding="utf-8"))
            for unit in units:
                teryt = str(unit.get("id") or "")
                city_raw = str(unit.get("name") or "")
                city = _clean_city(city_raw)
                if city not in allowed:
                    continue
                for val_entry in unit.get("values") or []:
                    year = val_entry.get("year")
                    val = val_entry.get("val")
                    if year is None:
                        continue
                    long_rows.append(
                        {
                            "teryt": teryt,
                            "city": city,
                            "year": int(year),
                            "indicator": indicator,
                            "value": float(val) if val is not None else None,
                        }
                    )

        if not long_rows:
            logger.warning("No data rows after flattening — check indicator IDs")
            empty = pl.DataFrame(
                schema={
                    "teryt": pl.String,
                    "city": pl.String,
                    "year": pl.Int16,
                    **{ind: pl.Float64 for ind in _INDICATOR_FILES},
                }
            )
            return self._save(empty)

        df = pl.DataFrame(long_rows)
        logger.info(
            "Flattened {} long rows for {} cities", len(df), df["city"].n_unique()
        )

        # Pivot to wide format
        wide = df.pivot(
            on="indicator",
            index=["teryt", "city", "year"],
            values="value",
            aggregate_function="first",
        )

        # Ensure all indicator columns exist (may be absent if file missing)
        for ind in _INDICATOR_FILES:
            if ind not in wide.columns:
                wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(ind))

        # Validate and cast
        wide = wide.with_columns(
            pl.col("year").cast(pl.Int16),
            # population: positive int, else null
            pl.when(pl.col("population") > 0)
            .then(pl.col("population").cast(pl.Int32))
            .otherwise(None)
            .alias("population"),
            # avg_gross_salary: positive float, else null
            pl.when(pl.col("avg_gross_salary") > 0)
            .then(pl.col("avg_gross_salary"))
            .otherwise(None)
            .alias("avg_gross_salary"),
            # unemployment_rate: 0–100, else null
            pl.when(
                pl.col("unemployment_rate").is_not_null()
                & (pl.col("unemployment_rate") >= 0)
                & (pl.col("unemployment_rate") <= 100)
            )
            .then(pl.col("unemployment_rate"))
            .otherwise(None)
            .alias("unemployment_rate"),
            # migration_balance: cast to Int32 (can be negative)
            pl.col("migration_balance")
            .cast(pl.Int32, strict=False)
            .alias("migration_balance"),
            # working_age_population: positive int, else null
            pl.when(pl.col("working_age_population") > 0)
            .then(pl.col("working_age_population").cast(pl.Int32))
            .otherwise(None)
            .alias("working_age_population"),
        )

        logger.info(
            "Transformed {} rows ({} cities × {} years)",
            len(wide),
            wide["city"].n_unique(),
            wide["year"].n_unique(),
        )
        return self._save(wide)

    def _save(self, df: pl.DataFrame) -> Path:
        stem = Path(self._source_path).name  # batch_id directory name
        out_path = self._processed_dir / self.source_name / f"{stem}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out_path)
        logger.info("Saved to '{}'", out_path)
        return out_path


if __name__ == "__main__":
    raw_dirs = sorted(Path("data/raw/gus_bdl").glob("*/"))
    if raw_dirs:
        GUSBDLTransformer(source_path=raw_dirs[-1]).run()
