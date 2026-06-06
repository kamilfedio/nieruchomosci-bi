"""Kaggle loader — FK lookup + load into Kaggle dimensional model."""

import datetime
import hashlib
from pathlib import Path

import polars as pl
from loguru import logger
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import FactListing
from src.api.db.repositories.dimensions import (
    DimDemographicsRepository,
    DimFloodRiskRepository,
    DimGeoLocationRepository,
    DimMarketTypeRepository,
    DimTimeRepository,
    DimUnitTypeRepository,
    FactListingRepository,
)
from src.api.db.repositories.flood_zones import FloodZoneRepository

from .base import BaseLoader

_BATCH_SIZE = 500

# Kaggle dataset uses ASCII city names; GUS BDL uses Polish diacritics.
# Map ASCII → canonical Polish form for fk_demographics lookup.
_CITY_CANONICAL: dict[str, str] = {
    "krakow": "kraków",
    "wroclaw": "wrocław",
    "lodz": "łódź",
    "gdansk": "gdańsk",
    "poznan": "poznań",
    "lublin": "lublin",
    "szczecin": "szczecin",
    "katowice": "katowice",
    "bydgoszcz": "bydgoszcz",
    "warszawa": "warszawa",
}

_TYPE_ATTRS = [
    "market_type",
    "rooms",
    "floor",
    "floor_count",
    "build_year",
    "building_material_norm",
    "condition_norm",
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
        engine = build_engine(self._config.database_url)
        init_db(engine)

        df = pl.read_parquet(self._source_path)
        if df.is_empty():
            logger.info("No listings to load")
            return 0

        # Pre-load demographics map to avoid per-row DB queries
        with get_session(engine) as session:
            demo_map = DimDemographicsRepository(session).load_city_year_map()

        total = 0
        with get_session(engine) as session:
            DimFloodRiskRepository(session).seed()
            dim_time = DimTimeRepository(session)
            dim_geo = DimGeoLocationRepository(session)
            dim_unit = DimUnitTypeRepository(session)
            dim_market = DimMarketTypeRepository(session)
            fact_repo = FactListingRepository(session)
            zone_repo = FloodZoneRepository(session)

            for batch_start in range(0, len(df), _BATCH_SIZE):
                batch = df[batch_start : batch_start + _BATCH_SIZE]
                batch_rows = list(batch.iter_rows(named=True))

                points: list[tuple[str, float, float]] = []
                for row in batch_rows:
                    lat = row.get("latitude")
                    lon = row.get("longitude")
                    listing_id = str(row.get("id") or "")
                    if lat is not None and lon is not None and listing_id:
                        points.append((listing_id, float(lon), float(lat)))

                flood_map = zone_repo.lookup_flood_risk_ids(points)

                facts: list[FactListing] = []

                for row in batch_rows:
                    snapshot_date: datetime.date | None = row.get("snapshot_date")
                    if snapshot_date is None:
                        continue

                    fk_time = dim_time.get_or_create(snapshot_date)

                    fk_geo = dim_geo.get_or_create_id(
                        city=row.get("city_norm") or row.get("city") or "UNKNOWN",
                        latitude=row.get("latitude"),
                        longitude=row.get("longitude"),
                    )

                    th = _type_hash(row)
                    fk_unit = dim_unit.get_or_create_id(
                        type_hash=th,
                        market_type=row.get("market_type"),
                        rooms=_to_int(row.get("rooms")),
                        floor=_to_int(row.get("floor")),
                        floor_count=_to_int(row.get("floor_count")),
                        build_year=_to_int(row.get("build_year")),
                        building_material=row.get("building_material_norm"),
                        condition=row.get("condition_norm"),
                        has_balcony=row.get("has_balcony"),
                        has_elevator=row.get("has_elevator"),
                        has_parking=row.get("has_parking_space"),
                        has_storage=row.get("has_storage_room"),
                    )

                    fk_market = dim_market.get_or_create_id(
                        row.get("market_type") or "unknown"
                    )

                    price = row.get("price")
                    area = row.get("square_meters")
                    if price is None or area is None:
                        continue

                    fk_flood = flood_map.get(str(row.get("id") or ""), 0)

                    city_raw = row.get("city_norm") or row.get("city") or ""
                    city_norm = _CITY_CANONICAL.get(city_raw, city_raw)
                    year = snapshot_date.year if snapshot_date else None
                    fk_demo: int | None = None
                    if city_norm and year:
                        fk_demo = demo_map.get((city_norm, year)) or demo_map.get(
                            (city_norm, year - 1)
                        )

                    facts.append(
                        FactListing(
                            fk_time=fk_time,
                            fk_geo_location=fk_geo,
                            fk_unit_type=fk_unit,
                            fk_market_type=fk_market,
                            listing_id=str(row.get("id") or ""),
                            total_price_pln=float(price),
                            area_m2=float(area),
                            fk_flood_risk=fk_flood,
                            fk_demographics=fk_demo,
                            price_per_m2_pln=row.get("price_per_m2_pln"),
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
