"""Unit tests for MZPTransformer."""

import json
from pathlib import Path

from src.api.transformers.mzp_transformer import MZPTransformer, _RETURN_PERIOD_MAP


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_feature(return_period: int, geom: dict | None = None) -> dict:
    geom = geom or {
        "type": "Polygon",
        "coordinates": [[[20.0, 51.0], [21.0, 51.0], [21.0, 52.0], [20.0, 52.0], [20.0, 51.0]]],
    }
    return {
        "type": "Feature",
        "geometry": geom,
        "properties": {
            "likelihoodOfOccurrence": {
                "LikelihoodOfOccurrence": {
                    "quantitativeLikelihood": {
                        "QuantitativeLikelihood": {
                            "returnPeriod": return_period
                        }
                    }
                }
            },
            "magnitudeOrIntensity": None,
        },
    }


def _make_raw_geojson(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _run_transformer(tmp_path: Path, features: list[dict]) -> list[dict]:
    raw_path = tmp_path / "raw.geojson"
    out_dir = tmp_path / "processed"
    raw_path.write_text(json.dumps(_make_raw_geojson(features)), encoding="utf-8")

    # Patch the fixed output path so tests don't write to the real filesystem
    import src.api.transformers.mzp_transformer as mzp_mod
    orig = mzp_mod._OUTPUT_PATH
    mzp_mod._OUTPUT_PATH = out_dir / "flood_zones.geojson"
    try:
        t = MZPTransformer(source_path=raw_path)
        out = t.run()
        return json.loads(out.read_text())["features"]
    finally:
        mzp_mod._OUTPUT_PATH = orig


# ── _RETURN_PERIOD_MAP ────────────────────────────────────────────────────────


def test_return_period_map_values():
    assert _RETURN_PERIOD_MAP[10] == "Q10%"
    assert _RETURN_PERIOD_MAP[100] == "Q1%"
    assert _RETURN_PERIOD_MAP[500] == "Q0.2%"


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_processes_valid_feature(tmp_path):
    features = _run_transformer(tmp_path, [_make_feature(10)])
    # +1 for "none" sentinel
    assert len(features) == 2
    assert features[0]["properties"]["scenario"] == "Q10%"
    assert features[0]["properties"]["risk_class"] == "high"


def test_run_skips_unknown_return_period(tmp_path):
    feat = _make_feature(999)  # not in _RETURN_PERIOD_MAP
    features = _run_transformer(tmp_path, [feat])
    # Only sentinel row should remain
    assert len(features) == 1
    assert features[0]["properties"]["scenario"] == "none"


def test_run_appends_none_sentinel(tmp_path):
    features = _run_transformer(tmp_path, [_make_feature(100)])
    sentinel = features[-1]
    assert sentinel["properties"]["scenario"] == "none"
    assert sentinel["geometry"] is None


def test_run_skips_null_geometry(tmp_path):
    feat = _make_feature(10)
    feat["geometry"] = None
    features = _run_transformer(tmp_path, [feat])
    non_sentinel = [f for f in features if f["properties"]["scenario"] != "none"]
    assert len(non_sentinel) == 0


def test_run_all_three_risk_scenarios(tmp_path):
    feats = [_make_feature(rp) for rp in (10, 100, 500)]
    features = _run_transformer(tmp_path, feats)
    scenarios = {f["properties"]["scenario"] for f in features}
    assert {"Q10%", "Q1%", "Q0.2%", "none"}.issubset(scenarios)


def test_run_risk_class_mapping(tmp_path):
    feats = [_make_feature(rp) for rp in (10, 100, 500)]
    features = [f for f in _run_transformer(tmp_path, feats)
                if f["properties"]["scenario"] != "none"]
    risk_by_scenario = {f["properties"]["scenario"]: f["properties"]["risk_class"]
                        for f in features}
    assert risk_by_scenario["Q10%"] == "high"
    assert risk_by_scenario["Q1%"] == "medium"
    assert risk_by_scenario["Q0.2%"] == "low"


def test_run_output_is_feature_collection(tmp_path):
    raw_path = tmp_path / "raw.geojson"
    out_path = tmp_path / "out.geojson"
    raw_path.write_text(json.dumps(_make_raw_geojson([])))
    import src.api.transformers.mzp_transformer as mzp_mod
    orig = mzp_mod._OUTPUT_PATH
    mzp_mod._OUTPUT_PATH = out_path
    try:
        MZPTransformer(source_path=raw_path).run()
        data = json.loads(out_path.read_text())
        assert data["type"] == "FeatureCollection"
        assert isinstance(data["features"], list)
    finally:
        mzp_mod._OUTPUT_PATH = orig
