"""LLM 구조화 출력 스키마 (절대규칙 3: 출력은 JSON으로 받아 파싱).

읽기 시간은 여기 없다 — LLM에 묻지 않고 글자수÷속도로 직접 계산한다.
keywords는 정규화 전 원본. 저장 직전에 normalize_keywords를 태운다(절대규칙 6).
"""

from pydantic import BaseModel, Field


class LLMSummary(BaseModel):
    summary_lines: list[str] = Field(..., description="3줄 요약")
    keywords: list[str] = Field(default_factory=list, description="핵심 키워드(정규화 전)")
