"""RSS 수집 단위 테스트 — 네트워크·DB·LLM 실호출 0회 (가짜 주입)."""

from datetime import UTC, datetime

from app.collect.hashing import compute_content_hash
from app.collect.rss import parse_feed
from app.collect.service import collect_source

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>First post</title>
      <link>https://example.com/1</link>
      <description>Body one</description>
      <pubDate>Mon, 09 Jun 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Second post</title>
      <link>https://example.com/2</link>
      <description>Body two</description>
      <pubDate>Tue, 10 Jun 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>No link, should be skipped</title>
      <description>orphan body</description>
    </item>
  </channel>
</rss>
"""


class FakeSink:
    """content_hash 집합으로 중복을 흉내내는 가짜 저장소."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.rows: list[dict] = []

    async def add_if_absent(self, *, content_hash: str, **fields) -> bool:
        if content_hash in self.seen:
            return False
        self.seen.add(content_hash)
        self.rows.append({"content_hash": content_hash, **fields})
        return True


async def fake_fetch(url: str) -> bytes:
    return SAMPLE_RSS


# --- hashing ---------------------------------------------------------------


def test_content_hash_normalizes_whitespace():
    # 공백/개행만 다른 본문은 같은 해시여야 한다 (표기 흔들림 흡수)
    assert compute_content_hash("a  b\n c") == compute_content_hash("a b c")


def test_content_hash_is_sha256_hex():
    h = compute_content_hash("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# --- parsing ---------------------------------------------------------------


def test_parse_feed_extracts_entries_and_skips_incomplete():
    entries = parse_feed(SAMPLE_RSS)
    # link 없는 3번째 항목은 제외 → 2건
    assert len(entries) == 2
    first = entries[0]
    assert first.title == "First post"
    assert first.url == "https://example.com/1"
    assert first.body == "Body one"
    assert first.published_at == datetime(2026, 6, 9, 10, 0, 0, tzinfo=UTC)


# --- collect orchestration -------------------------------------------------


async def test_collect_source_counts_new():
    sink = FakeSink()
    result = await collect_source(source_id=1, feed_url="x", fetch=fake_fetch, sink=sink)
    assert result.fetched == 2
    assert result.new == 2
    assert result.duplicate == 0


async def test_collect_source_is_idempotent_on_rerun():
    # 같은 sink로 두 번 수집 → 두 번째는 전부 중복 (재실행 시 중복 0건, 절대규칙 2)
    sink = FakeSink()
    await collect_source(source_id=1, feed_url="x", fetch=fake_fetch, sink=sink)
    second = await collect_source(source_id=1, feed_url="x", fetch=fake_fetch, sink=sink)
    assert second.new == 0
    assert second.duplicate == 2
    assert len(sink.rows) == 2
