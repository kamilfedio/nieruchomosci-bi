"""Base class for scrapers"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger


class BaseScraper(ABC):
    def __init__(self, raw_dir: Path = Path("data/raw")) -> None:
        self._raw_dir: Path = raw_dir
        self._raw_dir.mkdir(parents=True, exist_ok=True)

        pl_tz = ZoneInfo("Europe/Warsaw")
        self.batch_id: str = datetime.now(tz=pl_tz).strftime("%Y%m%d_%H%M%S")

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def extract(self) -> Path: ...

    def run(self) -> Path:
        logger.info("Starting downloading data")
        path = self.extract()
        logger.info("Data saved to {}", path)
        return path
