"""Config for application"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """Base settings class with common configuration for all services"""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


class KaggleConfig(BaseConfig):
    """Kaggle config for downloading data"""

    api_token: str = Field(alias="KAGGLE_API_TOKEN")


class Config(BaseConfig):
    """Config"""

    kaggle: KaggleConfig = Field(default_factory=KaggleConfig)  # type: ignore
