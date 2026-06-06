"""MZP loader — seeds Dim_Flood_Risk with 4 static rows."""

from pathlib import Path

from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.repositories.dimensions import DimFloodRiskRepository

from .base import BaseLoader


class MZPLoader(BaseLoader):
    def __init__(self, source_path: Path, config: Config | None = None) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def load(self) -> int:
        engine = build_engine(self._config.db_path)
        init_db(engine)

        with get_session(engine) as session:
            DimFloodRiskRepository(session).seed()

        logger.info("Dim_Flood_Risk seeded (4 rows)")
        return 4
