"""Base class for staging"""

import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import polars as pl
from loguru import logger


class BaseStaging(ABC):
    def __init__(
        self, source_path: Path, staging_dir: Path = Path("data/staging")
    ) -> None:
        self._source_path: Path = source_path
        self._staging_dir: Path = staging_dir
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def stage(self, df: pl.LazyFrame) -> pl.LazyFrame: ...

    @abstractmethod
    def read(self) -> pl.LazyFrame: ...

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        return name.lower()

    @staticmethod
    def _to_snake_case(name: str) -> str:
        return re.sub(r"\s+", "_", name.strip()).lower()

    def _rename_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        names = df.collect_schema().names()
        return df.rename({col: self._to_snake_case(col) for col in names})

    def _add_technical_columns(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            pl.lit(str(uuid4())).alias("batch_id"),
            pl.lit(datetime.now(UTC)).alias("loaded_at"),
            pl.lit(str(self._source_path)).alias("source_file"),
        )

    def _dedup(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.unique(keep="first", maintain_order=False)

    def save(self, lf: pl.LazyFrame) -> Path:
        path = (
            self._staging_dir / self.source_name / (self._source_path.stem + ".parquet")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        lf.sink_parquet(path)
        return path

    def run(self) -> Path:
        logger.info("Starting staging of '{}'", self._source_path)
        lf = self.read()
        lf = self._rename_columns(lf)
        lf = self.stage(lf)
        lf = self._add_technical_columns(lf)
        lf = self._dedup(lf)
        path = self.save(lf)
        logger.info("Saved to '{}'", path)
        return path
