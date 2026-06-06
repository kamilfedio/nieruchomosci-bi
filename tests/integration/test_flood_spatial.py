"""Integration tests for PostGIS flood risk spatial join in KaggleLoader."""

import datetime
import json

import pytest
from src.api.db.connection import get_session
from src.api.db.models import FactListing
from src.api.loaders.kaggle_loader import KaggleLoader
from src.api.loaders.mzp_loader import MZPLoader

from tests.conftest import make_processed_parquet


def _flood_geojson(path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [21.0, 52.2],
                                    [21.01, 52.2],
                                    [21.01, 52.21],
                                    [21.0, 52.21],
                                    [21.0, 52.2],
                                ]
                            ],
                        },
                        "properties": {
                            "scenario": "Q10%",
                            "risk_class": "high",
                            "depth_m": None,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def seeded_flood_zones(tmp_path, test_config, db_engine):
    geojson = tmp_path / "zones.geojson"
    _flood_geojson(geojson)
    MZPLoader(source_path=geojson, config=test_config).load()
    return db_engine


def test_listing_inside_zone_gets_fk_flood_risk_1(
    tmp_path, test_config, seeded_flood_zones, seeded_market_types
):
    parquet = make_processed_parquet(
        tmp_path,
        "kaggle",
        {
            "id": ["L1"],
            "price": [500_000.0],
            "square_meters": [50.0],
            "city": ["warszawa"],
            "city_norm": ["warszawa"],
            "type": ["apartmentBuilding"],
            "market_type": ["primary"],
            "latitude": [52.205],
            "longitude": [21.005],
            "snapshot_date": [datetime.date(2024, 1, 15)],
            "price_per_m2_pln": [10_000.0],
        },
    )

    KaggleLoader(source_path=parquet, config=test_config).load()

    with get_session(seeded_flood_zones) as session:
        row = session.query(FactListing).filter(FactListing.listing_id == "L1").one()
        assert row.fk_flood_risk == 1


def test_listing_outside_zone_gets_fk_flood_risk_0(
    tmp_path, test_config, seeded_flood_zones, seeded_market_types
):
    parquet = make_processed_parquet(
        tmp_path,
        "kaggle",
        {
            "id": ["L2"],
            "price": [500_000.0],
            "square_meters": [50.0],
            "city": ["warszawa"],
            "city_norm": ["warszawa"],
            "type": ["apartmentBuilding"],
            "market_type": ["primary"],
            "latitude": [50.0],
            "longitude": [20.0],
            "snapshot_date": [datetime.date(2024, 1, 15)],
            "price_per_m2_pln": [10_000.0],
        },
    )

    KaggleLoader(source_path=parquet, config=test_config).load()

    with get_session(seeded_flood_zones) as session:
        row = session.query(FactListing).filter(FactListing.listing_id == "L2").one()
        assert row.fk_flood_risk == 0
