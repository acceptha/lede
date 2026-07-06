"""임베딩 저장/검색 — pgvector (V3 벡터 방향).

set_embedding: summaries.embedding 채움. find_similar: 코사인 거리(`<=>`) 최근접 질의.
select_needs_embedding: embedding NULL인 요약 → embed_pending 대상(재실행 시 자가 치유).
"""

from sqlalchemy import select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Summary


class EmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def select_needs_embedding(self, *, limit: int = 0) -> list[Row]:
        stmt = select(Summary.id, Summary.summary).where(Summary.embedding.is_(None))
        if limit > 0:
            stmt = stmt.limit(limit)
        return list((await self._session.execute(stmt)).all())

    async def set_embedding(self, *, summary_id: int, vector: list[float]) -> None:
        await self._session.execute(
            update(Summary).where(Summary.id == summary_id).values(embedding=vector)
        )

    async def find_similar(
        self, *, embedding: list[float], k: int = 5, exclude_summary_id: int | None = None
    ) -> list[Row]:
        """embedding과 코사인 거리가 가까운 요약 상위 k건 (content_id, distance)."""
        stmt = select(
            Summary.content_id,
            Summary.embedding.cosine_distance(embedding).label("distance"),
        ).where(Summary.embedding.is_not(None))
        if exclude_summary_id is not None:
            stmt = stmt.where(Summary.id != exclude_summary_id)
        stmt = stmt.order_by("distance").limit(k)
        return list((await self._session.execute(stmt)).all())
