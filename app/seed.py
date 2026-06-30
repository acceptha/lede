"""seed 소스 등록 — 본문 전문(full-text) RSS를 주는 소스만.

채택 기준: 요약 파이프라인은 본문 전문이 있어야 의미가 있으므로, content:encoded 등
실제 본문이 담긴 피드만 등록한다. 보류/제외 사유는 DESIGN §11 소스 표 참조.
실행: `python -m app.seed` (DATABASE_URL은 env로 주입).
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import SessionFactory
from app.db.models import Source, User

SEED_SOURCES: list[dict[str, str]] = [
    {
        "source_name": "어피티",
        "source_url": "https://uppity.co.kr/feed",
        "source_type": "rss",
    },
    {
        "source_name": "토스 기술블로그",
        "source_url": "https://toss.tech/rss.xml",
        "source_type": "rss",
    },
    {
        "source_name": "네이버 D2",
        "source_url": "https://d2.naver.com/d2.atom",
        "source_type": "rss",
    },
]


async def ensure_seed_sources(session: AsyncSession) -> int:
    """소스를 source_url 기준으로 idempotent하게 보장. 새로 추가한 개수 반환."""
    added = 0
    for spec in SEED_SOURCES:
        existing = await session.scalar(
            select(Source).where(Source.source_url == spec["source_url"])
        )
        if existing is None:
            session.add(Source(**spec))
            added += 1
    await session.commit()
    return added


async def ensure_seed_user(session: AsyncSession) -> bool:
    """0단계 단일 유저(내 메일)를 email 기준으로 idempotent하게 보장. 새로 추가 시 True."""
    email = get_settings().seed_user_email
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return False
    session.add(User(email=email, nickname="seed"))
    await session.commit()
    return True


async def _main() -> None:
    async with SessionFactory() as session:
        added_sources = await ensure_seed_sources(session)
        added_user = await ensure_seed_user(session)
    print(f"seed ensured (sources added: {added_sources}, user added: {int(added_user)})")


if __name__ == "__main__":
    asyncio.run(_main())
