"""코사인 유사도 — 임베딩 기반 점수 전략 (V3 방향, DESIGN §5).

Jaccard는 정확 토큰 매칭이라 `AI`≠`인공지능`이면 0. 코사인은 의미 벡터 각도라
표기가 달라도 의미가 가까우면 높은 값을 준다. 순수 함수 → 단독 테스트 가능.
"""

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"차원 불일치: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_by_cosine(
    query: list[float],
    candidates: list[tuple[int, list[float]]],
    *,
    top_n: int = 0,
) -> list[tuple[int, float]]:
    """(content_id, vector) 후보를 query와의 코사인 유사도 내림차순 정렬.

    top_n>0이면 상위 N건. Jaccard의 top-N 선정과 같은 형태로 전략 교체가 쉽다.
    """
    scored = [(cid, cosine_similarity(query, vec)) for cid, vec in candidates]
    scored.sort(key=lambda cs: cs[1], reverse=True)
    return scored[:top_n] if top_n > 0 else scored
