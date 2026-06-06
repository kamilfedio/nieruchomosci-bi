"""Kaggle data pipeline: scrape → stage → transform → load"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="kaggle_pipeline",
    schedule="@monthly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kaggle", "staging"],
)
def kaggle_pipeline():
    @task
    def scrape() -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.scrapers.kaggle_scraper import KaggleScraper

        path = KaggleScraper("krzysztofjamroz/apartment-prices-in-poland").run()
        return str(path)

    @task
    def stage(raw_path: str) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.staging.kaggle_staging import KaggleStaging

        path = KaggleStaging(source_path=Path(raw_path)).run()
        return str(path)

    @task
    def transform(staged_path: str) -> str:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.transformers.kaggle_transformer import KaggleTransformer

        path = KaggleTransformer(source_path=Path(staged_path)).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        import sys

        sys.path.insert(0, "/opt/airflow")
        from src.api.loaders.kaggle_loader import KaggleLoader

        return KaggleLoader(source_path=Path(processed_path)).run()

    raw = scrape()
    staged = stage(raw)  # type: ignore[arg-type]
    processed = transform(staged)  # type: ignore[arg-type]
    load(processed)  # type: ignore[arg-type]


kaggle_pipeline()
