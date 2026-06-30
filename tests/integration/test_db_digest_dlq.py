"""실 DB 통합 테스트 — 점수 선정·다이제스트 idempotency + dead-letter park."""

from datetime import UTC, date, datetime

import pytest

from app.db.models import Content, Source, Summary, User, UserInterest
from app.deadletter.repository import SqlDeadLetterRepository
from app.digest.repository import DigestRepository
from app.scoring.service import score_and_select

pytestmark = pytest.mark.integration


async def _seed_content(session, *, keywords: list[str], hash_: str) -> int:
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
    session.add(Summary(content_id=c.id, summary="요약", keywords=keywords, reading_time=2))
    await session.flush()
    return c.id


async def _seed_user(session, *, interests: list[str]) -> int:
    u = User(email="me@x.com", nickname="seed")
    session.add(u)
    await session.flush()
    for kw in interests:
        session.add(UserInterest(user_id=u.id, keyword=kw))
    await session.flush()
    return u.id


async def test_scoring_selection_and_send_idempotency(db_session):
    cid_match = await _seed_content(db_session, keywords=["ai", "수출통제"], hash_="m")
    await _seed_content(db_session, keywords=["스포츠"], hash_="n")  # 미겹침 → 제외
    uid = await _seed_user(db_session, interests=["ai", "수출통제"])
    await db_session.commit()

    repo = DigestRepository(db_session)
    interests = await repo.get_interest_keywords(user_id=uid)
    candidates = await repo.select_scoring_candidates()
    selections = score_and_select(candidates=candidates, interests=interests, top_n=5)

    ids = [s.content_id for s in selections]
    assert cid_match in ids  # 겹치는 콘텐츠 선정
    assert all(s.score > 0 for s in selections)  # score>0만
    assert len(selections) == 1  # 미겹침 콘텐츠는 제외

    digest = await repo.create(user_id=uid, digest_date=date(2026, 1, 1))
    await repo.add_items(
        digest_id=digest.id, selections=[(s.content_id, s.score) for s in selections]
    )
    await db_session.commit()

    # 발송 처리 → 같은 날 다이제스트는 sent로 조회 (재발송 방지의 근거)
    await repo.mark_sent(digest_id=digest.id, sent_at=datetime.now(UTC))
    await db_session.commit()
    again = await repo.get_by_date(user_id=uid, digest_date=date(2026, 1, 1))
    assert again is not None and again.status == "sent"


async def test_dead_letter_upsert_and_park(db_session):
    cid = await _seed_content(db_session, keywords=["x"], hash_="d")
    await db_session.commit()

    dlq = SqlDeadLetterRepository(db_session)
    await dlq.record(job_type="summarize", content_id=cid, error="e1")
    await db_session.commit()
    await dlq.record(job_type="summarize", content_id=cid, error="e2")
    await db_session.commit()

    rows = await dlq.list()
    assert len(rows) == 1  # 대상당 1행(upsert)
    assert rows[0].attempts == 2  # 누적
    assert rows[0].error == "e2"  # 최신 에러로 갱신

    # 임계값에 따라 park 여부
    assert await dlq.parked_content_ids(job_type="summarize", max_attempts=2) == {cid}
    assert await dlq.parked_content_ids(job_type="summarize", max_attempts=3) == set()
