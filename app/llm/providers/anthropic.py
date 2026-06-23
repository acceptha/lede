"""Anthropic(Claude) provider — 실제 SDK는 이 파일에서만 import (절대규칙 1).

- async SDK(AsyncAnthropic)로 통일 (규칙4)
- 강제 tool use로 구조화 출력(summary_lines/keywords) → block.input(dict) 검증
- thinking 미사용(요약은 단순 작업 → 비용↓; Haiku는 effort/adaptive 미지원)
- max_retries=0 → 429를 LLMRateLimitError로 띄워 워커가 full jitter로 재시도 (DESIGN §5)
- usage(토큰)·추정 비용을 구조화 로깅 → README의 "측정된 숫자" 근거
"""

import logging
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from app.llm.provider import LLMError, LLMRateLimitError
from app.llm.schema import LLMSummary

logger = logging.getLogger("lede.llm.anthropic")

# Haiku 4.5 단가 (USD per 1M tokens). 캐시 read는 ~0.1x.
_PRICE_INPUT = 1.0
_PRICE_OUTPUT = 5.0
_PRICE_CACHE_READ = 0.1

_TOOL_NAME = "emit_summary"
_TOOL: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "본문의 3줄 요약과 핵심 키워드를 구조화해 반환한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary_lines": {
                "type": "array",
                "items": {"type": "string"},
                "description": "한국어 3줄 요약 (각 줄 한 문장)",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "핵심 키워드. 영문 소문자 canonical 형태 "
                    "(예: 도커→docker, AWS Lambda→aws lambda)"
                ),
            },
        },
        "required": ["summary_lines", "keywords"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "너는 한국어 뉴스레터 큐레이터다. 주어진 본문을 한국어 3줄로 요약하고 핵심 키워드를 뽑아라. "
    "키워드는 영문 소문자 canonical 형태로 통일한다. 읽기 시간은 계산하지 않는다. "
    "반드시 emit_summary 도구로만 답하라."
)


def _to_llm_error(exc: Exception) -> LLMError:
    """SDK 예외 → 파이프라인 예외. 429만 재시도 대상(LLMRateLimitError)."""
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitError(str(exc))
    return LLMError(f"{type(exc).__name__}: {exc}")


class AnthropicProvider:
    def __init__(self, model: str = "claude-haiku-4-5") -> None:
        self._model = model
        # 재시도는 워커가 full jitter로 담당 → SDK 자동 재시도는 끔
        self._client = AsyncAnthropic(max_retries=0)

    async def summarize(self, *, title: str, body: str) -> LLMSummary:
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM,
                        # 반복 시스템 프롬프트 캐싱(기법). 단 Haiku 최소 캐시 prefix(4096토큰)
                        # 미만이면 실제 캐시는 안 됨 → 주 비용 레버는 content_hash 캐싱.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": f"제목: {title}\n\n본문:\n{body}"}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except anthropic.APIError as exc:
            raise _to_llm_error(exc) from exc

        self._log_usage(resp.usage)

        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            raise LLMError(f"no tool_use block (stop_reason={resp.stop_reason})")
        try:
            return LLMSummary.model_validate(block.input)
        except Exception as exc:
            raise LLMError(f"invalid structured output: {exc}") from exc

    def _log_usage(self, usage: Any) -> None:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cost = (
            usage.input_tokens * _PRICE_INPUT
            + cache_read * _PRICE_CACHE_READ
            + usage.output_tokens * _PRICE_OUTPUT
        ) / 1_000_000
        logger.info(
            "llm_usage",
            extra={
                "event": "llm_usage",
                "provider": "anthropic",
                "model": self._model,
                "input_tokens": usage.input_tokens,
                "cache_read": cache_read,
                "output_tokens": usage.output_tokens,
                "cost_usd": round(cost, 6),
            },
        )
