"""GUS BDL loader — upserts demographic data into Dim_Demographics."""

from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import DimDemographics
from src.api.db.repositories.dimensions import DimDemographicsRepository

from .base import BaseLoader

_BATCH_SIZE = 500


class GUSBDLLoader(BaseLoader):
    def __init__(self, source_path: Path, config: Config | None = None) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def load(self) -> int:
        engine = build_engine(self._config.db_path)
        init_db(engine)

        df = pl.read_parquet(self._source_path)
        if df.is_empty():
            logger.info("No demographic rows to load")
            return 0

        total = 0
        with get_session(engine) as session:
            repo = DimDemographicsRepository(session)

            for batch_start in range(0, len(df), _BATCH_SIZE):
                batch = df[batch_start : batch_start + _BATCH_SIZE]
                records: list[DimDemographics] = []

                for row in batch.iter_rows(named=True):
                    records.append(
                        DimDemographics(
                            teryt=str(row["teryt"]),
                            year=int(row["year"]),
                            city=str(row["city"]),
                            population=_to_int(row.get("population")),
                            avg_gross_salary=row.get("avg_gross_salary"),
                            unemployment_rate=row.get("unemployment_rate"),
                            migration_balance=_to_int(row.get("migration_balance")),
                            working_age_population=_to_int(
                                row.get("working_age_population")
                            ),
                        )
                    )

                inserted = repo.upsert_batch(records)
                total += inserted
                logger.debug("Batch {}/{}: {} upserted", batch_start, len(df), inserted)

        logger.info("Dim_Demographics: {} rows upserted", total)
        return total


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
