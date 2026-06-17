"""email sender 선택 — 설정값으로 구현체를 고른다.

MVP 기본은 "fake". 실제 SES sender는 AWS 자격증명·검증 주소가 준비되면
여기 분기에 추가한다 (DESIGN §8 샌드박스 게이트). SDK import는 해당 구현체 안에서만.
"""

from app.config import Settings
from app.email.sender import EmailSender
from app.email.senders.fake import FakeEmailSender


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "fake":
        return FakeEmailSender()
    raise ValueError(f"unknown email_provider: {settings.email_provider!r} (실 SES는 추후 추가)")
