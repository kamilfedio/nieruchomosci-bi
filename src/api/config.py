"""Config for application"""

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
    database_url: str = (
        "postgresql+psycopg2://airflow:airflow@localhost:5432/nieruchomosci"
    )
    gemini_api_key: str = "REDACTED_GEMINI_KEY"
    bdl_api_key: str = "REDACTED_BDL_KEY"
    scrape_limit: int | None = 1000  # set to e.g. 100 for test runs
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
