"""GOV metadata staging"""

from pathlib import Path

import polars as pl

from .base import BaseStaging


class GovMetadataStaging(BaseStaging):
    @property
    def source_name(self) -> str:
        return "gov_metadata"

    @property
    def natural_key(self) -> list[str]:
        return ["resource_url"]

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            pl.col("dataset_created").str.to_datetime(time_zone="UTC", strict=False),
            pl.col("dataset_verified").str.to_datetime(time_zone="UTC", strict=False),
            pl.col("data_date").str.to_date(format=None, strict=False),
        )


if __name__ == "__main__":
    file = Path("data/processed/gov_metadata/20260530_231513.parquet")
    staging = GovMetadataStaging(source_path=file)
    staging.run()
