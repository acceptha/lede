"""LLM provider 인터페이스 (절대규칙 1).

파이프라인 코드는 이 Protocol과 예외만 안다. 실제 SDK(openai/anthropic 등)는
app/llm/providers/ 안의 구현체에서만 import한다. 테스트는 FakeProvider를 주입한다.
"""

from typing import Protocol

from app.llm.schema import LLMSummary


class LLMError(Exception):
    """LLM 호출 일반 실패 (영구·일시 무관). 한 건 실패는 격리하고 계속 (절대규칙 5)."""


class LLMRateLimitError(LLMError):
    """공유 rate limit(429). full jitter 백오프 대상 — 동시 재시도 파도 방지 (DESIGN §5)."""


class LLMProvider(Protocol):
    async def summarize(self, *, title: str, body: str) -> LLMSummary: ...
