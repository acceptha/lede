"""예상 읽기 시간 — LLM에 묻지 않고 글자수÷분당속도로 직접 계산 (절대규칙 3, 토큰 절약)."""

import math


def estimate_reading_time(text: str, chars_per_min: int = 500) -> int:
    """분 단위(올림). 빈 글은 0, 그 외 최소 1분."""
    chars = len(text)
    if chars == 0:
        return 0
    return max(1, math.ceil(chars / chars_per_min))
