"""실 DB 통합 테스트 — pgvector 임베딩 저장 + 코사인 최근접 검색 (V3)."""

import pytest
from sqlalchemy import select

from app.db.models import Content, Source, Summary
from app.embedding.repository import EmbeddingRepository

pytestmark = pytest.mark.integration

DIM = 1024


def _vec(*head: float) -> list[float]:
    """앞부분만 지정하고 나머지는 0으로 채운 DIM 차원 벡터."""
    v = list(head) + [0.0] * (DIM - len(head))
    return v[:DIM]


async def _seed_summary(session, *, hash_: str) -> int:
    src = Source(source_name="t", source_url=f"http://t/{hash_}", source_type="rss")
    session.add(src)
    await session.flush()
    c = Content(
        source_id=src.id,
        title="제목",
        content="본문",
        original_url=f"http://a/{hash_}",
        published_at=None,
        content_hash=hash_,
    )
    session.add(c)
    await session.flush()
    s = Summary(content_id=c.id, summary="요약", keywords=["k"], reading_time=1)
    session.add(s)
    await session.flush()
    return s.id  # summary_id


async def test_needs_embedding_then_set(db_session):
    sid = await _seed_summary(db_session, hash_="e1")
    await db_session.commit()
    repo = EmbeddingRepository(db_session)

    needs = await repo.select_needs_embedding()
    assert sid in [r.id for r in needs]  # 임베딩 없으면 대상

    await repo.set_embedding(summary_id=sid, vector=_vec(1.0, 0.0))
    await db_session.commit()

    needs_after = await repo.select_needs_embedding()
    assert sid not in [r.id for r in needs_after]  # 채워지면 제외


async def test_find_similar_orders_by_cosine_distance(db_session):
    sid_a = await _seed_summary(db_session, hash_="a")  # [1,0,...]
    sid_b = await _seed_summary(db_session, hash_="b")  # [0,1,...]
    repo = EmbeddingRepository(db_session)
    await repo.set_embedding(summary_id=sid_a, vector=_vec(1.0, 0.0))
    await repo.set_embedding(summary_id=sid_b, vector=_vec(0.0, 1.0))
    await db_session.commit()

    # query가 A에 가까움 → A의 content가 상위
    near = await repo.find_similar(embedding=_vec(0.9, 0.1), k=2)
    assert len(near) == 2
    a_content = (
        await db_session.execute(select(Summary.content_id).where(Summary.id == sid_a))
    ).scalar_one()
    assert near[0].content_id == a_content
    assert near[0].distance < near[1].distance  # 거리 오름차순(가까운 것 먼저)
