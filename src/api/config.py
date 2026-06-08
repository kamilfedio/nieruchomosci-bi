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
    analyst_database_url: str = Field(
        default="postgresql+psycopg2://analyst_ro:analyst@localhost:5432/nieruchomosci",
        validation_alias=AliasChoices("ANALYST_DATABASE_URL"),
        description=(
            "Read-only connection URL used by the Streamlit dashboard (analyst_ro role). "
            "Falls back to DATABASE_URL if not set."
        ),
    )
    admin_password_hash: str = Field(
        default="8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
        validation_alias=AliasChoices("ADMIN_PASSWORD_HASH"),
        description="SHA-256 hex digest of the admin dashboard password. Default: 'admin'.",
    )
    analyst_password_hash: str = Field(
        default="f44ceb062e35dfeea6ed7f8524d53bb0bff19f553e25cae7ef4850e4185ccbba",
        validation_alias=AliasChoices("ANALYST_PASSWORD_HASH"),
        description="SHA-256 hex digest of the analyst dashboard password. Default: 'analyst'.",
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
