"""Batch download of gov_data developer files (pending queue from DB)."""

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from httpx import Client, Timeout
from loguru import logger
from sqlalchemy.engine import Engine
from src.api.config import Config
from src.api.db.connection import build_engine, get_session, init_db
from src.api.db.models import DeveloperFile
from src.api.db.repositories.developer_files import DeveloperFileRepository
from src.api.scrapers.gov_data_scraper import GovDataScraper


@dataclass(frozen=True, slots=True)
class GovDataScrapeItem:
    path: str
    download_url: str
    regon: str = ""
    developer_name: str = ""


@dataclass(frozen=True, slots=True)
class GovDataScrapeBatchStats:
    ready: int
    failed: int
    skipped: int


@dataclass(frozen=True, slots=True)
class _PendingRecord:
    download_url: str
    file_format: str
    status: str
    raw_path: str
    regon: str = field(default="")
    developer_name: str = field(default="")


@dataclass(frozen=True, slots=True)
class _DownloadOutcome:
    item: GovDataScrapeItem | None = None
    failed: bool = False
    skipped: bool = False


def _output_stem_from_url(download_url: str) -> str:
    """Stable unique filename stem — safe for parallel downloads."""
    digest = hashlib.sha256(download_url.encode()).hexdigest()[:16]
    return f"gov_{digest}"


class GovDataBatchScraper:
    """Fetch up to ``gov_data_batch_size`` pending files and download them."""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()

    def scrape_batch(self) -> list[GovDataScrapeItem]:
        engine = build_engine(self._config.database_url)
        init_db(engine)

        pending = self._fetch_pending(engine)
        if not pending:
            batch_size = self._config.gov_data_batch_size
            logger.info(
                "gov_data scrape batch: no pending files (batch_size={})",
                batch_size,
            )
            return []

        workers = self._config.gov_data_scrape_workers
        logger.info(
            "gov_data scrape batch: {} file(s) queued (batch_size={}, workers={})",
            len(pending),
            self._config.gov_data_batch_size,
            workers,
        )
        items, stats = self._download_pending(engine, pending)
        logger.info(
            "gov_data scrape batch done: {} ready, {} failed, {} skipped",
            stats.ready,
            stats.failed,
            stats.skipped,
        )
        return items

    def _fetch_pending(self, engine: Engine) -> list[_PendingRecord]:
        with get_session(engine) as session:
            rows: list[DeveloperFile] = DeveloperFileRepository(
                session
            ).get_pending_by_cities(
                self._config.cities,
                limit=self._config.gov_data_batch_size,
            )
            return [
                _PendingRecord(
                    download_url=r.download_url,
                    file_format=r.file_format or "",
                    status=r.status,
                    raw_path=r.raw_path or "",
                    regon=r.regon or "",
                    developer_name=r.developer_name or "",
                )
                for r in rows
            ]

    def _download_pending(
        self,
        engine: Engine,
        pending: list[_PendingRecord],
    ) -> tuple[list[GovDataScrapeItem], GovDataScrapeBatchStats]:
        results: list[GovDataScrapeItem] = []
        to_download: list[_PendingRecord] = []
        skipped = 0

        for record in pending:
            if not record.file_format:
                skipped += 1
                continue

            existing = self._reuse_existing_raw(record)
            if existing is not None:
                results.append(existing)
                continue

            to_download.append(record)

        failed = 0
        if to_download:
            workers = min(self._config.gov_data_scrape_workers, len(to_download))
            shared_client = Client(
                timeout=Timeout(connect=10.0, read=600.0, write=5.0, pool=5.0),
                follow_redirects=True,
                limits=__import__("httpx").Limits(
                    max_connections=workers,
                    max_keepalive_connections=workers,
                ),
            )
            with shared_client, ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(self._download_one, engine, record, shared_client)
                    for record in to_download
                ]
                for future in as_completed(futures):
                    outcome = future.result()
                    if outcome.skipped:
                        skipped += 1
                    elif outcome.failed:
                        failed += 1
                    elif outcome.item is not None:
                        results.append(outcome.item)

        stats = GovDataScrapeBatchStats(
            ready=len(results),
            failed=failed,
            skipped=skipped,
        )
        return results, stats

    def _download_one(
        self,
        engine: Engine,
        record: _PendingRecord,
        client: Client,
    ) -> _DownloadOutcome:
        try:
            path = GovDataScraper(
                resource_url=record.download_url,
                file_format=record.file_format,
                output_stem=_output_stem_from_url(record.download_url),
                client=client,
            ).run()
            with get_session(engine) as session:
                repo = DeveloperFileRepository(session)
                repo.update_status(record.download_url, "downloaded")
                repo.update_raw_path(record.download_url, str(path))
            return _DownloadOutcome(
                item=GovDataScrapeItem(
                    path=str(path),
                    download_url=record.download_url,
                    regon=record.regon,
                    developer_name=record.developer_name,
                )
            )
        except Exception:  # noqa: BLE001
            with get_session(engine) as session:
                DeveloperFileRepository(session).update_status(
                    record.download_url, "failed"
                )
            return _DownloadOutcome(failed=True)

    @staticmethod
    def _reuse_existing_raw(record: _PendingRecord) -> GovDataScrapeItem | None:
        if record.status != "downloaded" or not record.raw_path:
            return None
        raw_path = Path(record.raw_path)
        if not raw_path.exists():
            return None
        return GovDataScrapeItem(
            path=record.raw_path,
            download_url=record.download_url,
            regon=record.regon,
            developer_name=record.developer_name,
        )
