"""Integration tests for MZPLoader — verifies Dim_Flood_Risk seeding."""

from src.api.db.connection import get_session
from src.api.db.models import DimFloodRisk
from src.api.loaders.mzp_loader import MZPLoader


def test_load_seeds_four_rows(tmp_path, test_config, db_engine):
    count = MZPLoader(source_path=tmp_path / "dummy.geojson", config=test_config).load()
    assert count == 4

    with get_session(db_engine) as session:
        assert session.query(DimFloodRisk).count() == 4


def test_load_seeds_correct_scenarios(tmp_path, test_config, db_engine):
    MZPLoader(source_path=tmp_path / "dummy.geojson", config=test_config).load()

    with get_session(db_engine) as session:
        scenarios = {r.scenario for r in session.query(DimFloodRisk).all()}

    assert scenarios == {"none", "Q10%", "Q1%", "Q0.2%"}


def test_load_seeds_correct_risk_classes(tmp_path, test_config, db_engine):
    MZPLoader(source_path=tmp_path / "dummy.geojson", config=test_config).load()

    with get_session(db_engine) as session:
        by_scenario = {r.scenario: r.risk_class for r in session.query(DimFloodRisk).all()}

    assert by_scenario["none"] == "none"
    assert by_scenario["Q10%"] == "high"
    assert by_scenario["Q1%"] == "medium"
    assert by_scenario["Q0.2%"] == "low"


def test_load_is_idempotent(tmp_path, test_config, db_engine):
    loader = MZPLoader(source_path=tmp_path / "dummy.geojson", config=test_config)
    loader.load()
    count2 = loader.load()
    assert count2 == 4

    with get_session(db_engine) as session:
        assert session.query(DimFloodRisk).count() == 4


def test_load_fixed_primary_keys(tmp_path, test_config, db_engine):
    """IDs must be stable: 0=none, 1=Q10%, 2=Q1%, 3=Q0.2%."""
    MZPLoader(source_path=tmp_path / "dummy.geojson", config=test_config).load()

    with get_session(db_engine) as session:
        by_id = {r.id: r.scenario for r in session.query(DimFloodRisk).all()}

    assert by_id[0] == "none"
    assert by_id[1] == "Q10%"
    assert by_id[2] == "Q1%"
    assert by_id[3] == "Q0.2%"
