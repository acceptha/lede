"""환경변수 기반 설정. 시크릿 하드코딩 금지 — 모든 값은 env → Settings로 주입."""

from functools import lru_cache

from pydantic import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 앱 메타
    app_name: str = "lede"
    environment: str = "local"

    # 영속 / 캐시
    database_url: str = "postgresql+asyncpg://lede:lede@postgres:5432/lede"
    redis_url: RedisDsn = "redis://redis:6379/0"


@lru_cache
def get_settings() -> Settings:
    """프로세스당 한 번만 로드 (app·worker 공용)."""
    return Settings()
