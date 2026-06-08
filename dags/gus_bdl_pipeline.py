"""GUS BDL pipeline: scrape → transform → load (annual, runs mid-March).

GUS publishes updated demographic data in Q1 each year.
Set BDL_API_KEY in .env or as an Airflow Variable to avoid IP rate-limiting.
"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="gus_bdl_pipeline",
    schedule="0 6 15 3 *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gus", "bdl", "demographics"],
)
def gus_bdl_pipeline():
    @task
    def scrape() -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.scrapers.gus_bdl_scraper import GUSBDLScraper

        path = GUSBDLScraper().run()
        return str(path)

    @task
    def transform(raw_dir: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.transformers.gus_bdl_transformer import GUSBDLTransformer

        path = GUSBDLTransformer(source_path=Path(raw_dir)).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.loaders.gus_bdl_loader import GUSBDLLoader

        return GUSBDLLoader(source_path=Path(processed_path)).run()

    raw = scrape()
    processed = transform(raw)  # type: ignore[arg-type]
    load(processed)  # type: ignore[arg-type]


gus_bdl_pipeline()
