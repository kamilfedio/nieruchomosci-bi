"""Abstract base loader"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseLoader(ABC):
    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path

    @abstractmethod
    def load(self) -> int:
        """Load records into DB. Returns number of inserted rows."""
        ...

    def run(self) -> int:
        from loguru import logger

        logger.info("Starting load from '{}'", self._source_path)
        inserted = self.load()
        logger.info("Inserted {} new records", inserted)
        return inserted
