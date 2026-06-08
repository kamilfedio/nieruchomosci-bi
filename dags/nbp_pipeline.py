"""NBP data pipeline: scrape → stage → transform → load"""

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
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.scrapers.nbp_scraper import NBPScraper

        path = NBPScraper(
            "https://static.nbp.pl/dane/rynek-nieruchomosci/ceny_mieszkan.xlsx"
        ).run()
        return str(path)

    @task
    def stage(raw_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.staging.nbp_staging import NBPStaging

        path = NBPStaging(source_path=Path(raw_path)).run()
        return str(path)

    @task
    def transform(staged_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.transformers.nbp_transformer import NBPTransformer

        path = NBPTransformer(source_path=Path(staged_path)).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.loaders.nbp_loader import NBPLoader

        return NBPLoader(source_path=Path(processed_path)).run()

    raw = scrape()
    staged = stage(raw)  # type: ignore[arg-type]
    processed = transform(staged)  # type: ignore[arg-type]
    load(processed)  # type: ignore[arg-type]


nbp_pipeline()
