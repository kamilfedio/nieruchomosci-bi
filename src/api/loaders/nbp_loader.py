"""NBP BaRN loader — FK lookup + load into Fact_Benchmark_NBP.

Dim_Location and Dim_Market_Type are looked up only (not created).
Rows whose city is not in Dim_Location are skipped and logged.
"""

import datetime
from pathlib import Path

import polars as pl
from loguru import logger
from sqlalchemy.dialects.sqlite import insert
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import FactBenchmarkNbp
from src.api.db.repositories.dimensions import DimLocationRepository, DimTimeRepository

from .base import BaseLoader

_BATCH_SIZE = 500

_QUARTER_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}

_MARKET_CODE = {"primary": "primary", "secondary": "secondary"}


def _quarter_start(year: int, quarter: int) -> datetime.date:
    return datetime.date(year, _QUARTER_MONTH[quarter], 1)


class NBPLoader(BaseLoader):
    def __init__(self, source_path: Path, config: Config | None = None) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def load(self) -> int:
        engine = build_engine(self._config.db_path)
        init_db(engine)

        df = pl.read_parquet(self._source_path)
        if df.is_empty():
            logger.info("No NBP benchmark rows to load")
            return 0

        total = 0
        skipped_cities: set[str] = set()

        with get_session(engine) as session:
            dim_time = DimTimeRepository(session)
            dim_loc = DimLocationRepository(session)

            # Pre-load market type ids from DB (must exist — created by Kaggle pipeline)
            from src.api.db.models import DimMarketType

            market_ids: dict[str, int] = {
                r.market_code: r.id for r in session.query(DimMarketType).all()
            }

            for batch_start in range(0, len(df), _BATCH_SIZE):
                batch = df[batch_start : batch_start + _BATCH_SIZE]
                facts: list[dict] = []

                for row in batch.iter_rows(named=True):
                    year = row.get("year")
                    quarter = row.get("quarter")
                    if not year or not quarter:
                        continue

                    fk_time = dim_time.get_or_create(
                        _quarter_start(int(year), int(quarter))
                    )

                    city: str = str(row.get("city") or "")
                    fk_loc = dim_loc.get_id(city)
                    if fk_loc is None:
                        skipped_cities.add(city)
                        continue

                    market: str = str(row.get("market") or "")
                    fk_market = market_ids.get(_MARKET_CODE.get(market, market))
                    if fk_market is None:
                        logger.warning("Market type not found in DB: {!r}", market)
                        continue

                    facts.append(
                        dict(
                            fk_time=fk_time,
                            fk_location=fk_loc,
                            fk_market_type=fk_market,
                            avg_offer_price_m2_pln=row.get("avg_offer_price_m2_pln"),
                            avg_transaction_price_m2_pln=row.get(
                                "avg_transaction_price_m2_pln"
                            ),
                            hedonic_index=row.get("hedonic_index"),
                        )
                    )

                if facts:
                    session.execute(
                        insert(FactBenchmarkNbp)
                        .values(facts)
                        .on_conflict_do_nothing(
                            index_elements=["fk_time", "fk_location", "fk_market_type"]
                        )
                    )
                    total += len(facts)
                    logger.debug(
                        "Batch {}/{}: {} inserted", batch_start, len(df), len(facts)
                    )

        if skipped_cities:
            logger.warning(
                "Skipped {} cities not in Dim_Location: {}",
                len(skipped_cities),
                sorted(skipped_cities),
            )

        return total
