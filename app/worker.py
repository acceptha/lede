"""Arq 워커 진입점.

API와 동일하게 async로 통일 (DESIGN §2). 이 단계에서는 Redis 연결 확인용
ping 잡 하나만 둔다. RSS 수집/LLM 요약/메일 발송 잡은 다음 단계에서 추가.
"""

from arq.connections import RedisSettings

from app.config import get_settings

settings = get_settings()


async def ping(ctx: dict) -> str:
    """워커-Redis 왕복 확인용 최소 잡."""
    return "pong"


async def startup(ctx: dict) -> None:
    ctx["settings"] = settings


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    """`arq app.worker.WorkerSettings` 로 기동."""

    functions = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(str(settings.redis_url))
