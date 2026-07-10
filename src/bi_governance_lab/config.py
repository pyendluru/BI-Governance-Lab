from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_prefix="BI_GOVERNANCE_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "BI Governance Lab"
    database_url: str = "sqlite:///./bi_governance.db"
    debug: bool = False
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
