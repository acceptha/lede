"""요약 저장/조회 — 캐싱(재요약 0회)과 idempotency를 DB에 위임 (절대규칙 2).

select_pending_contents: 아직 요약 없는 콘텐츠만 → 이미 요약된 글은 다시 안 부른다(캐싱).
add_if_absent: ON CONFLICT(content_id) DO NOTHING → 재실행해도 중복 요약 0건.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Content, Summary


class SummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def select_pending_contents(self) -> list[Content]:
        stmt = (
            select(Content)
            .outerjoin(Summary, Summary.content_id == Content.id)
            .where(Summary.id.is_(None))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def add_if_absent(
        self,
        *,
        content_id: int,
        summary: str,
        keywords: list[str],
        reading_time: int,
    ) -> bool:
        stmt = (
            pg_insert(Summary)
            .values(
                content_id=content_id,
                summary=summary,
                keywords=keywords,
                reading_time=reading_time,
            )
            .on_conflict_do_nothing(index_elements=["content_id"])
            .returning(Summary.id)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
