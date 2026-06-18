"""provider 선택 — 설정값으로 구현체를 고른다.

MVP 기본은 "fake". 실제 공급자(openai/anthropic 등)는 공급자·키가 정해지면
여기 분기에 추가한다 (DESIGN §11: 측정 후 결정). SDK import는 해당 구현체 안에서만.
"""

from app.config import Settings
from app.llm.provider import LLMProvider
from app.llm.providers.fake import FakeProvider


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.llm_provider == "anthropic":
        # lazy import: fake 경로에서는 anthropic SDK를 로드하지 않음
        from app.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider(model=settings.anthropic_model)
    if settings.llm_provider == "ollama":
        from app.llm.providers.ollama import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    raise ValueError(f"unknown llm_provider: {settings.llm_provider!r}")
