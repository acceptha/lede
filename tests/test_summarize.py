"""요약 서비스 단위 테스트 — FakeProvider 주입, LLM 실호출 0회 (절대규칙 1).

읽기 시간을 LLM이 아니라 글자수로 계산하는지(규칙3), 키워드를 정규화하는지(규칙6),
HTML을 제거해 토큰을 아끼는지(규칙3)를 검증한다.
"""

from app.llm.providers.fake import FakeProvider
from app.llm.schema import LLMSummary
from app.summarize.service import summarize_content


async def test_normalizes_keywords_and_joins_summary_lines():
    provider = FakeProvider(
        LLMSummary(summary_lines=["첫째", "둘째", "셋째"], keywords=["Docker", "도커", "Python"])
    )
    data = await summarize_content(title="제목", body="본문", provider=provider)
    assert data.summary == "첫째\n둘째\n셋째"
    # Docker + 도커 → docker 하나로, 정규화 + 중복 제거
    assert data.keywords == ["docker", "python"]
    assert provider.call_count == 1


async def test_reading_time_from_charcount_not_llm():
    provider = FakeProvider(LLMSummary(summary_lines=["x"], keywords=[]))
    body = "<p>" + ("가" * 1000) + "</p>"  # 텍스트 1000자
    data = await summarize_content(title="t", body=body, provider=provider, chars_per_min=500)
    assert data.reading_time == 2  # ceil(1000 / 500)


async def test_html_stripped_before_provider_for_token_saving():
    provider = FakeProvider(LLMSummary(summary_lines=["x"], keywords=[]))
    await summarize_content(
        title="t",
        body="<div>안녕 <b>세계</b><script>alert(1)</script></div>",
        provider=provider,
    )
    # provider에는 태그·script 내용이 제거된 텍스트만 전달돼야 한다
    assert provider.last_body == "안녕 세계"
    assert "<" not in (provider.last_body or "")
