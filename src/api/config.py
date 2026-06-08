"""Config for application"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """Base settings class with common configuration for all services"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


class Config(BaseConfig):
    database_url: str = Field(
        default="postgresql+psycopg2://airflow:airflow@localhost:5432/nieruchomosci",
        validation_alias=AliasChoices("DATABASE_URL"),
    )
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY"),
        description=(
            "Google Gemini API key for column mapping. "
            "Set via GEMINI_API_KEY in .env or Airflow Variable."
        ),
    )
    bdl_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("BDL_API_KEY"),
        description=(
            "GUS BDL REST API key. Set via BDL_API_KEY in .env or Airflow Variable."
        ),
    )
    gov_data_batch_size: int | None = Field(
        default=500,
        validation_alias=AliasChoices("GOV_DATA_BATCH_SIZE", "SCRAPE_LIMIT"),
        description=(
            "Max developer files processed per gov_data_pipeline run "
            "(scrape → stage → transform → load). None = no limit."
        ),
    )
    gov_data_scrape_workers: int = Field(
        default=12,
        validation_alias=AliasChoices("GOV_DATA_SCRAPE_WORKERS"),
        description="Parallel HTTP download workers for gov_data scrape batch.",
    )
    google_maps_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_MAPS_API_KEY"),
        description=(
            "Google Maps Geocoding API key. When empty, address geocoding is "
            "skipped and lat/lon stays NULL for developer units."
        ),
    )
    geocode_workers: int = Field(
        default=8,
        validation_alias=AliasChoices("GEOCODE_WORKERS"),
        description="Parallel workers for Google Maps API geocoding calls.",
    )
    gemini_timeout_ms: int = Field(
        default=60_000,
        validation_alias=AliasChoices("GEMINI_TIMEOUT_MS"),
        description="Gemini API timeout for column mapping (milliseconds).",
    )
    kaggle_dataset_slug: str = Field(
        default="krzysztofjamroz/apartment-prices-in-poland",
        validation_alias=AliasChoices("KAGGLE_DATASET_SLUG"),
        description="Kaggle dataset identifier used by all Kaggle pipeline DAGs.",
    )
    cities: list[str] = [
        "Warszawa",
        "Kraków",
        "Wrocław",
        "Gdańsk",
        "Poznań",
        "Łódź",
        "Katowice",
        "Lublin",
        "Szczecin",
        "Bydgoszcz",
    ]
