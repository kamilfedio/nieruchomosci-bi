"""GUS BDL scraper — downloads demographic indicators from the BDL REST API.

Downloads 5 indicators at unit-level=6 (cities with county rights).
Each indicator is saved as a separate JSON file for resumability.
Handles pagination via links.next and HTTP 429 with exponential backoff.
"""

import json
import time
from pathlib import Path

from httpx import Client, HTTPStatusError, Timeout
from loguru import logger

from .base import BaseScraper

_BDL_BASE = "https://bdl.stat.gov.pl/api/v1/data/by-variable"

# GUS BDL variable IDs → internal indicator names
_INDICATORS: dict[int, str] = {
    72305: "population",
    64428: "avg_gross_salary",
    60270: "unemployment_rate",
    254524: "migration_balance",
    72308: "working_age_population",
}

_RETRY_DELAYS = [15, 30, 60, 120]  # seconds, for HTTP 429


class GUSBDLScraper(BaseScraper):
    """Downloads BDL demographic data per indicator and saves to data/raw/gus_bdl/."""

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

        with Client(
            timeout=Timeout(connect=15.0, read=60.0, write=5.0, pool=5.0),
            follow_redirects=True,
        ) as client:
            for var_id, name in _INDICATORS.items():
                logger.info("Fetching indicator: {} (var_id={})", name, var_id)
                results = self._fetch_indicator(client, var_id, headers)
                out_path = out_dir / f"{name}.json"
                out_path.write_text(
                    json.dumps(results, ensure_ascii=False), encoding="utf-8"
                )
                logger.info("  {} → {} units saved", name, len(results))

        return out_dir

    def _fetch_indicator(
        self, client: Client, var_id: int, headers: dict[str, str]
    ) -> list[dict]:
        url = f"{_BDL_BASE}/{var_id}"
        params: dict[str, object] = {
            "format": "json",
            "unit-level": 6,
            "page-size": 100,
        }
        all_results: list[dict] = []

        while True:
            data = self._get_with_retry(client, url, params, headers)
            all_results.extend(data.get("results") or [])

            next_url = (data.get("links") or {}).get("next")
            if not next_url:
                break
            url = next_url
            params = {}  # next URL already contains all parameters

        return all_results

    def _get_with_retry(
        self,
        client: Client,
        url: str,
        params: dict,
        headers: dict[str, str],
    ) -> dict:
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                logger.warning(
                    "HTTP 429 — waiting {}s before retry {}/{}",
                    delay,
                    attempt,
                    len(_RETRY_DELAYS),
                )
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
                raise
        raise RuntimeError(
            f"HTTP 429 persists after {len(_RETRY_DELAYS)} retries: {url}"
        )


if __name__ == "__main__":
    scraper = GUSBDLScraper()
    scraper.run()
