"""GOV data staging — LLM-based column normalization to unified schema."""

from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config

from .base import BaseStaging
from .column_mapper import map_columns
from .schema import TARGET_COLUMNS, TARGET_SCHEMA


def _detect_separator(path: Path) -> str:
    sample = path.read_bytes()[:4096].decode("utf-8-sig", errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


class GovDataStaging(BaseStaging):
    def __init__(self, *args, config: Config | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._config = config or Config()

    @property
    def source_name(self) -> str:
        return "gov_data"

    def read(self) -> pl.LazyFrame:
        sep = _detect_separator(self._source_path)
        return pl.scan_csv(
            self._source_path,
            separator=sep,
            encoding="utf8-lossy",
            infer_schema_length=1000,
            low_memory=True,
        )

    def _rename_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        source_cols = df.collect_schema().names()
        mapping = map_columns(source_cols, self._config.gemini_api_key)

        # Build rename dict: source_col → target_col (skip unmapped)
        rename: dict[str, str] = {
            src: tgt for tgt, src in mapping.items() if src is not None
        }
        mapped_count = sum(v is not None for v in mapping.values())
        logger.info("Mapped {}/{} target columns", mapped_count, len(TARGET_COLUMNS))

        df = df.rename(rename)

        # Add null columns for targets that had no mapping
        mapped_targets = set(rename.values())
        null_cols = [
            pl.lit(None).cast(TARGET_SCHEMA[col]).alias(col)
            for col in TARGET_COLUMNS
            if col not in mapped_targets
        ]
        if null_cols:
            df = df.with_columns(null_cols)

        return df.select(TARGET_COLUMNS)

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        numeric_cols = ["total_price_gross", "usable_area_m2"]
        return df.with_columns(
            [
                pl.col(c)
                .cast(pl.String)
                .str.replace(",", ".")
                .cast(pl.Float64, strict=False)
                for c in numeric_cols
            ]
        )


if __name__ == "__main__":
    for f in sorted(Path("data/raw/gov_data").glob("*.csv")):
        logger.info("Staging {}", f.name)
        GovDataStaging(source_path=f).run()
