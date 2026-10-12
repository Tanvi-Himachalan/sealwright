"""Central configuration. Values come from environment variables / a .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'storage' / 'sealwright.db'}"
    storage_dir: Path = BASE_DIR / "storage" / "certificates"
    secret_key: str = "change-me-please"
    public_base_url: str = "http://127.0.0.1:8000"
    worker_threads: int = 2
    max_recipients: int = 5000
    generation_delay_ms: int = 0
    process_inline: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
