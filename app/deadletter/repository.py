"""dead-letter 저장/조회 (DESIGN §5 — N회 실패 기록하고 계속).

record: 대상당 1행 upsert(attempts += 1). parked_content_ids: attempts 임계 이상(park) 집합.
실패가 영속되어 "어떤 글이 왜 실패했는지"가 남고, 임계 초과 시 재시도에서 제외된다.
"""

from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeadLetter


class DeadLetterRepository(Protocol):
    async def record(self, *, job_type: str, content_id: int | None, error: str) -> None: ...
    async def list(self) -> list[DeadLetter]: ...


class SqlDeadLetterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, *, job_type: str, content_id: int | None, error: str) -> None:
        stmt = pg_insert(DeadLetter).values(
            job_type=job_type, content_id=content_id, error=error, attempts=1
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_deadletter_job_content",
            set_={
                "attempts": DeadLetter.attempts + 1,
                "error": error,
                "updated_at": func.now(),
            },
        )
        await self._session.execute(stmt)

    async def parked_content_ids(self, *, job_type: str, max_attempts: int) -> set[int]:
        rows = await self._session.scalars(
            select(DeadLetter.content_id).where(
                DeadLetter.job_type == job_type,
                DeadLetter.attempts >= max_attempts,
                DeadLetter.content_id.is_not(None),
            )
        )
        return set(rows)

    async def list(self) -> list[DeadLetter]:
        result = await self._session.execute(
            select(DeadLetter).order_by(DeadLetter.updated_at.desc())
        )
        return list(result.scalars().all())
