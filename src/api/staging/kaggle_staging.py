"""Kaggle staging"""

from pathlib import Path

import polars as pl

from .base import BaseStaging


class KaggleStaging(BaseStaging):
    @property
    def source_name(self) -> str:
        return "kaggle_data"

    def read(self) -> pl.LazyFrame:
        return pl.scan_csv(
            self._source_path,
            separator=",",
            infer_schema_length=1000,
            low_memory=True,
        )

    def _rename_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        names = df.collect_schema().names()
        return df.rename({col: self._camel_to_snake(col) for col in names})

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df


if __name__ == "__main__":
    file = Path("data/raw/kaggle_data/20260530_150953.csv")
    staging = KaggleStaging(source_path=file)
    staging.run()
