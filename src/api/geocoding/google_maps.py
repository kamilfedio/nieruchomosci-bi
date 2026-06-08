"""Google Maps Geocoding service with three-level cache.

Cache hierarchy (fastest first):
  1. In-process dict   — zero-cost within the same loader run
  2. PostgreSQL table  — persists across DAG runs; batch-queried with IN (...)
  3. Google Maps API   — called only for addresses absent from both caches;
                         concurrent via ThreadPoolExecutor

Address deduplication happens before any cache lookup — each unique
(city, street) pair is resolved at most once per load() call.
"""

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"

Coords = tuple[float, float]  # (lat, lon)
Address = tuple[str, str]     # (city, street)


def _normalize(city: str, street: str) -> str:
    """Canonical address string used as cache key input."""
    return f"{street.strip()}, {city.strip()}, polska".lower()


def _cache_key(normalized_address: str) -> str:
    return hashlib.md5(normalized_address.encode()).hexdigest()  # noqa: S324


class GoogleMapsGeocoder:
    """Geocode (city, street) pairs with three-level cache."""

    def __init__(
        self,
        api_key: str,
        engine: Engine,
        max_workers: int = 8,
    ) -> None:
        self._api_key = api_key
        self._engine = engine
        self._max_workers = max_workers
        self._process_cache: dict[str, Coords | None] = {}
        self._lock = threading.Lock()
        self._http = httpx.Client(timeout=10.0, follow_redirects=True)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GoogleMapsGeocoder":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def geocode_batch(
        self, addresses: list[Address]
    ) -> dict[Address, Coords | None]:
        """Geocode a list of (city, street) pairs.

        Returns {(city, street): (lat, lon) | None} for every input address.
        None means the address could not be geocoded (API miss or failure).
        """
        if not addresses:
            return {}

        unique: list[Address] = list({(c, s) for c, s in addresses if c and s})
        if not unique:
            return {}

        norm_map: dict[Address, str] = {cs: _normalize(*cs) for cs in unique}
        key_map: dict[Address, str] = {cs: _cache_key(n) for cs, n in norm_map.items()}

        result: dict[Address, Coords | None] = {}
        to_db: list[Address] = []

        # ── Level 1: process cache ────────────────────────────────────────────
        with self._lock:
            for cs in unique:
                k = key_map[cs]
                if k in self._process_cache:
                    result[cs] = self._process_cache[k]
                else:
                    to_db.append(cs)

        # ── Level 2: DB cache (batch IN query) ────────────────────────────────
        to_api: list[Address] = []
        if to_db:
            db_key_to_cs: dict[str, Address] = {key_map[cs]: cs for cs in to_db}
            db_hits = self._db_get(list(db_key_to_cs.keys()))
            for k, coords in db_hits.items():
                cs = db_key_to_cs[k]
                result[cs] = coords
                with self._lock:
                    self._process_cache[k] = coords
            to_api = [db_key_to_cs[k] for k in db_key_to_cs if k not in db_hits]

        # ── Level 3: Google Maps API (concurrent) ────────────────────────────
        if to_api:
            api_results = self._api_batch(to_api)
            for cs, coords in api_results.items():
                result[cs] = coords
                k = key_map[cs]
                with self._lock:
                    self._process_cache[k] = coords
            self._db_set(api_results, norm_map, key_map)

        logger.info(
            "Geocoding: {} unique addresses — {} process-cache, {} DB-cache, {} API",
            len(unique),
            len(unique) - len(to_db),
            len(to_db) - len(to_api),
            len(to_api),
        )
        return result

    # ── DB cache ─────────────────────────────────────────────────────────────

    def _db_get(self, keys: list[str]) -> dict[str, Coords | None]:
        if not keys:
            return {}
        placeholders = ", ".join(f":k{i}" for i in range(len(keys)))
        sql = text(
            f"SELECT cache_key, latitude, longitude "  # noqa: S608
            f"FROM geocoding_cache WHERE cache_key IN ({placeholders})"
        )
        params = {f"k{i}": k for i, k in enumerate(keys)}
        with self._engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: dict[str, Coords | None] = {}
        for key, lat, lon in rows:
            out[str(key)] = (float(lat), float(lon)) if lat is not None else None
        return out

    def _db_set(
        self,
        api_results: dict[Address, Coords | None],
        norm_map: dict[Address, str],
        key_map: dict[Address, str],
    ) -> None:
        if not api_results:
            return
        rows = [
            {
                "cache_key": key_map[cs],
                "address": norm_map[cs],
                "latitude": coords[0] if coords else None,
                "longitude": coords[1] if coords else None,
            }
            for cs, coords in api_results.items()
        ]
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO geocoding_cache
                        (cache_key, address, latitude, longitude)
                    VALUES (:cache_key, :address, :latitude, :longitude)
                    ON CONFLICT (cache_key) DO NOTHING
                """),
                rows,
            )
        logger.debug("Stored {} new geocoding results in DB cache", len(rows))

    # ── Google Maps API ───────────────────────────────────────────────────────

    def _api_batch(self, addresses: list[Address]) -> dict[Address, Coords | None]:
        workers = min(self._max_workers, len(addresses))
        results: dict[Address, Coords | None] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._api_one, city, street): (city, street)
                for city, street in addresses
            }
            for future in as_completed(futures):
                cs = futures[future]
                try:
                    results[cs] = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Geocoding API error for {}: {}", cs, exc)
                    results[cs] = None
        return results

    def _api_one(self, city: str, street: str) -> Coords | None:
        address = f"{street}, {city}, Polska"
        resp = self._http.get(
            _GEOCODING_URL,
            params={
                "address": address,
                "key": self._api_key,
                "language": "pl",
                "region": "pl",
                "components": "country:PL",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            logger.debug(
                "Geocoding non-OK status '{}' for: {}", data.get("status"), address
            )
            return None
        results = data.get("results")
        if not results:
            return None
        loc = results[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
