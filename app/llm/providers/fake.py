"""테스트·로컬용 가짜 provider — 네트워크/비용 0, 결정론적.

pytest는 항상 이걸 주입한다(실호출 0회면 정상, 1회라도 나가면 버그 — CLAUDE.md 절대규칙 1).
call_count로 캐싱(재요약 0회)을, last_body로 토큰 절약(HTML 제거)을 검증할 수 있다.
"""

from app.llm.schema import LLMSummary


class FakeProvider:
    """response를 주면 그대로 반환, 없으면 입력에서 결정론적으로 생성한다."""

    def __init__(self, response: LLMSummary | None = None) -> None:
        self._response = response
        self.call_count = 0
        self.last_title: str | None = None
        self.last_body: str | None = None

    async def summarize(self, *, title: str, body: str) -> LLMSummary:
        self.call_count += 1
        self.last_title = title
        self.last_body = body
        if self._response is not None:
            return self._response
        words = [w for w in body.split() if w][:3]
        return LLMSummary(
            summary_lines=[f"{title} 요약 {i}" for i in (1, 2, 3)],
            keywords=words,
        )
