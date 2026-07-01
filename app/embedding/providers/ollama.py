"""Ollama(로컬) 임베딩 provider — httpx로 /api/embed 호출 (절대규칙 1·4). 비용 $0.

기본 모델 bge-m3(다국어, 한국어 포함). SDK 없이 REST 배치 호출.
"""

import logging
from typing import Any

import httpx

from app.embedding.provider import EmbeddingError

logger = logging.getLogger("lede.embedding.ollama")


def _parse_embeddings(data: dict[str, Any], expected: int) -> list[list[float]]:
    """Ollama /api/embed 응답 → 벡터 목록. 개수 불일치·누락이면 EmbeddingError."""
    embeddings = data.get("embeddings")
    if not embeddings or len(embeddings) != expected:
        raise EmbeddingError(f"ollama embed: 예상 {expected}개, 실제 {data!r}"[:200])
    return embeddings


class OllamaEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "bge-m3",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self._model, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/embed", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"ollama embed request failed: {exc!r}") from exc
        return _parse_embeddings(data, len(texts))
