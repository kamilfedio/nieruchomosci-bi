"""Kaggle transformer — normalization and enrichment of apartment listings."""

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger

from .base import BaseTransformer

_MARKET_TYPE_MAP = {
    "apartmentBuilding": "primary",
    "blockOfFlats": "secondary",
    "tenement": "secondary",
}

_MATERIAL_VALID = {"brick", "concrete", "wood", "other"}

_CONDITION_MAP = {
    "high": "high",
    "medium": "medium",
    "low": "low",
}

_BOOL_COLS = [
    "has_parking_space",
    "has_balcony",
    "has_elevator",
    "has_storage_room",
]

_INT_COLS = ["rooms", "floor", "floor_count", "build_year"]

_FLOOD_ZONES_PATH = Path("data/processed/mzp/flood_zones.geojson")

# Flood risk scenario priority (lower return period = worse = higher priority)
_SCENARIO_PRIORITY: dict[str, int] = {
    "Q10%": 0,
    "Q1%": 1,
    "Q0.2%": 2,
    "none": 3,
}
_SCENARIO_ID: dict[str, int] = {
    "none": 0,
    "Q10%": 1,
    "Q1%": 2,
    "Q0.2%": 3,
}


@dataclass
class _FloodZone:
    scenario: str
    shape: object  # shapely geometry


def _bool_expr(col: str) -> pl.Expr:
    lower = pl.col(col).cast(pl.String).str.to_lowercase().str.strip_chars()
    return (
        pl.when(lower == "yes")
        .then(True)
        .when(lower == "no")
        .then(False)
        .otherwise(None)
    )


def _load_flood_zones(path: Path) -> list[_FloodZone]:
    from shapely.geometry import shape

    raw = json.loads(path.read_text())
    zones: list[_FloodZone] = []
    for feat in raw.get("features") or []:
        geom_raw = feat.get("geometry")
        scenario = (feat.get("properties") or {}).get("scenario", "none")
        if geom_raw is None or scenario == "none":
            continue
        try:
            zones.append(_FloodZone(scenario=scenario, shape=shape(geom_raw)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping invalid flood zone geometry: {}", exc)
    return zones


class KaggleTransformer(BaseTransformer):
    @property
    def source_name(self) -> str:
        return "kaggle"

    def read(self) -> pl.LazyFrame:
        return pl.scan_parquet(self._source_path)

    def transform(self, df: pl.LazyFrame) -> pl.LazyFrame:
        df = self._cast(df)
        df = self._filter_valid(df)
        df = self._normalize(df)
        df = self._computed(df)
        df = self._enrich_flood_risk(df)
        return df

    def _cast(self, df: pl.LazyFrame) -> pl.LazyFrame:
        int_exprs = [pl.col(c).cast(pl.Int32, strict=False).alias(c) for c in _INT_COLS]
        return df.with_columns(
            pl.col("price").cast(pl.Float64, strict=False),
            pl.col("square_meters").cast(pl.Float64, strict=False),
            pl.col("latitude").cast(pl.Float64, strict=False),
            pl.col("longitude").cast(pl.Float64, strict=False),
            *int_exprs,
        )

    def _filter_valid(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.filter(
            pl.col("price").is_not_null()
            & (pl.col("price") > 0)
            & pl.col("square_meters").is_not_null()
            & (pl.col("square_meters") > 0)
            & pl.col("id").is_not_null()
        )

    def _normalize(self, df: pl.LazyFrame) -> pl.LazyFrame:
        city_lower = pl.col("city").str.to_lowercase().str.strip_chars()

        market_type_expr = pl.lit("unknown")
        for src, tgt in _MARKET_TYPE_MAP.items():
            market_type_expr = (
                pl.when(pl.col("type") == src)
                .then(pl.lit(tgt))
                .otherwise(market_type_expr)
            )

        material_lower = (
            pl.col("building_material").str.to_lowercase().str.strip_chars()
        )
        material_norm = (
            pl.when(material_lower.is_in(list(_MATERIAL_VALID)))
            .then(material_lower)
            .when(pl.col("building_material").is_null())
            .then(pl.lit("unknown"))
            .otherwise(pl.lit("other"))
        )

        condition_norm = pl.lit("unknown")
        for src, tgt in _CONDITION_MAP.items():
            condition_norm = (
                pl.when(pl.col("condition").str.to_lowercase() == src)
                .then(pl.lit(tgt))
                .otherwise(condition_norm)
            )

        # build_year: keep only 1900–2026
        build_year = (
            pl.when(
                pl.col("build_year").is_not_null()
                & (pl.col("build_year") >= 1900)
                & (pl.col("build_year") <= 2026)
            )
            .then(pl.col("build_year"))
            .otherwise(None)
        )

        # floor: reject negatives
        floor = (
            pl.when(pl.col("floor").is_not_null() & (pl.col("floor") >= 0))
            .then(pl.col("floor"))
            .otherwise(None)
        )

        # rooms: reject <= 0
        rooms = (
            pl.when(pl.col("rooms").is_not_null() & (pl.col("rooms") > 0))
            .then(pl.col("rooms"))
            .otherwise(None)
        )

        # floor_count: reject 0
        floor_count = (
            pl.when(pl.col("floor_count").is_not_null() & (pl.col("floor_count") > 0))
            .then(pl.col("floor_count"))
            .otherwise(None)
        )

        # snapshot_date from source_file stem: data/raw/kaggle_data/YYYYMMDD_HHMMSS.csv
        snapshot_date = (
            pl.col("source_file")
            .str.extract(r"(\d{8})_\d{6}", 1)
            .str.strptime(pl.Date, "%Y%m%d", strict=False)
        )

        bool_exprs = [_bool_expr(c).alias(c) for c in _BOOL_COLS]

        return df.with_columns(
            city_lower.alias("city_norm"),
            market_type_expr.alias("market_type"),
            material_norm.alias("building_material_norm"),
            condition_norm.alias("condition_norm"),
            build_year.alias("build_year"),
            floor.alias("floor"),
            rooms.alias("rooms"),
            floor_count.alias("floor_count"),
            snapshot_date.alias("snapshot_date"),
            *bool_exprs,
        )

    def _computed(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(
            (pl.col("price") / pl.col("square_meters")).alias("price_per_m2_pln"),
        )

    def _enrich_flood_risk(self, df: pl.LazyFrame) -> pl.LazyFrame:
        if not _FLOOD_ZONES_PATH.exists():
            logger.warning(
                "MZP flood zones not found at '{}' — fk_flood_risk will be null",
                _FLOOD_ZONES_PATH,
            )
            return df.with_columns(pl.lit(None, dtype=pl.Int32).alias("fk_flood_risk"))

        from shapely import STRtree
        from shapely.geometry import Point

        zones = _load_flood_zones(_FLOOD_ZONES_PATH)
        if not zones:
            return df.with_columns(pl.lit(0, dtype=pl.Int32).alias("fk_flood_risk"))

        tree = STRtree([z.shape for z in zones])  # type: ignore[arg-type]

        # Collect id + coords eagerly for point-in-polygon
        pts = df.select(["id", "latitude", "longitude"]).collect()

        fk_list: list[int] = []
        for row in pts.iter_rows(named=True):
            lat = row.get("latitude")
            lon = row.get("longitude")
            if lat is None or lon is None:
                fk_list.append(0)
                continue

            pt = Point(lon, lat)  # shapely uses (x=lon, y=lat)
            # Query candidates by bounding box, then filter by actual containment
            candidate_idxs = tree.query(pt, predicate="within")

            if len(candidate_idxs) == 0:
                fk_list.append(0)  # outside all zones → "none" (id=0)
                continue

            # Pick worst scenario (lowest returnPeriod = highest priority)
            best = min(
                candidate_idxs,
                key=lambda i: _SCENARIO_PRIORITY.get(zones[i].scenario, 99),
            )
            scenario = zones[best].scenario
            fk_list.append(_SCENARIO_ID.get(scenario, 0))

        risk_df = pts.select("id").with_columns(
            pl.Series("fk_flood_risk", fk_list, dtype=pl.Int32)
        )

        in_zone = sum(1 for v in fk_list if v > 0)
        logger.info(
            "Flood risk enrichment: {}/{} listings in a hazard zone",
            in_zone,
            len(fk_list),
        )

        return df.join(risk_df.lazy(), on="id", how="left")
