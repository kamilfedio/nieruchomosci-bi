"""SQLAlchemy ORM models"""

import datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class Base(DeclarativeBase):
    pass


# ── Operational ──────────────────────────────────────────────────────────────


class DeveloperFile(MappedAsDataclass, Base):
    __tablename__ = "developer_files"

    download_url: Mapped[str] = mapped_column(String, unique=True)
    developer_name: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    regon: Mapped[str | None] = mapped_column(String(14), default=None)
    file_format: Mapped[str | None] = mapped_column(String(20), default=None)
    institution_city: Mapped[str | None] = mapped_column(
        String, default=None, index=True
    )
    data_date: Mapped[str | None] = mapped_column(String(10), default=None)
    dataset_url: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    first_seen_at: Mapped[str] = mapped_column(server_default=func.now(), init=False)
    last_seen_at: Mapped[str] = mapped_column(server_default=func.now(), init=False)


# ── Dimensions ───────────────────────────────────────────────────────────────


class DimCzas(MappedAsDataclass, Base):
    __tablename__ = "Dim_Czas"

    # id = YYYYMMDD integer — natural, compact, sortable
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, unique=True)
    year: Mapped[int] = mapped_column(SmallInteger)
    quarter: Mapped[int] = mapped_column(SmallInteger)
    month: Mapped[int] = mapped_column(SmallInteger)
    day: Mapped[int] = mapped_column(SmallInteger)
    day_of_week: Mapped[int] = mapped_column(SmallInteger)


class DimLokalizacja(MappedAsDataclass, Base):
    __tablename__ = "Dim_Lokalizacja"

    miasto_norm: Mapped[str] = mapped_column(String, unique=True)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimStatusLokalu(MappedAsDataclass, Base):
    __tablename__ = "Dim_Status_Lokalu"

    status_norm: Mapped[str] = mapped_column(String(20), unique=True)
    status_label: Mapped[str | None] = mapped_column(String, default=None)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimInwestycja(MappedAsDataclass, Base):
    """SCD Type 2 — keeps full history of investment attribute changes."""

    __tablename__ = "Dim_Inwestycja"

    valid_from: Mapped[datetime.date] = mapped_column(Date)

    developer_name: Mapped[str | None] = mapped_column(Text, default=None)
    investment_id: Mapped[str | None] = mapped_column(String, default=None)
    regon: Mapped[str | None] = mapped_column(String(14), default=None)
    city: Mapped[str | None] = mapped_column(String, default=None)
    street: Mapped[str | None] = mapped_column(String, default=None)
    valid_to: Mapped[datetime.date | None] = mapped_column(Date, default=None)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


# ── Fact ─────────────────────────────────────────────────────────────────────


class FactZmiana(MappedAsDataclass, Base):
    """One row per (unit, snapshot) where price OR status changed."""

    __tablename__ = "Fact_Zmiana"
    __table_args__ = (UniqueConstraint("download_url", "unit_id"),)

    fk_czas: Mapped[int] = mapped_column(ForeignKey("Dim_Czas.id"))
    fk_inwestycja: Mapped[int] = mapped_column(ForeignKey("Dim_Inwestycja.id"))
    fk_status_lokalu: Mapped[int] = mapped_column(ForeignKey("Dim_Status_Lokalu.id"))
    fk_lokalizacja: Mapped[int] = mapped_column(ForeignKey("Dim_Lokalizacja.id"))
    unit_id: Mapped[str] = mapped_column(String)
    download_url: Mapped[str] = mapped_column(String)

    is_price_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_status_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_obnizka: Mapped[bool] = mapped_column(Boolean, default=False)
    wartosc_lokalu_pln: Mapped[float | None] = mapped_column(Float, default=None)
    prev_cena: Mapped[float | None] = mapped_column(Float, default=None)
    kwota_zmiany_pln: Mapped[float | None] = mapped_column(Float, default=None)
    cena_m2_pln: Mapped[float | None] = mapped_column(Float, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
