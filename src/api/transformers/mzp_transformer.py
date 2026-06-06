"""MZP transformer — processes raw WFS GeoJSON into flood zone features.

Steps:
  1. Map returnPeriod → scenario (Q10%/Q1%/Q0.2%)
  2. Extract depth_m from levelOfFlood
  3. Compute risk_class (high/medium/low)
  4. Validate geometry (Shapely is_valid, not is_empty)
  5. Simplify geometry (tolerance 0.0001°)
  6. Ensure CRS = EPSG:4326 (WFS request used SRSNAME=EPSG:4326)
  7. Append "no risk" sentinel row (geometry=null, scenario="none")
  8. Save to data/processed/mzp/flood_zones.geojson
"""

import json
from pathlib import Path

from loguru import logger
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

from .base import BaseTransformer

_RETURN_PERIOD_MAP: dict[int, str] = {10: "Q10%", 100: "Q1%", 500: "Q0.2%"}
_RISK_CLASS: dict[str, str] = {
    "Q10%": "high",
    "Q1%": "medium",
    "Q0.2%": "low",
    "none": "none",
}

_OUTPUT_PATH = Path("data/processed/mzp/flood_zones.geojson")


class MZPTransformer(BaseTransformer):
    @property
    def source_name(self) -> str:
        return "mzp"

    def read(self):  # type: ignore[override]
        pass  # not used — run() handles IO directly

    def transform(self, df):  # type: ignore[override]
        pass  # not used — run() handles IO directly

    def run(self) -> Path:  # type: ignore[override]
        logger.info("Starting MZP transformation from '{}'", self._source_path)

        raw = json.loads(self._source_path.read_text())
        features = raw.get("features") or []
        logger.info("Input: {} raw features", len(features))

        processed: list[dict] = []
        skipped = 0

        for feat in features:
            props = feat.get("properties") or {}
            geom_raw = feat.get("geometry")

            # ── returnPeriod → scenario ───────────────────────────────────
            rp = props.get("returnPeriod")
            try:
                scenario = _RETURN_PERIOD_MAP.get(int(rp), "unknown")
            except (TypeError, ValueError):
                scenario = "unknown"

            if scenario == "unknown":
                skipped += 1
                continue

            # ── levelOfFlood → depth_m ────────────────────────────────────
            try:
                depth_m = float(props.get("levelOfFlood") or "")
            except (TypeError, ValueError):
                depth_m = None

            risk_class = _RISK_CLASS[scenario]

            # ── geometry validation + simplification ──────────────────────
            if geom_raw is None:
                skipped += 1
                continue
            try:
                geom = shape(geom_raw)
                if geom.is_empty:
                    skipped += 1
                    continue
                if not geom.is_valid:
                    geom = make_valid(geom)
                geom = geom.simplify(0.0001, preserve_topology=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Invalid geometry skipped: {}", exc)
                skipped += 1
                continue

            processed.append(
                {
                    "type": "Feature",
                    "geometry": mapping(geom),
                    "properties": {
                        "scenario": scenario,
                        "risk_class": risk_class,
                        "depth_m": depth_m,
                    },
                }
            )

        # ── sentinel "no risk" row ────────────────────────────────────────
        processed.append(
            {
                "type": "Feature",
                "geometry": None,
                "properties": {
                    "scenario": "none",
                    "risk_class": "none",
                    "depth_m": None,
                },
            }
        )

        logger.info("Processed {} features, skipped {}", len(processed) - 1, skipped)

        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUTPUT_PATH.write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": processed},
                ensure_ascii=False,
            )
        )
        logger.info("Saved to '{}'", _OUTPUT_PATH)
        return _OUTPUT_PATH


if __name__ == "__main__":
    raw = sorted(Path("data/raw/mzp").glob("*.geojson"))
    if raw:
        MZPTransformer(source_path=raw[-1]).run()
