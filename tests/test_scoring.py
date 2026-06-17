"""점수 함수 단위 테스트 — Jaccard 값 + 적용 정책(정규화·top-N·score>0·동점).

성공 기준의 정규화 케이스(대소문자·한/영 별칭)와 "미겹침 콘텐츠 미포함"을 검증한다.
"""

from datetime import UTC, datetime

from app.scoring.jaccard import jaccard
from app.scoring.service import Candidate, score_and_select


def test_jaccard_values():
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert jaccard({"a"}, {"a"}) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0
    assert jaccard(set(), set()) == 0.0


def test_filters_zero_and_limits_top_n():
    interests = {"python", "docker"}
    candidates = [
        Candidate(1, ["python", "docker"], None),  # 2/2 = 1.0
        Candidate(2, ["python", "go"], None),  # 1/3
        Candidate(3, ["java"], None),  # 0 → 제외
    ]
    selections = score_and_select(candidates=candidates, interests=interests, top_n=2)
    ids = [s.content_id for s in selections]
    assert 3 not in ids  # 안 겹치면 미포함 (성공 기준)
    assert ids[0] == 1  # 높은 점수 먼저
    assert selections[0].score == 1.0


def test_normalization_case_and_korean_alias_match():
    # 관심사 "Docker"(대문자) ↔ 콘텐츠 "도커"(한글 별칭) → 같은 canonical → 매칭
    selections = score_and_select(
        candidates=[Candidate(1, ["도커"], None)], interests={"Docker"}, top_n=5
    )
    assert len(selections) == 1
    assert selections[0].score == 1.0


def test_tiebreak_by_published_at_desc():
    interests = {"python"}
    older = Candidate(1, ["python"], datetime(2026, 6, 1, tzinfo=UTC))
    newer = Candidate(2, ["python"], datetime(2026, 6, 10, tzinfo=UTC))
    selections = score_and_select(candidates=[older, newer], interests=interests, top_n=5)
    assert [s.content_id for s in selections] == [2, 1]  # 동점이면 최신 먼저


def test_empty_interests_returns_nothing():
    selections = score_and_select(
        candidates=[Candidate(1, ["python"], None)], interests=set(), top_n=5
    )
    assert selections == []
