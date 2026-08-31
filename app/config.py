"""Application configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, overridable by environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAKMDM_", extra="ignore")

    database_url: str = "postgresql+psycopg://takmdm:takmdm@localhost:5432/takmdm"
    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
