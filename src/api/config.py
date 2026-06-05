"""Config for application"""

from pathlib import Path

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
    db_path: Path = Path("data/db/nieruchomosci.db")
    gemini_api_key: str = ""
    scrape_limit: int | None = None  # set to e.g. 100 for test runs
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
