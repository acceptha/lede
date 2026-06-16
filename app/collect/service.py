"""수집 오케스트레이션 — fetch와 sink를 주입받아 네트워크·DB로부터 분리.

LLM provider 주입(절대규칙 1)과 같은 철학: 파이프라인 로직은 인터페이스만 알고,
테스트는 가짜 fetch + 가짜 sink로 비용·부작용 0으로 검증한다.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.collect.hashing import compute_content_hash
from app.collect.rss import parse_feed

# (feed_url) -> 피드 바이트
FetchFn = Callable[[str], Awaitable[bytes]]


@dataclass(slots=True)
class CollectResult:
    source_id: int
    fetched: int  # 파싱된 유효 항목 수
    new: int  # 새로 저장된 수
    duplicate: int  # content_hash 중복으로 건너뛴 수


class ContentSink(Protocol):
    """저장 인터페이스. 신규 저장이면 True, 이미 있으면 False."""

    async def add_if_absent(
        self,
        *,
        source_id: int,
        title: str,
        body: str,
        url: str,
        published_at: datetime | None,
        content_hash: str,
    ) -> bool: ...


async def collect_source(
    *,
    source_id: int,
    feed_url: str,
    fetch: FetchFn,
    sink: ContentSink,
) -> CollectResult:
    """한 소스를 수집해 저장한다. 재실행해도 content_hash로 중복 0건 (절대규칙 2)."""
    raw = await fetch(feed_url)
    entries = parse_feed(raw)
    new = duplicate = 0
    for entry in entries:
        inserted = await sink.add_if_absent(
            source_id=source_id,
            title=entry.title,
            body=entry.body,
            url=entry.url,
            published_at=entry.published_at,
            content_hash=compute_content_hash(entry.body),
        )
        if inserted:
            new += 1
        else:
            duplicate += 1
    return CollectResult(source_id=source_id, fetched=len(entries), new=new, duplicate=duplicate)
