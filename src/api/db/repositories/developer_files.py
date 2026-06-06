"""Repository for developer_files table"""

from sqlalchemy.dialects.sqlite import insert

from ..models import DeveloperFile
from .base import BaseRepository


class DeveloperFileRepository(BaseRepository[DeveloperFile]):
    def insert_or_ignore(self, record: DeveloperFile) -> None:
        stmt = (
            insert(DeveloperFile)
            .values(
                download_url=record.download_url,
                developer_name=record.developer_name,
                title=record.title,
                regon=record.regon,
                file_format=record.file_format,
                institution_city=record.institution_city,
                data_date=record.data_date,
                dataset_url=record.dataset_url,
            )
            .on_conflict_do_nothing(index_elements=["download_url"])
        )
        self._session.execute(stmt)

    def insert_or_ignore_batch(self, records: list[DeveloperFile]) -> int:
        if not records:
            return 0
        rows = [
            {
                "download_url": r.download_url,
                "developer_name": r.developer_name,
                "title": r.title,
                "regon": r.regon,
                "file_format": r.file_format,
                "institution_city": r.institution_city,
                "data_date": r.data_date,
                "dataset_url": r.dataset_url,
            }
            for r in records
        ]
        stmt = (
            insert(DeveloperFile)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["download_url"])
        )
        result = self._session.execute(stmt)
        return result.rowcount

    def get_pending_by_cities(
        self, cities: list[str], limit: int | None = None
    ) -> list[DeveloperFile]:
        """Return files ready to process: pending (need download) or downloaded
        with a known raw_path (can skip download, go straight to staging)."""
        q = self._session.query(DeveloperFile).filter(
            DeveloperFile.institution_city.in_(cities),
            DeveloperFile.status.in_(["pending", "downloaded"]),
        )
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def update_raw_path(self, download_url: str, raw_path: str) -> None:
        self._session.query(DeveloperFile).filter(
            DeveloperFile.download_url == download_url
        ).update({"raw_path": raw_path})

    def get_urls_by_status(self, status: str) -> list[str]:
        rows = (
            self._session.query(DeveloperFile.download_url)
            .filter(DeveloperFile.status == status)
            .all()
        )
        return [r.download_url for r in rows]

    def get_by_cities(self, cities: list[str]) -> list[DeveloperFile]:
        return (
            self._session.query(DeveloperFile)
            .filter(DeveloperFile.institution_city.in_(cities))
            .all()
        )

    def update_status(self, download_url: str, status: str) -> None:
        self._session.query(DeveloperFile).filter(
            DeveloperFile.download_url == download_url
        ).update({"status": status})

    def update_status_batch(self, download_urls: list[str], status: str) -> None:
        self._session.query(DeveloperFile).filter(
            DeveloperFile.download_url.in_(download_urls)
        ).update({"status": status}, synchronize_session="fetch")
