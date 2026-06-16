"""실제 저장 구현 — Postgres ON CONFLICT로 idempotency를 DB에 위임.

INSERT ... ON CONFLICT (content_hash) DO NOTHING RETURNING id:
행이 반환되면 신규(True), 비면 중복(False). 경합 상황에서도 안전하다.
"""

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Content


class SqlContentSink:
    """ContentSink 프로토콜의 Postgres 구현. commit은 호출부(잡)가 책임진다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_if_absent(
        self,
        *,
        source_id: int,
        title: str,
        body: str,
        url: str,
        published_at: datetime | None,
        content_hash: str,
    ) -> bool:
        stmt = (
            pg_insert(Content)
            .values(
                source_id=source_id,
                title=title,
                content=body,
                original_url=url,
                published_at=published_at,
                content_hash=content_hash,
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
            .returning(Content.id)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
