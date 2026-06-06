"""MZP loader — seeds Dim_Flood_Risk and loads flood zone geometries into PostGIS."""

import re
from pathlib import Path

from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.repositories.dimensions import DimFloodRiskRepository
from src.api.db.repositories.flood_zones import FloodZoneRepository

from .base import BaseLoader


def _batch_id_from_path(path: Path) -> str:
    match = re.search(r"(\d{8}_\d{6})", path.name)
    return match.group(1) if match else path.stem[:20]


class MZPLoader(BaseLoader):
    def __init__(self, source_path: Path, config: Config | None = None) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def load(self) -> int:
        engine = build_engine(self._config.database_url)
        init_db(engine)

        batch_id = _batch_id_from_path(self._source_path)

        with get_session(engine) as session:
            DimFloodRiskRepository(session).seed()
            zone_repo = FloodZoneRepository(session)
            inserted = zone_repo.replace_from_geojson(str(self._source_path), batch_id)

        logger.info(
            "Dim_Flood_Risk seeded; {} flood zone geometries loaded (batch {})",
            inserted,
            batch_id,
        )
        return inserted
