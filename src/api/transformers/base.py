"""Base class for transformers"""

from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl
from loguru import logger


class BaseTransformer(ABC):
    def __init__(
        self, source_path: Path, processed_dir: Path = Path("data/processed")
    ) -> None:
        self._source_path: Path = source_path
        self._processed_dir: Path = processed_dir
        self._processed_dir.mkdir(parents=True, exist_ok=True)

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame: ...

    @abstractmethod
    def read(self) -> pl.LazyFrame: ...

    def save(self, df: pl.DataFrame) -> Path:
        path = (
            self._processed_dir
            / self.source_name
            / (self._source_path.stem + ".parquet")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(path)
        return path

    def run(self) -> Path:
        logger.info("Starting transformation of '{}'", self._source_path)
        lf = self.read()
        lf = self.transform(lf)
        df = lf.collect(engine="streaming")
        logger.info("Transformation complete: {} rows", len(df))
        path = self.save(df)
        logger.info("Saved to '{}'", path)
        return path
