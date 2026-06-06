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


# ── Kaggle dimensions ────────────────────────────────────────────────────────


class DimGeoLocation(MappedAsDataclass, Base):
    """Grain: city + rounded lat/lon (3 dp ≈ 111 m)."""

    __tablename__ = "Dim_Geo_Location"
    __table_args__ = (UniqueConstraint("city", "lat_r", "lon_r"),)

    city: Mapped[str] = mapped_column(String)
    district: Mapped[str | None] = mapped_column(String, default=None)
    latitude: Mapped[float | None] = mapped_column(Float, default=None)
    longitude: Mapped[float | None] = mapped_column(Float, default=None)
    lat_r: Mapped[float | None] = mapped_column(Float, default=None)
    lon_r: Mapped[float | None] = mapped_column(Float, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimUnitType(MappedAsDataclass, Base):
    """SCD1 · unique combination of physical unit attributes."""

    __tablename__ = "Dim_Unit_Type"

    type_hash: Mapped[str] = mapped_column(String(32), unique=True)
    market_type: Mapped[str | None] = mapped_column(String(20), default=None)
    rooms: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    floor: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    floor_count: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    build_year: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    building_material: Mapped[str | None] = mapped_column(String(20), default=None)
    condition: Mapped[str | None] = mapped_column(String(20), default=None)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean, default=None)
    has_elevator: Mapped[bool | None] = mapped_column(Boolean, default=None)
    has_parking: Mapped[bool | None] = mapped_column(Boolean, default=None)
    has_storage: Mapped[bool | None] = mapped_column(Boolean, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimMarketType(MappedAsDataclass, Base):
    """SCD1 · primary / secondary / unknown."""

    __tablename__ = "Dim_Market_Type"

    market_code: Mapped[str] = mapped_column(String(20), unique=True)
    market_label: Mapped[str | None] = mapped_column(String(50), default=None)

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


class FactListing(MappedAsDataclass, Base):
    """Grain: one Kaggle listing."""

    __tablename__ = "Fact_Listing"

    fk_time: Mapped[int] = mapped_column(ForeignKey("Dim_Time.id"))
    fk_geo_location: Mapped[int] = mapped_column(ForeignKey("Dim_Geo_Location.id"))
    fk_unit_type: Mapped[int] = mapped_column(ForeignKey("Dim_Unit_Type.id"))
    fk_market_type: Mapped[int] = mapped_column(ForeignKey("Dim_Market_Type.id"))
    listing_id: Mapped[str] = mapped_column(String, unique=True)
    total_price_pln: Mapped[float] = mapped_column(Float)
    area_m2: Mapped[float] = mapped_column(Float)
    price_per_m2_pln: Mapped[float | None] = mapped_column(Float, default=None)
    listing_count: Mapped[int] = mapped_column(SmallInteger, default=1)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
