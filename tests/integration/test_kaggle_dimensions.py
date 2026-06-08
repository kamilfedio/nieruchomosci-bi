"""Integration tests for Kaggle dimension repositories."""

from src.api.db.connection import get_session
from src.api.db.models import DimGeoLocation, DimMarketType, DimUnitType
from src.api.db.repositories.dimensions import (
    DimGeoLocationRepository,
    DimMarketTypeRepository,
    DimUnitTypeRepository,
)


def test_dim_geo_location_get_or_create_is_idempotent(db_engine):
    with get_session(db_engine) as session:
        repo = DimGeoLocationRepository(session)
        id1 = repo.get_or_create_id("warszawa", 52.19395, 21.02393)
        id2 = repo.get_or_create_id("warszawa", 52.19395, 21.02393)
        assert id1 == id2

    with get_session(db_engine) as session:
        assert session.query(DimGeoLocation).count() == 1


def test_dim_unit_type_get_or_create_is_idempotent(db_engine):
    attrs = {
        "market_type": "primary",
        "rooms": 3,
        "floor": 2,
        "floor_count": 10,
        "build_year": 2010,
        "building_material": "brick",
        "condition": "high",
        "has_balcony": True,
        "has_elevator": False,
        "has_parking": True,
        "has_storage": False,
    }
    with get_session(db_engine) as session:
        repo = DimUnitTypeRepository(session)
        id1 = repo.get_or_create_id("abc123", **attrs)
        id2 = repo.get_or_create_id("abc123", **attrs)
        assert id1 == id2

    with get_session(db_engine) as session:
        assert session.query(DimUnitType).count() == 1


def test_dim_market_type_get_or_create_is_idempotent(db_engine):
    with get_session(db_engine) as session:
        repo = DimMarketTypeRepository(session)
        id1 = repo.get_or_create_id("primary")
        id2 = repo.get_or_create_id("primary")
        assert id1 == id2

    with get_session(db_engine) as session:
        assert session.query(DimMarketType).count() == 1
