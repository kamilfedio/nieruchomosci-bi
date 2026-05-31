"""GOV metadata staging"""

from pathlib import Path

import polars as pl

from .base import BaseStaging


class GovMetadataStaging(BaseStaging):
    @property
    def source_name(self) -> str:
        return "gov_metadata"

    def read(self) -> pl.LazyFrame:
        return pl.scan_csv(
            self._source_path,
            separator=";",
            infer_schema_length=1000,
            low_memory=True,
        )

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            pl.col("dataset_created").str.to_datetime(time_zone="UTC", strict=False),
            pl.col("dataset_verified").str.to_datetime(time_zone="UTC", strict=False),
            pl.col("data_date").str.to_date(format=None, strict=False),
        )


if __name__ == "__main__":
    file = Path("data/raw/gov_metadata/20260530_231513.csv")
    staging = GovMetadataStaging(source_path=file)
    staging.run()
