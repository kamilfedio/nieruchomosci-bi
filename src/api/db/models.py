"""SQLAlchemy ORM models"""

import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )


class ColumnMappingCache(MappedAsDataclass, Base):
    __tablename__ = "column_mapping_cache"

    cache_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    mapping: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )


class StagingRejectedRecord(MappedAsDataclass, Base):
    """Rows rejected by DQ checks — written by DQChecker.save_rejected()."""

    __tablename__ = "stg_rejected_records"

    # Required fields first (no default)
    source: Mapped[str] = mapped_column(String(64))
    rule_name: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    # Optional fields (have default)
    batch_id: Mapped[str | None] = mapped_column(String(32), default=None)
    rule_description: Mapped[str | None] = mapped_column(Text, default=None)
    row_data: Mapped[dict | None] = mapped_column(JSONB, default=None)
    # Server-managed (init=False)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    rejected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )


class GeocodingCache(MappedAsDataclass, Base):
    """Persistent cache of address → (lat, lon) from Google Maps Geocoding API."""

    __tablename__ = "geocoding_cache"

    cache_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    address: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float, default=None)
    longitude: Mapped[float | None] = mapped_column(Float, default=None)
    geocoded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )


# ── Dimensions ───────────────────────────────────────────────────────────────


class DimTime(MappedAsDataclass, Base):
    __tablename__ = "Dim_Time"

    # id = YYYYMMDD integer — natural, compact, sortable
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, unique=True)
    year: Mapped[int] = mapped_column(SmallInteger)
    quarter: Mapped[int] = mapped_column(SmallInteger)
    month: Mapped[int] = mapped_column(SmallInteger)
    week: Mapped[int] = mapped_column(SmallInteger)
    day: Mapped[int] = mapped_column(SmallInteger)
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    day_name: Mapped[str] = mapped_column(String(10))
    month_name: Mapped[str] = mapped_column(String(10))
    year_quarter: Mapped[str] = mapped_column(String(7))
    is_weekend: Mapped[bool] = mapped_column(Boolean)


class DimLocation(MappedAsDataclass, Base):
    __tablename__ = "Dim_Location"

    city_norm: Mapped[str] = mapped_column(String, unique=True)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimUnitStatus(MappedAsDataclass, Base):
    __tablename__ = "Dim_Unit_Status"

    status_norm: Mapped[str] = mapped_column(String(20), unique=True)
    status_label: Mapped[str | None] = mapped_column(String, default=None)
    status_group: Mapped[str] = mapped_column(String(20), default="INACTIVE")
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimInvestment(MappedAsDataclass, Base):
    """SCD Type 2 — keeps full history of investment attribute changes."""

    __tablename__ = "Dim_Investment"

    valid_from: Mapped[datetime.date] = mapped_column(Date)
    developer_name: Mapped[str | None] = mapped_column(Text, default=None)
    investment_id: Mapped[str | None] = mapped_column(String, default=None)
    investment_name: Mapped[str | None] = mapped_column(Text, default=None)
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
    has_security: Mapped[bool | None] = mapped_column(Boolean, default=None)
    ownership_form: Mapped[str | None] = mapped_column(String(30), default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimMarketType(MappedAsDataclass, Base):
    """SCD1 · primary / secondary / unknown."""

    __tablename__ = "Dim_Market_Type"

    market_code: Mapped[str] = mapped_column(String(20), unique=True)
    market_label: Mapped[str | None] = mapped_column(String(50), default=None)
    segment_nbp: Mapped[str | None] = mapped_column(String(5), default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimDemographics(MappedAsDataclass, Base):
    """Snapshot roczny wskaźników demograficznych — ziarno: city × year."""

    __tablename__ = "Dim_Demographics"
    __table_args__ = (UniqueConstraint("teryt", "year"),)

    teryt: Mapped[str] = mapped_column(String(12))
    year: Mapped[int] = mapped_column(SmallInteger)
    city: Mapped[str] = mapped_column(String)
    population: Mapped[int | None] = mapped_column(Integer, default=None)
    avg_gross_salary: Mapped[float | None] = mapped_column(Float, default=None)
    unemployment_rate: Mapped[float | None] = mapped_column(Float, default=None)
    migration_balance: Mapped[int | None] = mapped_column(Integer, default=None)
    working_age_population: Mapped[int | None] = mapped_column(Integer, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class DimFloodRisk(MappedAsDataclass, Base):
    """SCD0 · 4-row flood risk dictionary (id 0–3)."""

    __tablename__ = "Dim_Flood_Risk"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario: Mapped[str] = mapped_column(String(10), unique=True)
    risk_class: Mapped[str] = mapped_column(String(10))
    numeric_risk_class: Mapped[int | None] = mapped_column(Integer, default=None)
    description: Mapped[str | None] = mapped_column(String, default=None)
    depth_m: Mapped[float | None] = mapped_column(Float, default=None)


class FloodZone(Base):
    """Flood hazard polygons from MZP WFS — full refresh on each load."""

    __tablename__ = "flood_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario: Mapped[str] = mapped_column(String(10))
    risk_class: Mapped[str] = mapped_column(String(10))
    depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    fk_flood_risk: Mapped[int] = mapped_column(ForeignKey("Dim_Flood_Risk.id"))
    geom = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(20))


# ── Fact ─────────────────────────────────────────────────────────────────────


class FactChange(MappedAsDataclass, Base):
    """One row per (unit, snapshot) where price OR status changed."""

    __tablename__ = "Fact_Change"
    __table_args__ = (UniqueConstraint("download_url", "unit_id", "fk_time"),)

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
    prev_status: Mapped[str | None] = mapped_column(String(20), default=None)
    change_amount_pln: Mapped[float | None] = mapped_column(Float, default=None)
    price_per_m2_pln: Mapped[float | None] = mapped_column(Float, default=None)
    fk_flood_risk: Mapped[int | None] = mapped_column(
        ForeignKey("Dim_Flood_Risk.id"), default=None
    )

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class FactBenchmarkNbp(MappedAsDataclass, Base):
    """Grain: city × quarter × market type — quarterly NBP BaRN snapshot."""

    __tablename__ = "Fact_Benchmark_NBP"
    __table_args__ = (UniqueConstraint("fk_time", "fk_location", "fk_market_type"),)

    fk_time: Mapped[int] = mapped_column(ForeignKey("Dim_Time.id"))
    fk_location: Mapped[int] = mapped_column(ForeignKey("Dim_Location.id"))
    fk_market_type: Mapped[int] = mapped_column(ForeignKey("Dim_Market_Type.id"))
    avg_offer_price_m2_pln: Mapped[float | None] = mapped_column(Float, default=None)
    avg_transaction_price_m2_pln: Mapped[float | None] = mapped_column(
        Float, default=None
    )
    hedonic_index: Mapped[float | None] = mapped_column(Float, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)


class FactListing(MappedAsDataclass, Base):
    """Grain: one Kaggle listing at one snapshot date."""

    __tablename__ = "Fact_Listing"
    __table_args__ = (UniqueConstraint("listing_id", "fk_time"),)

    fk_time: Mapped[int] = mapped_column(ForeignKey("Dim_Time.id"))
    fk_geo_location: Mapped[int] = mapped_column(ForeignKey("Dim_Geo_Location.id"))
    fk_unit_type: Mapped[int] = mapped_column(ForeignKey("Dim_Unit_Type.id"))
    fk_market_type: Mapped[int] = mapped_column(ForeignKey("Dim_Market_Type.id"))
    listing_id: Mapped[str] = mapped_column(String)
    total_price_pln: Mapped[float] = mapped_column(Float)
    area_m2: Mapped[float] = mapped_column(Float)
    fk_flood_risk: Mapped[int | None] = mapped_column(
        ForeignKey("Dim_Flood_Risk.id"), default=None
    )
    fk_demographics: Mapped[int | None] = mapped_column(
        ForeignKey("Dim_Demographics.id"), default=None
    )
    price_per_m2_pln: Mapped[float | None] = mapped_column(Float, default=None)
    listing_count: Mapped[int] = mapped_column(SmallInteger, default=1)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
