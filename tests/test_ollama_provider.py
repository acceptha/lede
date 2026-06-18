"""Ollama provider 응답 파싱 단위 테스트 — 네트워크 없이 순수 함수만 검증.

실제 호출은 로컬 Ollama가 필요해 자동 테스트 대상이 아니다(수동 검증). 여기서는
/api/chat 응답(dict) → LLMSummary 변환과 빈 응답 처리만 본다.
"""

import pytest

from app.llm.provider import LLMError
from app.llm.providers.ollama import _parse_response


def test_parses_valid_response():
    data = {
        "message": {
            "role": "assistant",
            "content": '{"summary_lines": ["첫째", "둘째", "셋째"], "keywords": ["docker", "aws"]}',
        }
    }
    result = _parse_response(data)
    assert result.summary_lines == ["첫째", "둘째", "셋째"]
    assert result.keywords == ["docker", "aws"]


def test_empty_content_raises_llm_error():
    with pytest.raises(LLMError):
        _parse_response({"message": {"content": ""}})


def test_missing_message_raises_llm_error():
    with pytest.raises(LLMError):
        _parse_response({"error": "model not found"})


def test_malformed_json_raises_llm_error():
    with pytest.raises(LLMError):
        _parse_response({"message": {"content": "not json"}})
