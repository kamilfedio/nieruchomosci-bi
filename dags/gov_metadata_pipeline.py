"""GOV metadata pipeline: scrape → stage → transform → load"""

from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task


@dag(
    dag_id="gov_metadata_pipeline",
    schedule="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gov", "metadata", "staging"],
)
def gov_metadata_pipeline():
    @task
    def scrape() -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.scrapers.gov_metadata_scraper import GovMetadaScraper

        path = GovMetadaScraper(
            "https://api.dane.gov.pl/1.4/datasets/resources/metadata.csv", "Developers"
        ).run()
        return str(path)

    @task
    def stage(raw_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.staging.gov_metadata_staging import GovMetadataStaging

        path = GovMetadataStaging(source_path=Path(raw_path)).run()
        return str(path)

    @task
    def transform(staging_path: str) -> str:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.transformers.gov_metadata_transformer import GovMetadataTransformer

        path = GovMetadataTransformer(source_path=Path(staging_path)).run()
        return str(path)

    @task
    def load(processed_path: str) -> int:
        from _inject_env import setup_task_env

        setup_task_env()
        from src.api.loaders.gov_metadata_loader import GovMetadataLoader

        return GovMetadataLoader(source_path=Path(processed_path)).run()

    load(transform(stage(scrape())))  # type: ignore[arg-type]


gov_metadata_pipeline()
