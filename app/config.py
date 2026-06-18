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

    # LLM — 공급자는 측정 후 결정(DESIGN §11), MVP 기본은 가짜 provider
    llm_provider: str = "fake"  # "fake" | "anthropic" | "ollama"
    anthropic_model: str = "claude-haiku-4-5"  # 저비용 모델로 시작 (절대규칙 3)
    # Ollama(로컬, 무료). 컨테이너에서는 host.docker.internal로 host의 Ollama 접근
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "exaone3.5:2.4b"  # 한국어 특화 (LG EXAONE 3.5)
    chars_per_min: int = 500  # 읽기 시간 계산용 분당 글자수 (절대규칙 3)
    # ANTHROPIC_API_KEY는 SDK가 env에서 직접 읽음 — Settings에 두지 않음(로깅 유출 방지)

    # 이메일 / 다이제스트
    email_provider: str = "fake"  # 실 SES는 추후 (DESIGN §8 샌드박스 게이트)
    seed_user_email: str = "siha@ssrinc.co.kr"  # 0단계 "내 메일" 수신자
    digest_top_n: int = 5  # 점수 상위 N건만 다이제스트에 담음 (DESIGN §5, score>0)


@lru_cache
def get_settings() -> Settings:
    """프로세스당 한 번만 로드 (app·worker 공용)."""
    return Settings()
