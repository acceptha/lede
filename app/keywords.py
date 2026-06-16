"""키워드 정규화 — LLM 출력과 user_interests 등록에 **동일 적용** (절대규칙 6).

소문자화 + 별칭 매핑으로 두 집합을 같은 공간에 놓는다. 한쪽만 정규화하면
점수 함수(Jaccard)가 표기 흔들림 때문에 망가진다 (DESIGN §5 적용 정책 1).
별칭 표는 통제 어휘 초안 — 수집 데이터를 보며 점진 확장 (DESIGN §11).
"""

# 별칭(소문자 기준) → canonical
_ALIASES: dict[str, str] = {
    "도커": "docker",
    "쿠버네티스": "kubernetes",
    "k8s": "kubernetes",
    "파이썬": "python",
    "장고": "django",
    "람다": "aws lambda",
    "aws람다": "aws lambda",
}


def normalize_keyword(keyword: str) -> str:
    """공백 정리 + 소문자화 + 별칭 치환."""
    collapsed = " ".join(keyword.split()).lower()
    return _ALIASES.get(collapsed, collapsed)


def normalize_keywords(keywords: list[str]) -> list[str]:
    """정규화 후 빈 값 제거 + 순서 보존 중복 제거."""
    seen: set[str] = set()
    out: list[str] = []
    for kw in keywords:
        normalized = normalize_keyword(kw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out
