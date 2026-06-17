"""다이제스트 선정·저장·발송 상태 — idempotency를 DB로 보장 (절대규칙 2).

- select_undigested: 요약이 있고 아직 어떤 다이제스트에도 안 담긴 콘텐츠 (재발송 방지)
- get_by_date: 그날 다이제스트 존재 여부 ((user_id, digest_date) UNIQUE)
- mark_sent: pending → sent 전이. 이미 sent면 다시 안 보낸다
"""

from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Content, Digest, DigestItem, Summary, UserInterest
from app.digest.service import DigestItemView
from app.scoring.service import Candidate


class DigestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_interest_keywords(self, *, user_id: int) -> set[str]:
        rows = await self._session.scalars(
            select(UserInterest.keyword).where(UserInterest.user_id == user_id)
        )
        return set(rows)

    async def select_scoring_candidates(self) -> list[Candidate]:
        """요약 완료 + 아직 어떤 다이제스트에도 안 담긴 콘텐츠 (재발송 방지)."""
        already = select(DigestItem.content_id)
        stmt = (
            select(Content.id, Summary.keywords, Content.published_at)
            .join(Summary, Summary.content_id == Content.id)
            .where(Content.id.not_in(already))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            Candidate(content_id=cid, keywords=kw or [], published_at=pa) for cid, kw, pa in rows
        ]

    async def get_by_date(self, *, user_id: int, digest_date: date) -> Digest | None:
        return await self._session.scalar(
            select(Digest).where(Digest.user_id == user_id, Digest.digest_date == digest_date)
        )

    async def create(self, *, user_id: int, digest_date: date) -> Digest:
        digest = Digest(user_id=user_id, digest_date=digest_date, status="pending")
        self._session.add(digest)
        await self._session.flush()  # digest.id 확보
        return digest

    async def add_items(self, *, digest_id: int, selections: list[tuple[int, float]]) -> None:
        """selections: (content_id, score). 0단계엔 점수 함수가 없어 score=0.0 placeholder."""
        for content_id, score in selections:
            self._session.add(DigestItem(digest_id=digest_id, content_id=content_id, score=score))

    async def load_item_views(self, *, digest_id: int) -> list[DigestItemView]:
        stmt = (
            select(
                Content.title,
                Summary.summary,
                Summary.reading_time,
                Content.original_url,
            )
            .join(DigestItem, DigestItem.content_id == Content.id)
            .join(Summary, Summary.content_id == Content.id)
            .where(DigestItem.digest_id == digest_id)
            .order_by(DigestItem.id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            DigestItemView(title=t, summary=s, reading_time=rt or 0, url=u) for t, s, rt, u in rows
        ]

    async def mark_sent(self, *, digest_id: int, sent_at: datetime) -> None:
        await self._session.execute(
            update(Digest).where(Digest.id == digest_id).values(status="sent", sent_at=sent_at)
        )
