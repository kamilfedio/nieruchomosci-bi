"""NBP data pipeline: scrape → stage"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="nbp_pipeline",
    schedule="0 0 1 */3 *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["nbp", "staging"],
)
def nbp_pipeline():
    @task
    def scrape() -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.scrapers.nbp_scraper import NBPScraper

        path = NBPScraper(
            "https://static.nbp.pl/dane/rynek-nieruchomosci/ceny_mieszkan.xlsx"
        ).run()
        return str(path)

    @task
    def stage(raw_path: str) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.staging.nbp_staging import NBPStaging

        path = NBPStaging(source_path=Path(raw_path)).run()
        return str(path)

    stage(scrape())  # type: ignore


nbp_pipeline()
