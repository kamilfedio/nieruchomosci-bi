"""Kaggle loader — FK lookup + load into Kaggle dimensional model."""

import datetime
import hashlib
from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import FactOfertaNieruchomosci
from src.api.db.repositories.dimensions import (
    DimLokalizacjaRepository,
    DimTimeRepository,
    DimTypLokaluRepository,
    DimTypRynkuRepository,
    FactOfertaNieruchomosciRepository,
)

from .base import BaseLoader

_BATCH_SIZE = 500

_TYPE_ATTRS = [
    "rynek_norm",
    "rooms",
    "floor",
    "floor_count",
    "build_year",
    "material_norm",
    "stan_norm",
    "has_balcony",
    "has_elevator",
    "has_parking_space",
    "has_storage_room",
]


def _type_hash(row: dict) -> str:
    parts = [str(row.get(k)) for k in _TYPE_ATTRS]
    return hashlib.md5("|".join(parts).encode()).hexdigest()  # noqa: S324


class KaggleLoader(BaseLoader):
    def __init__(self, source_path: Path, config: Config | None = None) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def load(self) -> int:
        engine = build_engine(self._config.db_path)
        init_db(engine)

        df = pl.read_parquet(self._source_path)
        if df.is_empty():
            logger.info("No listings to load")
            return 0

        total = 0
        with get_session(engine) as session:
            dim_time = DimTimeRepository(session)
            dim_lok = DimLokalizacjaRepository(session)
            dim_typ = DimTypLokaluRepository(session)
            dim_rynek = DimTypRynkuRepository(session)
            fact_repo = FactOfertaNieruchomosciRepository(session)

            for batch_start in range(0, len(df), _BATCH_SIZE):
                batch = df[batch_start : batch_start + _BATCH_SIZE]
                facts: list[FactOfertaNieruchomosci] = []

                for row in batch.iter_rows(named=True):
                    snapshot_date: datetime.date | None = row.get("snapshot_date")
                    if snapshot_date is None:
                        continue

                    fk_czas = dim_time.get_or_create(snapshot_date)

                    fk_lok = dim_lok.get_or_create_id(
                        miasto=row.get("miasto_norm") or row.get("city") or "UNKNOWN",
                        latitude=row.get("latitude"),
                        longitude=row.get("longitude"),
                    )

                    th = _type_hash(row)
                    fk_typ = dim_typ.get_or_create_id(
                        type_hash=th,
                        rynek=row.get("rynek_norm"),
                        liczba_pokoi=_to_int(row.get("rooms")),
                        pietro=_to_int(row.get("floor")),
                        liczba_pieter=_to_int(row.get("floor_count")),
                        rok_budowy=_to_int(row.get("build_year")),
                        material=row.get("material_norm"),
                        stan=row.get("stan_norm"),
                        balkon=row.get("has_balcony"),
                        winda=row.get("has_elevator"),
                        parking=row.get("has_parking_space"),
                        komorka=row.get("has_storage_room"),
                    )

                    fk_rynek = dim_rynek.get_or_create_id(
                        row.get("rynek_norm") or "nieznany"
                    )

                    price = row.get("price")
                    area = row.get("square_meters")
                    if price is None or area is None:
                        continue

                    facts.append(
                        FactOfertaNieruchomosci(
                            fk_czas=fk_czas,
                            fk_lokalizacja=fk_lok,
                            fk_typ_lokalu=fk_typ,
                            fk_typ_rynku=fk_rynek,
                            listing_id=str(row.get("id") or ""),
                            cena_calkowita_pln=float(price),
                            powierzchnia_m2=float(area),
                            cena_m2_pln=row.get("cena_m2_pln"),
                        )
                    )

                inserted = fact_repo.insert_or_ignore_batch(facts)
                total += inserted
                logger.debug("Batch {}/{}: {} inserted", batch_start, len(df), inserted)

        return total


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
