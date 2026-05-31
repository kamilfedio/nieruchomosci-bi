"""GOV metadata transformer"""

from pathlib import Path

import polars as pl

from .base import BaseTransformer


class GovMetadataTransformer(BaseTransformer):
    _DEFAULT_COLUMNS: list[str] = [
        "dataset_url",
        "title",
        "category",
        "institution_type",
        "name",
        "id_institution",
        "regon",
        "resource_created",
        "data_date",
        "file_format",
        "download_url",
        "batch_id",
        "loaded_at",
        "source_file",
        "dataset_created",
        "dataset_regions",
    ]

    def __init__(self, columns: list[str] | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._columns: list[str] = (
            columns if columns is not None else self._DEFAULT_COLUMNS
        )

    @property
    def source_name(self) -> str:
        return "gov_metadata"

    def read(self) -> pl.LazyFrame:
        return pl.scan_parquet(self._source_path)

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(pl.col("institution_type") == "Developers").select(
            self._columns
        )


if __name__ == "__main__":
    file = Path("data/staging/gov_metadata/20260530_231513.parquet")
    transformer = GovMetadataTransformer(
        source_path=file,
    )
    transformer.run()
