"""Ollama(로컬) provider — 외부 SDK 없이 httpx로 로컬 REST API 호출 (절대규칙 1·4).

- async httpx로 localhost:11434/api/chat 호출 (sync 블로킹 없음)
- Ollama의 JSON 스키마 `format`으로 구조화 출력(summary_lines/keywords) 강제
- 로컬 실행이라 비용 $0, rate limit 없음 → 모든 실패는 LLMError(재시도는 잡 재실행이 담당)
- usage(토큰)·소요 시간을 구조화 로깅 (cost=0)
"""

import logging
from typing import Any

import httpx

from app.llm.provider import LLMError
from app.llm.schema import LLMSummary

logger = logging.getLogger("lede.llm.ollama")

# LLMSummary 구조화 출력 스키마 (Ollama structured outputs)
_FORMAT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_lines": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary_lines", "keywords"],
}

_SYSTEM = (
    "너는 한국어 뉴스레터 큐레이터다. 주어진 본문을 한국어 3줄로 요약하고 핵심 키워드를 뽑아라. "
    "summary_lines에는 3개의 문장을, keywords에는 영문 소문자 canonical 형태의 키워드를 담는다. "
    "읽기 시간은 계산하지 않는다."
)


def _parse_response(data: dict[str, Any]) -> LLMSummary:
    """Ollama /api/chat 응답(dict) → LLMSummary. content는 스키마에 맞는 JSON 문자열."""
    content = (data.get("message") or {}).get("content")
    if not content:
        raise LLMError(f"ollama returned no content (keys={list(data)})")
    try:
        return LLMSummary.model_validate_json(content)
    except Exception as exc:
        raise LLMError(f"invalid structured output: {exc}") from exc


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "exaone3.5:2.4b",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        # 첫 호출은 모델을 메모리에 로딩하느라 느릴 수 있어 타임아웃을 넉넉히
        self._timeout = timeout

    async def summarize(self, *, title: str, body: str) -> LLMSummary:
        payload = {
            "model": self._model,
            "stream": False,
            "format": _FORMAT,
            "keep_alive": "30m",  # 모델을 메모리에 유지 → 배치/반복 호출 시 콜드 로딩 회피
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"제목: {title}\n\n본문:\n{body}"},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            # 연결 실패(미실행)·타임아웃·HTTP 에러 모두 LLMError → 격리 후 재실행이 재시도
            raise LLMError(f"ollama request failed: {exc!r}") from exc

        self._log_usage(data)
        return _parse_response(data)

    def _log_usage(self, data: dict[str, Any]) -> None:
        total_ms = (data.get("total_duration") or 0) // 1_000_000
        logger.info(
            "llm_usage provider=ollama model=%s prompt_tokens=%s eval_tokens=%s "
            "total_ms=%s cost_usd=0(local)",
            self._model,
            data.get("prompt_eval_count"),
            data.get("eval_count"),
            total_ms,
        )
