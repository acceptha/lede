"""임베딩 provider 단위 테스트 — Fake 결정론성 + Ollama 응답 파싱 (네트워크 0)."""

import pytest

from app.embedding.provider import EmbeddingError
from app.embedding.providers.fake import FakeEmbeddingProvider
from app.embedding.providers.ollama import _parse_embeddings


async def test_fake_is_deterministic():
    provider = FakeEmbeddingProvider()
    first = await provider.embed(["안녕"])
    second = await provider.embed(["안녕"])
    assert first == second  # 같은 텍스트 → 같은 벡터
    assert provider.call_count == 2


async def test_fake_mapping_override():
    provider = FakeEmbeddingProvider(mapping={"x": [1.0, 0.0]})
    assert (await provider.embed(["x"]))[0] == [1.0, 0.0]


async def test_fake_batch_length():
    provider = FakeEmbeddingProvider()
    out = await provider.embed(["a", "b", "c"])
    assert len(out) == 3


def test_parse_ollama_ok():
    vectors = _parse_embeddings({"embeddings": [[0.1, 0.2], [0.3, 0.4]]}, 2)
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_parse_ollama_missing_raises():
    with pytest.raises(EmbeddingError):
        _parse_embeddings({}, 1)


def test_parse_ollama_count_mismatch_raises():
    with pytest.raises(EmbeddingError):
        _parse_embeddings({"embeddings": [[0.1]]}, 2)
