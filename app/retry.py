"""재시도 백오프 — 경로별로 의도적으로 다르게 (DESIGN §5).

- RSS·SES: herd가 없어 결정론적 지수 백오프 (deterministic_backoff).
- LLM 요약: 공유 rate limit(429)에 동시 재시도가 몰리는 thundering herd를
  흩뿌리기 위해 full jitter (full_jitter). 둘을 섞지 않는 게 의도다.
"""

import random


def deterministic_backoff(attempt: int, base: float = 2.0) -> float:
    """attempt(1부터, Arq의 job_try)에 대한 다음 재시도 대기 초.

    attempt=1 → base, 2 → 2·base, 3 → 4·base … (지수, 무작위화 없음).
    """
    return base * (2 ** (attempt - 1))


def full_jitter(attempt: int, base: float = 2.0) -> float:
    """random(0, base·2**(attempt-1)). LLM 재시도 전용.

    상한은 지수로 키우되 실제 대기는 [0, 상한) 균등 무작위 → 재시도 파도를 분산.
    """
    return random.uniform(0, base * (2 ** (attempt - 1)))
