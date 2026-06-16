"""재시도 백오프 — 경로별로 의도적으로 다르게 (DESIGN §5).

RSS·SES는 herd가 없어 결정론적 지수 백오프를 쓴다(이 함수).
LLM 요약 경로는 공유 rate limit(429)에 동시 재시도가 몰리는 thundering herd를
막기 위해 full jitter를 따로 적용하므로 이 함수를 쓰지 않는다.
"""


def deterministic_backoff(attempt: int, base: float = 2.0) -> float:
    """attempt(1부터, Arq의 job_try)에 대한 다음 재시도 대기 초.

    attempt=1 → base, 2 → 2·base, 3 → 4·base … (지수, 무작위화 없음).
    """
    return base * (2 ** (attempt - 1))
