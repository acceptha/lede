"""Arq 워커 진입점.

API와 동일하게 async로 통일 (DESIGN §2). 잡:
- ping: Redis 왕복 확인용 최소 잡
- collect_feeds: 등록된 RSS 소스를 순회 수집 → contents 저장 (content_hash 중복 차단)
"""

import httpx
from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy import select

from app.collect.repository import SqlContentSink
from app.collect.rss import DEFAULT_TIMEOUT, fetch_feed
from app.collect.service import collect_source
from app.config import get_settings
from app.db.base import SessionFactory
from app.db.models import Source
from app.retry import deterministic_backoff

settings = get_settings()

# RSS 수집 잡 최대 시도 횟수. 초과 시 실패 소스는 결과 요약에만 남기고 종료.
MAX_TRIES = 4


async def ping(ctx: dict) -> str:
    """워커-Redis 왕복 확인용 최소 잡."""
    return "pong"


async def collect_feeds(ctx: dict) -> dict:
    """등록된 모든 RSS 소스를 수집한다.

    실패 격리(절대규칙 5): 한 소스의 네트워크 실패가 다른 소스 수집을 막지 않는다.
    재시도(DESIGN §5): 실패가 남으면 결정론적 백오프(jitter 없음)로 잡을 재시도.
    재실행은 content_hash 중복 차단 덕에 안전하다(절대규칙 2).
    """
    job_try: int = ctx.get("job_try", 1)
    client: httpx.AsyncClient = ctx["http_client"]
    summary = {"sources": 0, "new": 0, "duplicate": 0, "failed": 0}
    failures: list[str] = []

    async def fetch(url: str) -> bytes:
        return await fetch_feed(url, client)

    async with SessionFactory() as session:
        sources = (await session.execute(select(Source))).scalars().all()
        sink = SqlContentSink(session)
        for src in sources:
            try:
                result = await collect_source(
                    source_id=src.id,
                    feed_url=src.source_url,
                    fetch=fetch,
                    sink=sink,
                )
                summary["sources"] += 1
                summary["new"] += result.new
                summary["duplicate"] += result.duplicate
            except httpx.HTTPError as exc:
                failures.append(f"{src.source_url}: {exc!r}")
        # 성공분은 먼저 영속화 → 재시도해도 중복으로 무시됨(idempotent)
        await session.commit()

    summary["failed"] = len(failures)
    if failures and job_try < MAX_TRIES:
        # RSS는 결정론적 지수 백오프 (full jitter는 LLM 경로 전용)
        raise Retry(defer=deterministic_backoff(job_try))
    return summary


async def startup(ctx: dict) -> None:
    ctx["settings"] = settings
    ctx["http_client"] = httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "lede/0.0 (+https://github.com/acceptha/lede)"},
    )


async def shutdown(ctx: dict) -> None:
    client: httpx.AsyncClient | None = ctx.get("http_client")
    if client is not None:
        await client.aclose()


class WorkerSettings:
    """`arq app.worker.WorkerSettings` 로 기동."""

    functions = [ping, collect_feeds]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_TRIES
    redis_settings = RedisSettings.from_dsn(str(settings.redis_url))
