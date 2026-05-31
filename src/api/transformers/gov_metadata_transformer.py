"""GOV metadata transformer"""

import re
from pathlib import Path

import polars as pl

from .base import BaseTransformer

_PL_CHARS = str.maketrans(
    "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "acelnoszzACELNOSZZ",
)


def _normalize_str(s: str) -> str:
    return s.translate(_PL_CHARS)


def _normalize_expr(expr: pl.Expr) -> pl.Expr:
    for src, dst in zip("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ", strict=True):
        expr = expr.str.replace_all(src, dst, literal=True)
    return expr


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

    def __init__(
        self, cities: list[str], columns: list[str] | None = None, *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)

        self._cities: list[str] = cities
        self._columns: list[str] = (
            columns if columns is not None else self._DEFAULT_COLUMNS
        )

    @property
    def source_name(self) -> str:
        return "gov_metadata"

    def read(self) -> pl.LazyFrame:
        return pl.scan_parquet(self._source_path)

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        city_pattern = "|".join(re.escape(_normalize_str(c)) for c in self._cities)
        return (
            df.filter(pl.col("institution_type") == "Developers")
            .with_columns(
                _normalize_expr(pl.col("dataset_regions")).alias("_regions_norm")
            )
            .filter(pl.col("_regions_norm").str.contains(city_pattern))
            .drop("_regions_norm")
            .select(self._columns)
        )


if __name__ == "__main__":
    file = Path("data/staging/gov_metadata/20260530_231513.parquet")
    transformer = GovMetadataTransformer(
        source_path=file,
        cities=["Warsaw", "Kraków"],
    )
    transformer.run()
