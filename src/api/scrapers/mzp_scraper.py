"""MZP scraper — downloads flood hazard zones from Wody Polskie WFS."""

import json
from pathlib import Path

from httpx import Client, Timeout
from loguru import logger

from .base import BaseScraper

_WFS_URL = "https://wody.isok.gov.pl/wss/INSPIRE/INSPIRE_NZ_HY_MZPMRP_WFS"

# BBOX per city: (min_lon, min_lat, max_lon, max_lat) — WGS84
_CITY_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "Warszawa": (20.85, 52.10, 21.27, 52.37),
    "Kraków": (19.79, 49.97, 20.17, 50.13),
    "Wrocław": (16.80, 51.03, 17.17, 51.20),
    "Gdańsk": (18.47, 54.27, 18.77, 54.45),
    "Poznań": (16.76, 52.31, 17.07, 52.51),
    "Łódź": (19.34, 51.68, 19.60, 51.85),
    "Katowice": (18.88, 50.19, 19.09, 50.32),
    "Lublin": (22.43, 51.16, 22.66, 51.32),
    "Szczecin": (14.42, 53.34, 14.70, 53.52),
    "Bydgoszcz": (17.93, 53.07, 18.17, 53.18),
}


def _wfs_params(bbox: tuple[float, float, float, float]) -> dict[str, str]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": "NZ.HazardArea",
        "outputFormat": "application/json",
        "SRSNAME": "EPSG:4326",
        "BBOX": (f"{min_lat},{min_lon},{max_lat},{max_lon},urn:ogc:def:crs:EPSG::4326"),
    }


class MZPScraper(BaseScraper):
    """Downloads NZ.HazardArea features per city BBOX and saves as GeoJSON."""

    def __init__(self, verify_ssl: bool = True, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._client = Client(
            timeout=Timeout(connect=15.0, read=120.0, write=5.0, pool=5.0),
            verify=verify_ssl,
            follow_redirects=True,
        )

    @property
    def source_name(self) -> str:
        return "mzp"

    def extract(self) -> Path:
        out_path = self._raw_dir / self.source_name / f"{self.batch_id}.geojson"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        all_features: list[dict] = []
        for city, bbox in _CITY_BBOXES.items():
            logger.info("Fetching MZP for {}", city)
            try:
                resp = self._client.get(_WFS_URL, params=_wfs_params(bbox))
                resp.raise_for_status()
                data = resp.json()
                features = data.get("features") or []
                logger.info("  {} → {} features", city, len(features))
                all_features.extend(features)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch MZP for {}: {}", city, exc)

        geojson = {"type": "FeatureCollection", "features": all_features}
        out_path.write_text(json.dumps(geojson, ensure_ascii=False))
        logger.info("Saved {} features to '{}'", len(all_features), out_path)
        return out_path


if __name__ == "__main__":
    scraper = MZPScraper(verify_ssl=False)
    scraper.run()
