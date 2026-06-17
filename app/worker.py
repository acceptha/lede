"""Arq 워커 진입점.

API와 동일하게 async로 통일 (DESIGN §2). 잡:
- ping: Redis 왕복 확인용 최소 잡
- collect_feeds: 등록된 RSS 소스를 순회 수집 → contents 저장 (content_hash 중복 차단)
- summarize_pending: 미요약 콘텐츠를 LLM provider로 요약 → summaries 캐싱 저장
- build_and_send_digest: 미수록 요약을 묶어 다이제스트 생성 → 이메일 발송 (중복 발송 차단)
"""

from datetime import UTC, date, datetime

import httpx
from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy import select

from app.collect.repository import SqlContentSink
from app.collect.rss import DEFAULT_TIMEOUT, fetch_feed
from app.collect.service import collect_source
from app.config import get_settings
from app.db.base import SessionFactory
from app.db.models import Source, User
from app.digest.repository import DigestRepository
from app.digest.service import render_email
from app.email.factory import get_email_sender
from app.email.sender import EmailError, EmailSender
from app.llm.factory import get_provider
from app.llm.provider import LLMError, LLMProvider, LLMRateLimitError
from app.retry import deterministic_backoff, full_jitter
from app.summarize.repository import SummaryRepository
from app.summarize.service import summarize_content

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


async def summarize_pending(ctx: dict) -> dict:
    """아직 요약 없는 콘텐츠를 요약해 저장한다.

    캐싱(절대규칙 2): 이미 요약된 글은 조회 단계에서 제외 → 재요약 0회.
    실패 격리(절대규칙 5): 한 콘텐츠 요약 실패는 dead-letter로 세고 다음으로 진행.
    rate limit(429): 공유 한도 → full jitter로 잡 전체를 백오프(재시도) (DESIGN §5).
    """
    job_try: int = ctx.get("job_try", 1)
    provider: LLMProvider = ctx["llm_provider"]
    summary = {"summarized": 0, "cached_skipped": 0, "failed": 0}

    async with SessionFactory() as session:
        repo = SummaryRepository(session)
        for content in await repo.select_pending_contents():
            try:
                data = await summarize_content(
                    title=content.title,
                    body=content.content,
                    provider=provider,
                    chars_per_min=settings.chars_per_min,
                )
            except LLMRateLimitError:
                await session.commit()  # 진행분 보존 후 잡 단위 백오프
                if job_try < MAX_TRIES:
                    raise Retry(defer=full_jitter(job_try)) from None
                raise
            except LLMError:
                summary["failed"] += 1  # dead-letter: 격리하고 계속
                continue

            inserted = await repo.add_if_absent(
                content_id=content.id,
                summary=data.summary,
                keywords=data.keywords,
                reading_time=data.reading_time,
            )
            summary["summarized" if inserted else "cached_skipped"] += 1
        await session.commit()

    return summary


async def build_and_send_digest(ctx: dict) -> dict:
    """미수록 요약을 묶어 다이제스트를 만들고 seed 유저에게 발송한다.

    선정: 그날 요약 전부(미수록), DIGEST_MAX_ITEMS>0이면 최신 N건으로 축소.
    스킵: 선정 0건이면 다이제스트를 만들지 않는다 (DESIGN §5 적용 정책).
    idempotency(절대규칙 2): (user_id, digest_date) UNIQUE + status pending→sent로
      재실행해도 재발송 0회. 발송 실패는 결정론적 백오프로 재시도 (SES, DESIGN §5).
    """
    job_try: int = ctx.get("job_try", 1)
    sender: EmailSender = ctx["email_sender"]
    digest_date = date.today()

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == settings.seed_user_email))
        if user is None:
            return {"status": "no_seed_user"}

        repo = DigestRepository(session)
        digest = await repo.get_by_date(user_id=user.id, digest_date=digest_date)
        if digest is None:
            items = await repo.select_undigested(limit=settings.digest_max_items)
            if not items:
                return {"status": "skipped_no_items"}
            digest = await repo.create(user_id=user.id, digest_date=digest_date)
            await repo.add_items(
                digest_id=digest.id,
                selections=[(content.id, 0.0) for content, _ in items],
            )

        if digest.status == "sent":
            await session.commit()
            return {"status": "already_sent", "digest_id": digest.id}

        views = await repo.load_item_views(digest_id=digest.id)
        subject, text, html = render_email(digest_date=digest_date, items=views)
        try:
            await sender.send(to=user.email, subject=subject, text=text, html=html)
        except EmailError:
            await session.commit()  # 빌드분(다이제스트·항목) 보존 후 재시도
            if job_try < MAX_TRIES:
                raise Retry(defer=deterministic_backoff(job_try)) from None
            raise

        await repo.mark_sent(digest_id=digest.id, sent_at=datetime.now(UTC))
        await session.commit()
        return {"status": "sent", "digest_id": digest.id, "items": len(views)}


async def startup(ctx: dict) -> None:
    ctx["settings"] = settings
    ctx["llm_provider"] = get_provider(settings)
    ctx["email_sender"] = get_email_sender(settings)
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

    functions = [ping, collect_feeds, summarize_pending, build_and_send_digest]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_TRIES
    redis_settings = RedisSettings.from_dsn(str(settings.redis_url))
