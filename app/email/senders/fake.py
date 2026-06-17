"""테스트·로컬용 가짜 이메일 sender — 실제로 보내지 않고 기록만.

pytest는 항상 이걸 주입한다(실발송이 1회라도 나가면 버그). sent 리스트로
발송 내용·횟수를 검증한다(예: 재실행 시 재발송 0회).
"""

from dataclasses import dataclass


@dataclass(slots=True)
class SentEmail:
    to: str
    subject: str
    text: str
    html: str | None


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None:
        self.sent.append(SentEmail(to=to, subject=subject, text=text, html=html))
