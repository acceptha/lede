"""요약 오케스트레이션 — provider를 주입받아 LLM SDK로부터 분리 (절대규칙 1).

HTML 제거(토큰 절약) → provider 호출(구조화 출력) → 키워드 정규화(규칙6) →
읽기 시간 직접 계산(규칙3). DB는 모른다 — 저장은 repository가 담당.
"""

from dataclasses import dataclass

from app.keywords import normalize_keywords
from app.llm.provider import LLMProvider
from app.reading_time import estimate_reading_time
from app.text import html_to_text


@dataclass(slots=True)
class SummaryData:
    summary: str
    keywords: list[str]  # 정규화된 canonical 태그
    reading_time: int  # 분


async def summarize_content(
    *,
    title: str,
    body: str,
    provider: LLMProvider,
    chars_per_min: int = 500,
) -> SummaryData:
    text = html_to_text(body)
    result = await provider.summarize(title=title, body=text)
    return SummaryData(
        summary="\n".join(result.summary_lines),
        keywords=normalize_keywords(result.keywords),
        reading_time=estimate_reading_time(text, chars_per_min),
    )
