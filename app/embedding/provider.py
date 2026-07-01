"""임베딩 provider 인터페이스 (LLM provider와 같은 추상화 철학, 절대규칙 1).

점수 전략을 Jaccard(정확 토큰) → 임베딩 코사인(의미 기반)으로 갈아끼우기 위한 토대.
실제 SDK/HTTP는 embedding/providers/ 안에서만. 테스트는 FakeEmbeddingProvider 주입.
"""

from typing import Protocol


class EmbeddingError(Exception):
    """임베딩 생성 실패."""


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
