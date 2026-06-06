"""Integration tests for MZPLoader — Dim_Flood_Risk seed + PostGIS geometries."""

import json

import pytest
from src.api.db.connection import get_session
from src.api.db.models import DimFloodRisk, FloodZone
from src.api.loaders.mzp_loader import MZPLoader


def _sample_geojson(path, features: list[dict] | None = None) -> None:
    if features is None:
        features = [
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
        ]
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


@pytest.fixture
def geojson_path(tmp_path):
    path = tmp_path / "flood_zones.geojson"
    _sample_geojson(path)
    return path


def test_load_seeds_dim_flood_risk(geojson_path, test_config, db_engine):
    MZPLoader(source_path=geojson_path, config=test_config).load()

    with get_session(db_engine) as session:
        assert session.query(DimFloodRisk).count() == 4


def test_load_inserts_geometry(geojson_path, test_config, db_engine):
    count = MZPLoader(source_path=geojson_path, config=test_config).load()
    assert count == 1

    with get_session(db_engine) as session:
        assert session.query(FloodZone).count() == 1


def test_load_seeds_correct_scenarios(geojson_path, test_config, db_engine):
    MZPLoader(source_path=geojson_path, config=test_config).load()

    with get_session(db_engine) as session:
        scenarios = {r.scenario for r in session.query(DimFloodRisk).all()}

    assert scenarios == {"none", "Q10%", "Q1%", "Q0.2%"}


def test_load_seeds_correct_risk_classes(geojson_path, test_config, db_engine):
    MZPLoader(source_path=geojson_path, config=test_config).load()

    with get_session(db_engine) as session:
        by_scenario = {
            r.scenario: r.risk_class for r in session.query(DimFloodRisk).all()
        }

    assert by_scenario["none"] == "none"
    assert by_scenario["Q10%"] == "high"
    assert by_scenario["Q1%"] == "medium"
    assert by_scenario["Q0.2%"] == "low"


def test_load_is_idempotent(geojson_path, test_config, db_engine):
    loader = MZPLoader(source_path=geojson_path, config=test_config)
    loader.load()
    count2 = loader.load()
    assert count2 == 1

    with get_session(db_engine) as session:
        assert session.query(FloodZone).count() == 1


def test_load_fixed_primary_keys(geojson_path, test_config, db_engine):
    """IDs must be stable: 0=none, 1=Q10%, 2=Q1%, 3=Q0.2%."""
    MZPLoader(source_path=geojson_path, config=test_config).load()

    with get_session(db_engine) as session:
        by_id = {r.id: r.scenario for r in session.query(DimFloodRisk).all()}

    assert by_id[0] == "none"
    assert by_id[1] == "Q10%"
    assert by_id[2] == "Q1%"
    assert by_id[3] == "Q0.2%"
