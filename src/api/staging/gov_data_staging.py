"""GOV data staging — LLM-based column normalization to unified schema."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import DeveloperFile
from src.api.db.repositories.developer_files import DeveloperFileRepository

from .base import BaseStaging
from .column_mapper import map_columns
from .schema import TARGET_COLUMNS, TARGET_SCHEMA


@dataclass
class _FileMeta:
    developer_name: str | None
    institution_city: str | None
    data_date: str | None
    regon: str | None


def _detect_separator(path: Path) -> str:
    sample = path.read_bytes()[:4096].decode("utf-8-sig", errors="replace")
    return ";" if sample.count(";") > sample.count(",") else ","


def _fetch_metadata(download_url: str, config: Config) -> _FileMeta | None:
    engine = build_engine(config.db_path)
    init_db(engine)
    with get_session(engine) as session:
        row: DeveloperFile | None = (
            DeveloperFileRepository(session)
            ._session.query(DeveloperFile)
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


class GovDataStaging(BaseStaging):
    def __init__(
        self,
        *args,
        config: Config | None = None,
        download_url: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._config = config or Config()
        self._download_url = download_url

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

        rename: dict[str, str] = {
            src: tgt for tgt, src in mapping.items() if src is not None
        }
        mapped_count = sum(v is not None for v in mapping.values())
        logger.info("Mapped {}/{} target columns", mapped_count, len(TARGET_COLUMNS))

        df = df.rename(rename)

        mapped_targets = set(rename.values())
        null_cols = [
            pl.lit(None).cast(TARGET_SCHEMA[col]).alias(col)
            for col in TARGET_COLUMNS
            if col not in mapped_targets
        ]
        if null_cols:
            df = df.with_columns(null_cols)

        return df.select(TARGET_COLUMNS)

    def _enrich_from_metadata(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        if not self._download_url:
            return lf

        meta = _fetch_metadata(self._download_url, self._config)
        if meta is None:
            logger.warning("No metadata found for URL: {}", self._download_url)
            return lf

        fills: list[pl.Expr] = []
        if meta.developer_name:
            fills.append(
                pl.col("developer_name").fill_null(pl.lit(meta.developer_name))
            )
        if meta.institution_city:
            fills.append(pl.col("city").fill_null(pl.lit(meta.institution_city)))

        # Extra columns not mappable by Gemini — always set from metadata
        fills.append(pl.lit(self._download_url).alias("download_url"))
        fills.append(pl.lit(meta.data_date).alias("snapshot_date"))
        fills.append(pl.lit(meta.regon).alias("regon"))

        logger.debug(
            "Enriching: developer={!r} city={!r} snapshot={}",
            meta.developer_name,
            meta.institution_city,
            meta.data_date,
        )
        return lf.with_columns(fills)

    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame:
        numeric_cols = ["total_price_gross", "usable_area_m2"]
        df = df.with_columns(
            [
                pl.col(c)
                .cast(pl.String)
                .str.replace(",", ".")
                .cast(pl.Float64, strict=False)
                for c in numeric_cols
            ]
        )
        return self._enrich_from_metadata(df)


if __name__ == "__main__":
    for f in sorted(Path("data/raw/gov_data").glob("*.csv")):
        logger.info("Staging {}", f.name)
        GovDataStaging(source_path=f).run()
