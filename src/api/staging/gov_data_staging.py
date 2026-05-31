"""GOV data staging"""

import json
from pathlib import Path

import polars as pl

from .base import BaseStaging

_COLUMN_MAP: dict[str, str] = json.loads(
    (Path(__file__).parent / "gov_data_columns_mapping.json").read_text(
        encoding="utf-8"
    )
)


class GovDataStaging(BaseStaging):
    @property
    def source_name(self) -> str:
        return "gov_data"

    def read(self) -> pl.LazyFrame:
        return pl.scan_csv(
            self._source_path,
            separator=",",
            infer_schema_length=1000,
            low_memory=True,
        )

    def _rename_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        names = df.collect_schema().names()
        mapping = {col: _COLUMN_MAP[col] for col in names if col in _COLUMN_MAP}
        return df.rename(mapping)

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            pl.col("price_per_sqm_date").str.to_date(format=None, strict=False),
            pl.col("price_date").str.to_date(format=None, strict=False),
        )


if __name__ == "__main__":
    file = Path("data/raw/gov_data/20260531_120033.csv")
    staging = GovDataStaging(source_path=file)
    staging.run()
