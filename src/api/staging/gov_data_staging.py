"""GOV data staging — raw preservation with structural rename only.

Staging responsibility:
- Read file (CSV or Excel), detect format automatically
- Rename columns to snake_case (mechanical, no semantic mapping)
- Add technical columns: batch_id, loaded_at, source_file, download_url
- Deduplicate within the file
- Save all original columns to Parquet

Business logic (Gemini mapping, DB enrichment, type casting,
normalization) belongs in GovDataTransformer.
"""

from pathlib import Path

import polars as pl

from .base import BaseStaging


def _detect_separator(path: Path) -> str:
    sample = path.read_bytes()[:4096].decode("utf-8-sig", errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


class GovDataStaging(BaseStaging):
    def __init__(self, *args, download_url: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._download_url = download_url

    @property
    def source_name(self) -> str:
        return "gov_data"

    def read(self) -> pl.LazyFrame:
        if self._source_path.suffix.lower() in (".xlsx", ".xls"):
            # infer_schema_length=0 → all columns read as String
            return pl.read_excel(self._source_path, infer_schema_length=0).lazy()
        sep = _detect_separator(self._source_path)
        # Use eager read_csv instead of scan_csv: chunked lazy reading breaks on
        # CSVs with quoted multi-line fields (embedded newlines cross chunk boundaries).
        return pl.read_csv(
            self._source_path,
            separator=sep,
            encoding="utf8-lossy",
            infer_schema_length=0,
            truncate_ragged_lines=True,
            ignore_errors=True,
        ).lazy()

    def _add_technical_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        df = super()._add_technical_columns(df)
        return df.with_columns(pl.lit(self._download_url).alias("download_url"))

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df

    def save(self, lf: pl.LazyFrame) -> Path:
        # Developer CSVs often have embedded newlines in quoted fields which
        # break Polars' streaming engine. Use eager collect instead.
        path = (
            self._staging_dir / self.source_name / (self._source_path.stem + ".parquet")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        lf.collect().write_parquet(path)
        return path


if __name__ == "__main__":
    from loguru import logger

    for f in sorted(Path("data/raw/gov_data").glob("*")):
        if f.suffix.lower() in (".csv", ".xlsx", ".xls"):
            logger.info("Staging {}", f.name)
            GovDataStaging(source_path=f).run()
