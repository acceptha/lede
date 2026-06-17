"""Jaccard 계수 — MVP 관심도 점수 (DESIGN §5).

|A∩B| / |A∪B|. 0~1 정규화라 threshold·top-N 자르기가 직관적.
빈 집합/합집합 0이면 0.0 (0으로 나누기 회피).
"""


def jaccard(a: set[str], b: set[str]) -> float:
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union
