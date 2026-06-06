"""Repository for flood_zones table — PostGIS geometry storage."""

import json
from pathlib import Path

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import FloodZone


class FloodZoneRepository:
    _SCENARIO_FK: dict[str, int] = {
        "Q10%": 1,
        "Q1%": 2,
        "Q0.2%": 3,
    }

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_from_geojson(self, geojson_path: str, batch_id: str) -> int:
        """Full refresh: truncate flood_zones and load from GeoJSON features."""
        raw = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
        features = raw.get("features") or []

        self._session.execute(text("TRUNCATE flood_zones RESTART IDENTITY"))

        inserted = 0
        skipped = 0
        for feat in features:
            props = feat.get("properties") or {}
            scenario = props.get("scenario", "unknown")
            if scenario in ("unknown", "none"):
                skipped += 1
                continue

            geom_raw = feat.get("geometry")
            if geom_raw is None:
                skipped += 1
                continue

            fk_id = self._SCENARIO_FK.get(scenario)
            if fk_id is None:
                skipped += 1
                continue

            try:
                self._session.execute(
                    text(
                        """
                        INSERT INTO flood_zones (
                            scenario, risk_class, depth_m,
                            fk_flood_risk, geom, batch_id
                        )
                        VALUES (
                            :scenario,
                            :risk_class,
                            :depth_m,
                            :fk_flood_risk,
                            ST_SimplifyPreserveTopology(
                                ST_MakeValid(
                                    ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)
                                ),
                                0.0001
                            ),
                            :batch_id
                        )
                        """
                    ),
                    {
                        "scenario": scenario,
                        "risk_class": props.get("risk_class"),
                        "depth_m": props.get("depth_m"),
                        "fk_flood_risk": fk_id,
                        "geojson": json.dumps(geom_raw),
                        "batch_id": batch_id,
                    },
                )
                inserted += 1
            except Exception as exc:
                logger.debug("Skipping invalid flood zone geometry: {}", exc)
                skipped += 1

        return inserted

    def count(self) -> int:
        return self._session.query(FloodZone).count()

    def lookup_flood_risk_ids(
        self, points: list[tuple[str, float, float]]
    ) -> dict[str, int]:
        """Return listing_id → fk_flood_risk for a batch of (id, lon, lat) points."""
        if not points:
            return {}

        values_parts: list[str] = []
        params: dict[str, object] = {}
        for i, (listing_id, lon, lat) in enumerate(points):
            values_parts.append(f"(:id_{i}, :lon_{i}, :lat_{i})")
            params[f"id_{i}"] = listing_id
            params[f"lon_{i}"] = lon
            params[f"lat_{i}"] = lat

        sql = (  # noqa: S608 — VALUES placeholders are bound, not user input
            f"""
            WITH listings(listing_id, lon, lat) AS (
                VALUES {", ".join(values_parts)}
            ),
            matched AS (
                SELECT DISTINCT ON (l.listing_id)
                    l.listing_id,
                    fz.fk_flood_risk
                FROM listings l
                LEFT JOIN flood_zones fz ON ST_Covers(
                    fz.geom,
                    ST_SetSRID(ST_MakePoint(l.lon, l.lat), 4326)
                )
                ORDER BY l.listing_id,
                    CASE fz.scenario
                        WHEN 'Q10%'  THEN 0
                        WHEN 'Q1%'   THEN 1
                        WHEN 'Q0.2%' THEN 2
                        ELSE 3
                    END
            )
            SELECT listing_id, fk_flood_risk FROM matched
        """
        )
        rows = self._session.execute(text(sql), params).all()
        result: dict[str, int] = {}
        for listing_id, fk in rows:
            result[str(listing_id)] = int(fk) if fk is not None else 0
        return result
