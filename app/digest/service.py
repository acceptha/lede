"""다이제스트 이메일 렌더 — 순수 함수(DB·네트워크 없음)라 단독 테스트 가능.

3줄 요약 + 예상 읽기 시간 + 원문 링크를 담는다. 사용자 입력이 섞일 수 있는
title/url은 HTML escape (LLM 출력이라도 신뢰 경계로 취급).
"""

from dataclasses import dataclass
from datetime import date
from html import escape


@dataclass(slots=True)
class DigestItemView:
    title: str
    summary: str  # 줄바꿈(\n)으로 구분된 3줄 요약
    reading_time: int  # 분
    url: str


def render_email(*, digest_date: date, items: list[DigestItemView]) -> tuple[str, str, str]:
    """(subject, text, html) 반환."""
    subject = f"[lede] {digest_date.isoformat()} 다이제스트 ({len(items)}건)"

    text_blocks: list[str] = []
    html_blocks: list[str] = []
    for i, item in enumerate(items, 1):
        lines = item.summary.splitlines() or [item.summary]
        text_blocks.append(
            f"{i}. {item.title}\n"
            + "\n".join(f"   - {line}" for line in lines)
            + f"\n   예상 읽기 시간: {item.reading_time}분\n   {item.url}"
        )
        bullets = "".join(f"<li>{escape(line)}</li>" for line in lines)
        html_blocks.append(
            f"<h3>{i}. {escape(item.title)}</h3>"
            f"<ul>{bullets}</ul>"
            f"<p>예상 읽기 시간: {item.reading_time}분 · "
            f'<a href="{escape(item.url, quote=True)}">원문</a></p>'
        )

    text = "오늘의 추천 콘텐츠\n\n" + "\n\n".join(text_blocks)
    html = "<h2>오늘의 추천 콘텐츠</h2>" + "".join(html_blocks)
    return subject, text, html
