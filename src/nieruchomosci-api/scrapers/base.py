"""Base class for scrapers"""

from abc import ABC, abstractmethod
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger


class BaseScraper(ABC):
    def __init__(
        self, raw_dir: Path = Path("data/raw"), file_format: str = "csv"
    ) -> None:
        self._raw_dir: Path = raw_dir
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        self._file_format = file_format

        pl_tz = ZoneInfo("Europe/Warsaw")
        self.batch_id: str = datetime.now(tz=pl_tz).strftime("%Y%m%d_%H%M%S")

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def extract(self) -> BytesIO: ...

    def _save(self, reader: BytesIO, path: Path) -> None:

        with open(path, "wb") as f:
            f.write(reader.getbuffer())

    def run(self) -> Path:
        logger.info("Starting downloading data")

        reader: BytesIO = self.extract()

        path: Path = (
            self._raw_dir / f"{self.batch_id}_{self.source_name}.{self._file_format}"
        )
        self._save(reader, path)
        logger.info("Data saved to {}", path)

        return path
