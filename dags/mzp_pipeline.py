"""MZP pipeline: extract → transform → load (manual trigger, one-shot).

MZP data (Mapy Zagrożenia Powodziowego) updates every ~6 years.
Run manually after Wody Polskie publish a new version.
"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="mzp_pipeline",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["mzp", "flood", "one-shot"],
)
def mzp_pipeline():
    @task
    def scrape() -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.scrapers.mzp_scraper import MZPScraper

        path = MZPScraper(verify_ssl=False).run()
        return str(path)

    @task
    def transform(raw_path: str) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.transformers.mzp_transformer import MZPTransformer

        path = MZPTransformer(source_path=Path(raw_path)).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.loaders.mzp_loader import MZPLoader

        return MZPLoader(source_path=Path(processed_path)).run()

    raw = scrape()
    processed = transform(raw)  # type: ignore[arg-type]
    load(processed)  # type: ignore[arg-type]


mzp_pipeline()
