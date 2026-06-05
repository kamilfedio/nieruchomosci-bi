"""GOV data pipeline: scrape (from DB) → stage"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="gov_data_pipeline",
    schedule="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gov", "data", "staging"],
)
def gov_data_pipeline():
    @task
    def scrape() -> list[str]:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.config import Config
        from src.api.db.connection import build_engine, get_session, init_db
        from src.api.db.repositories.developer_files import DeveloperFileRepository
        from src.api.scrapers.gov_data_scraper import GovDataScraper

        config = Config()
        engine = build_engine(config.db_path)
        init_db(engine)

        with get_session(engine) as session:
            repo = DeveloperFileRepository(session)
            pending = repo.get_pending_by_cities(config.cities)

        raw_paths: list[str] = []
        for record in pending:
            if not record.file_format:
                continue
            try:
                path = GovDataScraper(
                    resource_url=record.download_url,
                    file_format=record.file_format,
                ).run()
                raw_paths.append(str(path))
                with get_session(engine) as session:
                    DeveloperFileRepository(session).update_status(
                        record.download_url, "downloaded"
                    )
            except Exception:  # noqa: BLE001
                with get_session(engine) as session:
                    DeveloperFileRepository(session).update_status(
                        record.download_url, "failed"
                    )

        return raw_paths

    @task
    def stage(raw_paths: list[str]) -> list[str]:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.staging.gov_data_staging import GovDataStaging

        staged_paths: list[str] = []
        for raw_path in raw_paths:
            path = GovDataStaging(source_path=Path(raw_path)).run()
            staged_paths.append(str(path))

        return staged_paths

    stage(scrape())  # type: ignore


gov_data_pipeline()
