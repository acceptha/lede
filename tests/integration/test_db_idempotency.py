"""실 DB 통합 테스트 — content_hash 중복 차단 + 요약 캐싱 (절대규칙 2)."""

import pytest
from sqlalchemy import func, select

from app.collect.repository import SqlContentSink
from app.db.models import Content, Source
from app.summarize.repository import SummaryRepository

pytestmark = pytest.mark.integration


async def _seed_source(session) -> int:
    src = Source(source_name="t", source_url="http://t/feed", source_type="rss")
    session.add(src)
    await session.flush()
    return src.id


async def test_content_hash_blocks_duplicate(db_session):
    sid = await _seed_source(db_session)
    sink = SqlContentSink(db_session)
    fields = dict(source_id=sid, title="A", body="본문", url="http://a", published_at=None)
    assert await sink.add_if_absent(content_hash="h1", **fields) is True
    # 같은 해시 재삽입 → ON CONFLICT DO NOTHING → False(중복)
    assert await sink.add_if_absent(content_hash="h1", **fields) is False
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(Content))
    assert count == 1


async def test_summary_cached_and_excluded_from_pending(db_session):
    sid = await _seed_source(db_session)
    sink = SqlContentSink(db_session)
    await sink.add_if_absent(
        source_id=sid, title="A", body="b", url="http://a", published_at=None, content_hash="h"
    )
    await db_session.commit()
    cid = await db_session.scalar(select(Content.id))

    repo = SummaryRepository(db_session)
    assert (
        await repo.add_if_absent(content_id=cid, summary="s", keywords=["k"], reading_time=1)
        is True
    )
    # 같은 content_id 재요약 → ON CONFLICT → False (재요약 0회)
    assert (
        await repo.add_if_absent(content_id=cid, summary="s2", keywords=[], reading_time=2) is False
    )
    await db_session.commit()

    pending = await repo.select_pending_contents()
    assert cid not in [c.id for c in pending]  # 요약된 글은 pending 제외(캐싱)
