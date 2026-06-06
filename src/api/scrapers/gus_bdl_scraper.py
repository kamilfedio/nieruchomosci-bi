"""GUS BDL scraper — downloads demographic indicators from the BDL REST API.

Uses /api/v1/data/by-unit/{id} endpoint with hardcoded BDL unit IDs.
One request per city × indicator — all years returned in a single call.
Total: 10 cities × 5 indicators = 50 requests (~1 min vs 10 min with pagination).

Note: Warsaw is at level 5 (special capital status), other cities at level 6.
BDL unit IDs were resolved via /api/v1/units and are stable across years.
"""

import json
import time
from pathlib import Path

from httpx import Client, HTTPStatusError, Timeout
from loguru import logger

from .base import BaseScraper

_BDL_BASE = "https://bdl.stat.gov.pl/api/v1"

_INDICATORS: dict[int, str] = {
    72305:  "population",
    64428:  "avg_gross_salary",
    60270:  "unemployment_rate",
    149164: "migration_balance",   # saldo migracji P1355; was 254524 (non-existent)
    72308:  "working_age_population",
}

# BDL internal unit IDs — all at level 5 (Powiat m. X).
# Level-5 IDs are required for avg_gross_salary and unemployment_rate;
# population and working_age_population work at both levels.
# Pattern: level-6 gmina ID with last 3 digits 011 → 000 (parent powiat).
# Warsaw: already level 5 (capital city status, no level-6 equivalent).
_CITY_UNIT_IDS: dict[str, str] = {
    "warszawa":  "071412865000",
    "kraków":    "011212161000",
    "wrocław":   "030210564000",
    "gdańsk":    "042214361000",
    "poznań":    "023016264000",
    "łódź":      "051011661000",
    "katowice":  "012414869000",
    "lublin":    "060611163000",
    "szczecin":  "023216562000",
    "bydgoszcz": "040410661000",
}

_RETRY_DELAYS = [15, 30, 60, 120]


class GUSBDLScraper(BaseScraper):
    @property
    def source_name(self) -> str:
        return "gus_bdl"

    def extract(self) -> Path:
        from src.api.config import Config

        config = Config()
        out_dir = self._raw_dir / self.source_name / self.batch_id
        out_dir.mkdir(parents=True, exist_ok=True)

        if not config.bdl_api_key:
            raise RuntimeError(
                "BDL_API_KEY is required — register at https://api.stat.gov.pl/Home/BdlApi"
                " and set BDL_API_KEY in .env"
            )
        headers: dict[str, str] = {"X-ClientId": config.bdl_api_key}

        # Only fetch cities that are in config
        target = {c.lower() for c in config.cities}
        cities = {city: uid for city, uid in _CITY_UNIT_IDS.items() if city in target}
        missing = target - set(cities)
        if missing:
            logger.warning("No BDL unit ID for cities: {} — skipped", sorted(missing))

        logger.info("Fetching {} cities × {} indicators = {} requests",
                    len(cities), len(_INDICATORS), len(cities) * len(_INDICATORS))

        with Client(
            timeout=Timeout(connect=15.0, read=60.0, write=5.0, pool=5.0),
            follow_redirects=True,
        ) as client:
            for var_id, name in _INDICATORS.items():
                logger.info("Indicator: {} (var_id={})", name, var_id)
                results: list[dict] = []

                for i, (city, unit_id) in enumerate(cities.items()):
                    logger.debug("  [{}/{}] {} (unit_id={})", i + 1, len(cities), city, unit_id)
                    data = self._fetch_unit(client, unit_id, var_id, headers)
                    values = []
                    for rec in data.get("results") or []:
                        values = rec.get("values") or []
                        break
                    results.append({
                        "id": unit_id,
                        "name": data.get("unitName") or city,
                        "values": [
                            {"year": int(v["year"]), "val": v.get("val")}
                            for v in values
                        ],
                    })
                    logger.debug("    → {} year entries", len(values))

                out_path = out_dir / f"{name}.json"
                out_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
                logger.info("  Saved {} → {} cities, {} total year entries",
                            name, len(results),
                            sum(len(r["values"]) for r in results))

        return out_dir

    def _fetch_unit(
        self,
        client: Client,
        unit_id: str,
        var_id: int,
        headers: dict[str, str],
    ) -> dict:
        url = f"{_BDL_BASE}/data/by-unit/{unit_id}"
        params = {"format": "json", "var-id": var_id}
        return self._get_with_retry(client, url, params, headers)

    def _get_with_retry(
        self,
        client: Client,
        url: str,
        params: dict,
        headers: dict[str, str],
    ) -> dict:
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                logger.warning("HTTP 429 — waiting {}s (retry {}/{})",
                               delay, attempt, len(_RETRY_DELAYS))
                time.sleep(delay)
            try:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code == 429:
                    continue
                resp.raise_for_status()
                return resp.json()
            except HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    continue
                logger.error("HTTP {} for {}: {}",
                             exc.response.status_code, url, exc.response.text[:300])
                raise
        raise RuntimeError(
            f"HTTP 429 persists after {len(_RETRY_DELAYS)} retries: {url}"
        )


if __name__ == "__main__":
    GUSBDLScraper().run()
