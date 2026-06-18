"""Anthropic provider 에러 매핑 단위 테스트 — 네트워크/키 없이 순수 함수만 검증.

실제 호출은 키·네트워크가 필요해 자동 테스트 대상이 아니다(수동 검증). 여기서는
SDK 예외 → 파이프라인 예외 변환만 본다: 429만 재시도 대상(LLMRateLimitError).
"""

import httpx

from app.llm.provider import LLMError, LLMRateLimitError
from app.llm.providers.anthropic import _to_llm_error


def _resp(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api"))


def test_rate_limit_maps_to_retryable():
    import anthropic

    exc = anthropic.RateLimitError("429", response=_resp(429), body=None)
    assert isinstance(_to_llm_error(exc), LLMRateLimitError)


def test_other_api_error_maps_to_non_retryable():
    import anthropic

    exc = anthropic.APIStatusError("500", response=_resp(500), body=None)
    mapped = _to_llm_error(exc)
    assert isinstance(mapped, LLMError)
    assert not isinstance(mapped, LLMRateLimitError)


def test_generic_exception_maps_to_llm_error():
    mapped = _to_llm_error(ValueError("boom"))
    assert isinstance(mapped, LLMError)
    assert not isinstance(mapped, LLMRateLimitError)
