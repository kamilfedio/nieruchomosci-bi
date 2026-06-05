"""Gov data loader — steps 6-7: FK lookup + load into dimensional model.

Reads the processed (transformer output) parquet and writes to:
  Dim_Czas, Dim_Lokalizacja, Dim_Status_Lokalu, Dim_Inwestycja (SCD2),
  Fact_Zmiana.
"""

import datetime
from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import FactZmiana
from src.api.db.repositories.dimensions import (
    DimCzasRepository,
    DimInwestycjaRepository,
    DimLokalizacjaRepository,
    DimStatusLokaluRepository,
    FactZmianaRepository,
)

from .base import BaseLoader

_BATCH_SIZE = 500


class GovDataLoader(BaseLoader):
    def __init__(self, source_path: Path, config: Config | None = None) -> None:
        super().__init__(source_path)
        self._config = config or Config()

    def _parse_date(self, value: str | None) -> datetime.date | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%d.%m.%Y"):
            try:
                return datetime.datetime.strptime(value[:10], fmt).date()
            except ValueError:
                continue
        return None

    def load(self) -> int:
        engine = build_engine(self._config.db_path)
        init_db(engine)

        df = pl.read_parquet(self._source_path)
        if df.is_empty():
            logger.info("No change rows to load")
            return 0

        total = 0
        with get_session(engine) as session:
            dim_czas = DimCzasRepository(session)
            dim_lok = DimLokalizacjaRepository(session)
            dim_status = DimStatusLokaluRepository(session)
            dim_inw = DimInwestycjaRepository(session)
            fact_repo = FactZmianaRepository(session)

            for batch_start in range(0, len(df), _BATCH_SIZE):
                batch = df[batch_start : batch_start + _BATCH_SIZE]
                facts: list[FactZmiana] = []

                for row in batch.iter_rows(named=True):
                    # ── step 6: FK lookups ────────────────────────────────
                    snapshot_date = self._parse_date(row.get("snapshot_date"))
                    if snapshot_date is None:
                        continue

                    fk_czas = dim_czas.get_or_create(snapshot_date)

                    miasto = row.get("miasto_norm") or row.get("city") or "UNKNOWN"
                    fk_lok = dim_lok.get_or_create_id(miasto)

                    status = row.get("status_norm") or "UNKNOWN"
                    fk_status = dim_status.get_or_create_id(status)

                    fk_inw = dim_inw.get_or_create_id(
                        developer_name=row.get("developer_name"),
                        investment_id=row.get("investment_id"),
                        regon=row.get("regon"),
                        city=row.get("city"),
                        street=row.get("street"),
                        snapshot_date=snapshot_date,
                    )

                    # ── step 7: build Fact_Zmiana row ─────────────────────
                    facts.append(
                        FactZmiana(
                            fk_czas=fk_czas,
                            fk_inwestycja=fk_inw,
                            fk_status_lokalu=fk_status,
                            fk_lokalizacja=fk_lok,
                            unit_id=row.get("unit_id") or "",
                            download_url=row.get("download_url") or "",
                            is_price_changed=bool(row.get("is_price_changed")),
                            is_status_changed=bool(row.get("is_status_changed")),
                            is_obnizka=bool(row.get("is_obnizka")),
                            wartosc_lokalu_pln=row.get("wartosc_lokalu_pln"),
                            prev_cena=row.get("prev_cena"),
                            kwota_zmiany_pln=row.get("kwota_zmiany_pln"),
                            cena_m2_pln=row.get("cena_m2_pln"),
                        )
                    )

                inserted = fact_repo.insert_or_ignore_batch(facts)
                total += inserted
                logger.debug("Batch {}/{}: {} inserted", batch_start, len(df), inserted)

        return total
