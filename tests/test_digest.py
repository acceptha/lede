"""다이제스트 렌더 + 이메일 sender 단위 테스트 — 실발송 0회 (Fake 주입)."""

from datetime import date

from app.digest.service import DigestItemView, render_email
from app.email.senders.fake import FakeEmailSender


def _items() -> list[DigestItemView]:
    return [
        DigestItemView(
            title="제목A", summary="요약1\n요약2\n요약3", reading_time=5, url="https://e.com/a"
        ),
        DigestItemView(title="제목B", summary="한 줄 요약", reading_time=2, url="https://e.com/b"),
    ]


def test_render_email_lists_items_with_reading_time_and_link():
    subject, text, html = render_email(digest_date=date(2026, 6, 16), items=_items())
    assert "2026-06-16" in subject
    assert "2건" in subject
    # text 본문
    assert "제목A" in text
    assert "요약1" in text
    assert "5분" in text
    assert "https://e.com/a" in text
    # html 본문
    assert "제목B" in html
    assert "원문" in html


def test_render_email_escapes_untrusted_fields():
    items = [
        DigestItemView(
            title="<script>x</script>",
            summary="a & b",
            reading_time=1,
            url="https://e.com/x?q=1&y=2",
        )
    ]
    _, _, html = render_email(digest_date=date(2026, 6, 16), items=items)
    assert "<script>" not in html  # 이스케이프됨
    assert "&lt;script&gt;" in html
    assert "a &amp; b" in html


async def test_fake_email_sender_records_without_sending():
    sender = FakeEmailSender()
    await sender.send(to="a@b.com", subject="s", text="t", html="<p>t</p>")
    assert len(sender.sent) == 1
    assert sender.sent[0].to == "a@b.com"
    assert sender.sent[0].subject == "s"
