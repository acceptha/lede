"""테스트·로컬용 가짜 임베딩 provider — 네트워크 0, 결정론적.

같은 텍스트 → 같은 벡터(코사인 1.0)라 테스트에서 안정적. mapping으로 알려진 벡터 주입 가능.
"""

import hashlib


class FakeEmbeddingProvider:
    def __init__(self, mapping: dict[str, list[float]] | None = None, dim: int = 8) -> None:
        self._mapping = mapping or {}
        self._dim = dim
        self.call_count = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return [self._mapping.get(t) or self._deterministic(t) for t in texts]

    def _deterministic(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[: self._dim]]
