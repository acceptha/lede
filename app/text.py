"""HTML → 플레인 텍스트. 외부 의존성 없이 stdlib만.

content:encoded 본문에서 태그를 제거해 (1) LLM에 보낼 토큰을 아끼고(절대규칙 3),
(2) 읽기 시간 글자수 기준을 본문 텍스트로 맞춘다. script/style 내용은 버린다.
"""

from html.parser import HTMLParser

_DROP_TAGS = {"script", "style"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _DROP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join("".join(self._parts).split())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text
