"""Kaggle backfill pipeline: download all missing historical sale snapshots.

Run manually to backfill snapshots not yet present in data/raw/kaggle_data/.
The monthly kaggle_pipeline continues to fetch only the newest file.
"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="kaggle_backfill_pipeline",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["kaggle", "backfill", "one-shot"],
)
def kaggle_backfill_pipeline():
    @task
    def scrape() -> list[str]:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.config import Config
        from src.api.scrapers.kaggle_scraper import KaggleScraper

        paths = KaggleScraper(Config().kaggle_dataset_slug).extract_missing()
        return [str(p) for p in paths]

    @task
    def stage(raw_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.staging.kaggle_staging import KaggleStaging

        return str(KaggleStaging(source_path=Path(raw_path)).run())

    @task
    def transform(staged_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.transformers.kaggle_transformer import KaggleTransformer

        return str(KaggleTransformer(source_path=Path(staged_path)).run())

    @task
    def load_all(processed_paths: list[str]) -> int:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.loaders.kaggle_loader import KaggleLoader

        total = 0
        for path in processed_paths:
            total += KaggleLoader(source_path=Path(path)).run()
        return total

    raw_paths = scrape()
    staged_paths = stage.expand(raw_path=raw_paths)  # type: ignore[arg-type]
    processed_paths = transform.expand(staged_path=staged_paths)  # type: ignore[arg-type]
    load_all(processed_paths)  # type: ignore[arg-type]


kaggle_backfill_pipeline()
