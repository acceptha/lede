"""임베딩 provider 선택 — 설정값으로 구현체를 고른다 (lazy import)."""

from app.config import Settings
from app.embedding.provider import EmbeddingProvider
from app.embedding.providers.fake import FakeEmbeddingProvider


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "fake":
        return FakeEmbeddingProvider()
    if settings.embedding_provider == "ollama":
        from app.embedding.providers.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url, model=settings.ollama_embed_model
        )
    raise ValueError(f"unknown embedding_provider: {settings.embedding_provider!r}")
