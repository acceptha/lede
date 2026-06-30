"""RSS 수집 — 네트워크(async httpx)와 파싱(feedparser)을 분리.

fetch_feed: 네트워크 I/O만 (async). parse_feed: 받아온 바이트를 파싱 (순수 함수, I/O 없음).
이렇게 나눠야 테스트에서 네트워크 없이 parse_feed를 검증할 수 있다 (절대규칙 4).
"""

from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from pydantic import BaseModel

# RSS 호출 타임아웃(초). RSS 경로는 결정론적 백오프로 재시도 (DESIGN §5).
DEFAULT_TIMEOUT = 15.0

# 일부 피드(토스 등)는 비표준 UA를 차단 → 브라우저형 UA로 공개 RSS를 정상 수신.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class RawEntry(BaseModel):
    """피드에서 추출한 한 건의 원문 (DB 저장 전 단계)."""

    title: str
    body: str
    url: str
    published_at: datetime | None = None


async def fetch_feed(url: str, client: httpx.AsyncClient) -> bytes:
    """피드 원본 바이트를 가져온다. 4xx/5xx면 예외 → 호출부에서 재시도 판단."""
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.content


def _extract_body(entry: Any) -> str:
    """본문 추출: content[].value(전문) 우선, 없으면 summary(요약)."""
    contents = entry.get("content")
    if contents:
        return contents[0].get("value", "")
    return entry.get("summary", "")


def _extract_published(entry: Any) -> datetime | None:
    """feedparser가 UTC로 정규화한 struct_time → aware datetime."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


def parse_feed(raw: bytes) -> list[RawEntry]:
    """피드 바이트를 RawEntry 목록으로. link/body가 없는 불완전 항목은 건너뛴다."""
    parsed = feedparser.parse(raw)
    entries: list[RawEntry] = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        body = _extract_body(entry).strip()
        if not url or not body:
            continue
        entries.append(
            RawEntry(
                title=title,
                body=body,
                url=url,
                published_at=_extract_published(entry),
            )
        )
    return entries
