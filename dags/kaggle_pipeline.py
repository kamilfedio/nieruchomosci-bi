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
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.config import Config
        from src.api.scrapers.kaggle_scraper import KaggleScraper

        path = KaggleScraper(Config().kaggle_dataset_slug).run()
        return str(path)

    @task
    def stage(raw_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.staging.kaggle_staging import KaggleStaging

        path = KaggleStaging(source_path=Path(raw_path)).run()
        return str(path)

    @task
    def transform(staged_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.transformers.kaggle_transformer import KaggleTransformer

        path = KaggleTransformer(source_path=Path(staged_path)).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.loaders.kaggle_loader import KaggleLoader

        return KaggleLoader(source_path=Path(processed_path)).run()

    @task
    def validate(processed_path: str) -> dict:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.config import Config
        from src.api.quality.checker import DQChecker

        return DQChecker.source_summary("kaggle", Config().database_url)

    raw = scrape()
    staged = stage(raw)  # type: ignore[arg-type]
    processed = transform(staged)  # type: ignore[arg-type]
    load(processed)  # type: ignore[arg-type]
    validate(processed)  # type: ignore[arg-type]


kaggle_pipeline()
