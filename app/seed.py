"""seed 소스 등록 — 본문 전문(full-text) RSS를 주는 소스만.

검증(2026-06, 후보 5곳):
- 어피티(uppity.co.kr/feed): RSS 2.0 + content:encoded 본문 전문 → 채택.
- 너겟(nugget.im/rss): RSS는 있으나 본문 전부 빈 description(imweb 헤드라인형) → 보류.
- 캐릿·순살·뉴닉: 표준 피드 경로 전부 404, 공개 RSS 없음 → 보류.
보류 사유·상세는 DESIGN §11 참조. 본문 보강은 크롤링이 필요해 스코프 밖(§3-6).
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
