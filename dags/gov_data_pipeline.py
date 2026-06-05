"""GOV data pipeline: download → stage"""

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
    def scrape() -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.scrapers.gov_data_scraper import GovDataScraper

        path = GovDataScraper(
            "https://api.dane.gov.pl/resources/1082075,ceny-ofertowe-mieszkan-dewelopera-zd-wrocaw-szarskiego-spoka-z-ograniczona-odpowiedzialnoscia-inwestycja-lesnica-2026-01-16/file",
            "csv",
        ).run()
        return str(path)

    @task
    def stage(raw_path: str) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.staging.gov_data_staging import GovDataStaging

        path = GovDataStaging(source_path=Path(raw_path)).run()
        return str(path)

    stage(scrape())  # type: ignore


gov_data_pipeline()
