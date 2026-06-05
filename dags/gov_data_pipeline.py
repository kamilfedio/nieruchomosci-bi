"""GOV data pipeline: scrape → stage → transform → load"""

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
    def scrape() -> list[dict[str, str]]:
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
            rows = DeveloperFileRepository(session).get_pending_by_cities(
                config.cities, limit=config.scrape_limit
            )
            pending = [
                {"download_url": r.download_url, "file_format": r.file_format}
                for r in rows
            ]

        results: list[dict[str, str]] = []
        for record in pending:
            if not record["file_format"]:
                continue
            try:
                path = GovDataScraper(
                    resource_url=record["download_url"],
                    file_format=record["file_format"],
                ).run()
                results.append(
                    {"path": str(path), "download_url": record["download_url"]}
                )
                with get_session(engine) as session:
                    DeveloperFileRepository(session).update_status(
                        record["download_url"], "downloaded"
                    )
            except Exception:  # noqa: BLE001
                with get_session(engine) as session:
                    DeveloperFileRepository(session).update_status(
                        record["download_url"], "failed"
                    )

        return results

    @task
    def stage(item: dict[str, str]) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.staging.gov_data_staging import GovDataStaging

        return str(
            GovDataStaging(
                source_path=Path(item["path"]),
                download_url=item["download_url"],
            ).run()
        )

    @task
    def transform(staged_paths: list[str]) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.transformers.gov_data_transformer import GovDataTransformer

        # staged_paths contains all individual parquet paths from expand();
        # transformer reads the whole staging directory at once for LAG
        staging_dir = Path(staged_paths[0]).parent
        path = GovDataTransformer(source_path=staging_dir).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.loaders.gov_data_loader import GovDataLoader

        return GovDataLoader(source_path=Path(processed_path)).run()

    staged = stage.expand(item=scrape())
    processed = transform(staged)
    load(processed)  # type: ignore[arg-type]


gov_data_pipeline()
