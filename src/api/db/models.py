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
    raw_path: Mapped[str | None] = mapped_column(Text, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    first_seen_at: Mapped[str] = mapped_column(server_default=func.now(), init=False)
    last_seen_at: Mapped[str] = mapped_column(server_default=func.now(), init=False)


# ── Dimensions ───────────────────────────────────────────────────────────────


class DimTime(MappedAsDataclass, Base):
    __tablename__ = "Dim_Time"

    # id = YYYYMMDD integer — natural, compact, sortable
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, unique=True)
    year: Mapped[int] = mapped_column(SmallInteger)
    quarter: Mapped[int] = mapped_column(SmallInteger)
    month: Mapped[int] = mapped_column(SmallInteger)
    day: Mapped[int] = mapped_column(SmallInteger)
    day_of_week: Mapped[int] = mapped_column(SmallInteger)


class DimLocation(MappedAsDataclass, Base):
    __tablename__ = "Dim_Location"

    city_norm: Mapped[str] = mapped_column(String, unique=True)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimUnitStatus(MappedAsDataclass, Base):
    __tablename__ = "Dim_Unit_Status"

    status_norm: Mapped[str] = mapped_column(String(20), unique=True)
    status_label: Mapped[str | None] = mapped_column(String, default=None)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimInvestment(MappedAsDataclass, Base):
    """SCD Type 2 — keeps full history of investment attribute changes."""

    __tablename__ = "Dim_Investment"

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


class FactChange(MappedAsDataclass, Base):
    """One row per (unit, snapshot) where price OR status changed."""

    __tablename__ = "Fact_Change"
    __table_args__ = (UniqueConstraint("download_url", "unit_id"),)

    fk_time: Mapped[int] = mapped_column(ForeignKey("Dim_Time.id"))
    fk_investment: Mapped[int] = mapped_column(ForeignKey("Dim_Investment.id"))
    fk_unit_status: Mapped[int] = mapped_column(ForeignKey("Dim_Unit_Status.id"))
    fk_location: Mapped[int] = mapped_column(ForeignKey("Dim_Location.id"))
    unit_id: Mapped[str] = mapped_column(String)
    download_url: Mapped[str] = mapped_column(String)

    is_first_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_price_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_status_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_price_drop: Mapped[bool] = mapped_column(Boolean, default=False)
    unit_value_pln: Mapped[float | None] = mapped_column(Float, default=None)
    prev_price: Mapped[float | None] = mapped_column(Float, default=None)
    change_amount_pln: Mapped[float | None] = mapped_column(Float, default=None)
    price_per_m2_pln: Mapped[float | None] = mapped_column(Float, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
