"""점수 선정 — 후보들을 Jaccard로 점수 매겨 top-N 선정 (DESIGN §5 적용 정책).

정책: score>0 만, 상위 N건(기본 5), 동점은 published_at 최신순. 0건이면 빈 리스트.
양쪽 키워드를 정규화 후 비교(이미 canonical이라 멱등·방어적) → 표기 흔들림 흡수(규칙6).
"""

from dataclasses import dataclass
from datetime import datetime

from app.keywords import normalize_keywords
from app.scoring.jaccard import jaccard


@dataclass(slots=True)
class Candidate:
    content_id: int
    keywords: list[str]
    published_at: datetime | None


@dataclass(slots=True)
class Selection:
    content_id: int
    score: float


def score_and_select(
    *,
    candidates: list[Candidate],
    interests: set[str] | list[str],
    top_n: int = 5,
) -> list[Selection]:
    interest_set = set(normalize_keywords(list(interests)))
    if not interest_set:
        return []  # 관심사 없으면 매칭 0건

    scored: list[tuple[Candidate, float]] = []
    for candidate in candidates:
        score = jaccard(interest_set, set(normalize_keywords(candidate.keywords)))
        if score > 0:
            scored.append((candidate, score))

    # 1순위 점수 내림차순, 2순위 published_at 최신순(None은 가장 오래된 것으로)
    scored.sort(
        key=lambda cs: (
            cs[1],
            cs[0].published_at.timestamp() if cs[0].published_at else float("-inf"),
        ),
        reverse=True,
    )

    chosen = scored[:top_n] if top_n > 0 else scored
    return [Selection(content_id=c.content_id, score=s) for c, s in chosen]
