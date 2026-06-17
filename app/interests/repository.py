"""관심사 저장/조회 — MVP 단일 seed 유저 대상.

키워드는 router에서 정규화(규칙6)된 채로 들어온다. 등록은 (user_id, keyword) UNIQUE +
ON CONFLICT로 idempotent. Protocol로 추상화해 API 테스트는 FakeRepo를 주입한다.
"""

from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User, UserInterest


class InterestRepository(Protocol):
    async def add(self, keywords: list[str]) -> None: ...
    async def list(self) -> list[str]: ...
    async def remove(self, keyword: str) -> bool: ...


class SqlInterestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _user_id(self) -> int:
        email = get_settings().seed_user_email
        uid = await self._session.scalar(select(User.id).where(User.email == email))
        if uid is None:
            raise LookupError(f"seed user 없음: {email} (`python -m app.seed` 실행)")
        return uid

    async def add(self, keywords: list[str]) -> None:
        uid = await self._user_id()
        for kw in keywords:
            await self._session.execute(
                pg_insert(UserInterest)
                .values(user_id=uid, keyword=kw)
                .on_conflict_do_nothing(constraint="uq_user_keyword")
            )
        await self._session.commit()

    async def list(self) -> list[str]:
        uid = await self._user_id()
        rows = await self._session.scalars(
            select(UserInterest.keyword)
            .where(UserInterest.user_id == uid)
            .order_by(UserInterest.keyword)
        )
        return list(rows)

    async def remove(self, keyword: str) -> bool:
        uid = await self._user_id()
        result = await self._session.execute(
            delete(UserInterest).where(UserInterest.user_id == uid, UserInterest.keyword == keyword)
        )
        await self._session.commit()
        return result.rowcount > 0
