"""Repositories for dimensional model:
DimTime, DimLocation, DimUnitStatus, DimInvestment (SCD2), FactChange,
DimLokalizacja, DimTypLokalu, DimTypRynku, FactOfertaNieruchomosci."""

import datetime

from sqlalchemy.dialects.sqlite import insert

from ..models import (
    DimInvestment,
    DimLocation,
    DimLokalizacja,
    DimTime,
    DimTypLokalu,
    DimTypRynku,
    DimUnitStatus,
    FactChange,
    FactOfertaNieruchomosci,
)
from .base import BaseRepository


class DimTimeRepository(BaseRepository[DimTime]):
    def insert_or_ignore(self, record: DimTime) -> None:
        self._session.execute(
            insert(DimTime)
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

    def insert_or_ignore_batch(self, records: list[DimTime]) -> int:
        if not records:
            return 0
        result = self._session.execute(
            insert(DimTime)
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
            DimTime(
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


class DimLocationRepository(BaseRepository[DimLocation]):
    def insert_or_ignore(self, record: DimLocation) -> None:
        self._session.execute(
            insert(DimLocation)
            .values(city_norm=record.city_norm)
            .on_conflict_do_nothing(index_elements=["city_norm"])
        )

    def insert_or_ignore_batch(self, records: list[DimLocation]) -> int:
        if not records:
            return 0
        result = self._session.execute(
            insert(DimLocation)
            .values([{"city_norm": r.city_norm} for r in records])
            .on_conflict_do_nothing(index_elements=["city_norm"])
        )
        return result.rowcount

    def get_id(self, city_norm: str) -> int | None:
        row = (
            self._session.query(DimLocation)
            .filter(DimLocation.city_norm == city_norm)
            .first()
        )
        return row.id if row else None

    def get_or_create_id(self, city_norm: str) -> int:
        self.insert_or_ignore(DimLocation(city_norm=city_norm))
        return self.get_id(city_norm)  # type: ignore[return-value]


class DimUnitStatusRepository(BaseRepository[DimUnitStatus]):
    _LABELS: dict[str, str] = {
        "AVAILABLE": "Available",
        "RESERVED": "Reserved",
        "SOLD": "Sold",
        "WITHDRAWN": "Withdrawn",
        "UNKNOWN": "Unknown",
    }

    def insert_or_ignore(self, record: DimUnitStatus) -> None:
        self._session.execute(
            insert(DimUnitStatus)
            .values(status_norm=record.status_norm, status_label=record.status_label)
            .on_conflict_do_nothing(index_elements=["status_norm"])
        )

    def insert_or_ignore_batch(self, records: list[DimUnitStatus]) -> int:
        if not records:
            return 0
        result = self._session.execute(
            insert(DimUnitStatus)
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
            self._session.query(DimUnitStatus)
            .filter(DimUnitStatus.status_norm == status_norm)
            .first()
        )
        return row.id if row else None

    def get_or_create_id(self, status_norm: str) -> int:
        label = self._LABELS.get(status_norm, status_norm)
        self.insert_or_ignore(
            DimUnitStatus(status_norm=status_norm, status_label=label)
        )
        return self.get_id(status_norm)  # type: ignore[return-value]


class DimInvestmentRepository(BaseRepository[DimInvestment]):
    """SCD Type 2: tracks history of investment attribute changes."""

    def insert_or_ignore(self, record: DimInvestment) -> None:
        self._session.add(record)

    def insert_or_ignore_batch(self, records: list[DimInvestment]) -> int:
        self._session.add_all(records)
        return len(records)

    def _current(
        self, developer_name: str | None, investment_id: str | None, regon: str | None
    ) -> DimInvestment | None:
        return (
            self._session.query(DimInvestment)
            .filter(
                DimInvestment.developer_name == developer_name,
                DimInvestment.investment_id == investment_id,
                DimInvestment.regon == regon,
                DimInvestment.is_current.is_(True),
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
            new = DimInvestment(
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

        # SCD2 trigger: city or street changed
        if current.city != city or current.street != street:
            current.valid_to = snapshot_date
            current.is_current = False
            new = DimInvestment(
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


class FactChangeRepository(BaseRepository[FactChange]):
    def insert_or_ignore(self, record: FactChange) -> None:
        self._session.execute(
            insert(FactChange)
            .values(
                fk_time=record.fk_time,
                fk_investment=record.fk_investment,
                fk_unit_status=record.fk_unit_status,
                fk_location=record.fk_location,
                unit_id=record.unit_id,
                download_url=record.download_url,
                is_first_snapshot=record.is_first_snapshot,
                is_price_changed=record.is_price_changed,
                is_status_changed=record.is_status_changed,
                is_price_drop=record.is_price_drop,
                unit_value_pln=record.unit_value_pln,
                prev_price=record.prev_price,
                change_amount_pln=record.change_amount_pln,
                price_per_m2_pln=record.price_per_m2_pln,
            )
            .on_conflict_do_nothing(index_elements=["download_url", "unit_id"])
        )

    def insert_or_ignore_batch(self, records: list[FactChange]) -> int:
        if not records:
            return 0
        rows = [
            dict(
                fk_time=r.fk_time,
                fk_investment=r.fk_investment,
                fk_unit_status=r.fk_unit_status,
                fk_location=r.fk_location,
                unit_id=r.unit_id,
                download_url=r.download_url,
                is_first_snapshot=r.is_first_snapshot,
                is_price_changed=r.is_price_changed,
                is_status_changed=r.is_status_changed,
                is_price_drop=r.is_price_drop,
                unit_value_pln=r.unit_value_pln,
                prev_price=r.prev_price,
                change_amount_pln=r.change_amount_pln,
                price_per_m2_pln=r.price_per_m2_pln,
            )
            for r in records
        ]
        self._session.execute(
            insert(FactChange)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["download_url", "unit_id"])
        )
        return len(rows)


# ── Kaggle repositories ───────────────────────────────────────────────────────


class DimLokalizacjaRepository(BaseRepository[DimLokalizacja]):
    def insert_or_ignore(self, record: DimLokalizacja) -> None:
        self._session.add(record)

    def insert_or_ignore_batch(self, records: list[DimLokalizacja]) -> int:
        self._session.add_all(records)
        return len(records)

    def _get(
        self, miasto: str, lat_r: float | None, lon_r: float | None
    ) -> DimLokalizacja | None:
        return (
            self._session.query(DimLokalizacja)
            .filter(
                DimLokalizacja.miasto == miasto,
                DimLokalizacja.lat_r == lat_r,
                DimLokalizacja.lon_r == lon_r,
            )
            .first()
        )

    def get_or_create_id(
        self,
        miasto: str,
        latitude: float | None,
        longitude: float | None,
    ) -> int:
        lat_r = round(latitude, 3) if latitude is not None else None
        lon_r = round(longitude, 3) if longitude is not None else None
        row = self._get(miasto, lat_r, lon_r)
        if row:
            return row.id
        new = DimLokalizacja(
            miasto=miasto,
            latitude=latitude,
            longitude=longitude,
            lat_r=lat_r,
            lon_r=lon_r,
        )
        self._session.add(new)
        self._session.flush()
        return new.id


class DimTypLokaluRepository(BaseRepository[DimTypLokalu]):
    def insert_or_ignore(self, record: DimTypLokalu) -> None:
        self._session.add(record)

    def insert_or_ignore_batch(self, records: list[DimTypLokalu]) -> int:
        self._session.add_all(records)
        return len(records)

    def get_or_create_id(self, type_hash: str, **attrs: object) -> int:
        row = (
            self._session.query(DimTypLokalu)
            .filter(DimTypLokalu.type_hash == type_hash)
            .first()
        )
        if row:
            return row.id
        new = DimTypLokalu(type_hash=type_hash, **attrs)  # type: ignore[arg-type]
        self._session.add(new)
        self._session.flush()
        return new.id


class DimTypRynkuRepository(BaseRepository[DimTypRynku]):
    def insert_or_ignore(self, record: DimTypRynku) -> None:
        self._session.add(record)

    def insert_or_ignore_batch(self, records: list[DimTypRynku]) -> int:
        self._session.add_all(records)
        return len(records)

    _LABELS: dict[str, str] = {
        "pierwotny": "Rynek pierwotny",
        "wtorny": "Rynek wtórny",
        "nieznany": "Nieznany",
    }

    def get_or_create_id(self, rynek_kod: str) -> int:
        row = (
            self._session.query(DimTypRynku)
            .filter(DimTypRynku.rynek_kod == rynek_kod)
            .first()
        )
        if row:
            return row.id
        new = DimTypRynku(
            rynek_kod=rynek_kod,
            rynek_label=self._LABELS.get(rynek_kod, rynek_kod),
        )
        self._session.add(new)
        self._session.flush()
        return new.id


class FactOfertaNieruchomosciRepository(BaseRepository[FactOfertaNieruchomosci]):
    def insert_or_ignore(self, record: FactOfertaNieruchomosci) -> None:
        self._session.add(record)

    def insert_or_ignore_batch(self, records: list[FactOfertaNieruchomosci]) -> int:
        if not records:
            return 0
        rows = [
            dict(
                fk_czas=r.fk_czas,
                fk_lokalizacja=r.fk_lokalizacja,
                fk_typ_lokalu=r.fk_typ_lokalu,
                fk_typ_rynku=r.fk_typ_rynku,
                listing_id=r.listing_id,
                cena_calkowita_pln=r.cena_calkowita_pln,
                powierzchnia_m2=r.powierzchnia_m2,
                cena_m2_pln=r.cena_m2_pln,
                liczba_ofert=r.liczba_ofert,
            )
            for r in records
        ]
        self._session.execute(
            insert(FactOfertaNieruchomosci)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["listing_id"])
        )
        return len(rows)
