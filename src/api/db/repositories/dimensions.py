"""Repositories for dimensional model: Dim_Czas, Dim_Lokalizacja,
Dim_Status_Lokalu, Dim_Inwestycja (SCD2), Fact_Zmiana."""

import datetime

from sqlalchemy.dialects.sqlite import insert

from ..models import DimCzas, DimInwestycja, DimLokalizacja, DimStatusLokalu, FactZmiana
from .base import BaseRepository


class DimCzasRepository(BaseRepository[DimCzas]):
    def insert_or_ignore(self, record: DimCzas) -> None:
        self._session.execute(
            insert(DimCzas)
            .values(
                id=record.id,
                date=record.date,
                year=record.year,
                quarter=record.quarter,
                month=record.month,
                day=record.day,
                day_of_week=record.day_of_week,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )

    def insert_or_ignore_batch(self, records: list[DimCzas]) -> int:
        if not records:
            return 0
        result = self._session.execute(
            insert(DimCzas)
            .values(
                [
                    dict(
                        id=r.id,
                        date=r.date,
                        year=r.year,
                        quarter=r.quarter,
                        month=r.month,
                        day=r.day,
                        day_of_week=r.day_of_week,
                    )
                    for r in records
                ]
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        return result.rowcount

    def get_or_create(self, date: datetime.date) -> int:
        """Return id (YYYYMMDD) for given date, inserting if missing."""
        date_id = int(date.strftime("%Y%m%d"))
        self.insert_or_ignore(
            DimCzas(
                id=date_id,
                date=date,
                year=date.year,
                quarter=(date.month - 1) // 3 + 1,
                month=date.month,
                day=date.day,
                day_of_week=date.isoweekday(),
            )
        )
        return date_id


class DimLokalizacjaRepository(BaseRepository[DimLokalizacja]):
    def insert_or_ignore(self, record: DimLokalizacja) -> None:
        self._session.execute(
            insert(DimLokalizacja)
            .values(miasto_norm=record.miasto_norm)
            .on_conflict_do_nothing(index_elements=["miasto_norm"])
        )

    def insert_or_ignore_batch(self, records: list[DimLokalizacja]) -> int:
        if not records:
            return 0
        result = self._session.execute(
            insert(DimLokalizacja)
            .values([{"miasto_norm": r.miasto_norm} for r in records])
            .on_conflict_do_nothing(index_elements=["miasto_norm"])
        )
        return result.rowcount

    def get_id(self, miasto_norm: str) -> int | None:
        row = (
            self._session.query(DimLokalizacja)
            .filter(DimLokalizacja.miasto_norm == miasto_norm)
            .first()
        )
        return row.id if row else None

    def get_or_create_id(self, miasto_norm: str) -> int:
        self.insert_or_ignore(DimLokalizacja(miasto_norm=miasto_norm))
        return self.get_id(miasto_norm)  # type: ignore[return-value]


class DimStatusLokaluRepository(BaseRepository[DimStatusLokalu]):
    _LABELS: dict[str, str] = {
        "AVAILABLE": "Dostępny",
        "RESERVED": "Zarezerwowany",
        "SOLD": "Sprzedany",
        "WITHDRAWN": "Wycofany",
        "UNKNOWN": "Nieznany",
    }

    def insert_or_ignore(self, record: DimStatusLokalu) -> None:
        self._session.execute(
            insert(DimStatusLokalu)
            .values(status_norm=record.status_norm, status_label=record.status_label)
            .on_conflict_do_nothing(index_elements=["status_norm"])
        )

    def insert_or_ignore_batch(self, records: list[DimStatusLokalu]) -> int:
        if not records:
            return 0
        result = self._session.execute(
            insert(DimStatusLokalu)
            .values(
                [
                    {"status_norm": r.status_norm, "status_label": r.status_label}
                    for r in records
                ]
            )
            .on_conflict_do_nothing(index_elements=["status_norm"])
        )
        return result.rowcount

    def get_id(self, status_norm: str) -> int | None:
        row = (
            self._session.query(DimStatusLokalu)
            .filter(DimStatusLokalu.status_norm == status_norm)
            .first()
        )
        return row.id if row else None

    def get_or_create_id(self, status_norm: str) -> int:
        label = self._LABELS.get(status_norm, status_norm)
        self.insert_or_ignore(
            DimStatusLokalu(status_norm=status_norm, status_label=label)
        )
        return self.get_id(status_norm)  # type: ignore[return-value]


class DimInwestycjaRepository(BaseRepository[DimInwestycja]):
    """SCD Type 2: tracks history of investment attribute changes."""

    def insert_or_ignore(self, record: DimInwestycja) -> None:
        self._session.add(record)

    def insert_or_ignore_batch(self, records: list[DimInwestycja]) -> int:
        self._session.add_all(records)
        return len(records)

    def _current(
        self, developer_name: str | None, investment_id: str | None, regon: str | None
    ) -> DimInwestycja | None:
        return (
            self._session.query(DimInwestycja)
            .filter(
                DimInwestycja.developer_name == developer_name,
                DimInwestycja.investment_id == investment_id,
                DimInwestycja.regon == regon,
                DimInwestycja.is_current.is_(True),
            )
            .first()
        )

    def get_or_create_id(
        self,
        developer_name: str | None,
        investment_id: str | None,
        regon: str | None,
        city: str | None,
        street: str | None,
        snapshot_date: datetime.date,
    ) -> int:
        current = self._current(developer_name, investment_id, regon)

        if current is None:
            # First time we see this investment
            new = DimInwestycja(
                valid_from=snapshot_date,
                developer_name=developer_name,
                investment_id=investment_id,
                regon=regon,
                city=city,
                street=street,
            )
            self._session.add(new)
            self._session.flush()
            return new.id

        # Check if tracked attributes changed (SCD2 trigger)
        if current.city != city or current.street != street:
            current.valid_to = snapshot_date
            current.is_current = False
            new = DimInwestycja(
                valid_from=snapshot_date,
                developer_name=developer_name,
                investment_id=investment_id,
                regon=regon,
                city=city,
                street=street,
            )
            self._session.add(new)
            self._session.flush()
            return new.id

        return current.id


class FactZmianaRepository(BaseRepository[FactZmiana]):
    def insert_or_ignore(self, record: FactZmiana) -> None:
        self._session.execute(
            insert(FactZmiana)
            .values(
                fk_czas=record.fk_czas,
                fk_inwestycja=record.fk_inwestycja,
                fk_status_lokalu=record.fk_status_lokalu,
                fk_lokalizacja=record.fk_lokalizacja,
                unit_id=record.unit_id,
                download_url=record.download_url,
                is_price_changed=record.is_price_changed,
                is_status_changed=record.is_status_changed,
                is_obnizka=record.is_obnizka,
                wartosc_lokalu_pln=record.wartosc_lokalu_pln,
                prev_cena=record.prev_cena,
                kwota_zmiany_pln=record.kwota_zmiany_pln,
                cena_m2_pln=record.cena_m2_pln,
            )
            .on_conflict_do_nothing(index_elements=["download_url", "unit_id"])
        )

    def insert_or_ignore_batch(self, records: list[FactZmiana]) -> int:
        if not records:
            return 0
        rows = [
            dict(
                fk_czas=r.fk_czas,
                fk_inwestycja=r.fk_inwestycja,
                fk_status_lokalu=r.fk_status_lokalu,
                fk_lokalizacja=r.fk_lokalizacja,
                unit_id=r.unit_id,
                download_url=r.download_url,
                is_price_changed=r.is_price_changed,
                is_status_changed=r.is_status_changed,
                is_obnizka=r.is_obnizka,
                wartosc_lokalu_pln=r.wartosc_lokalu_pln,
                prev_cena=r.prev_cena,
                kwota_zmiany_pln=r.kwota_zmiany_pln,
                cena_m2_pln=r.cena_m2_pln,
            )
            for r in records
        ]
        result = self._session.execute(
            insert(FactZmiana)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["download_url", "unit_id"])
        )
        return result.rowcount
