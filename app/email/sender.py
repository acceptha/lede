"""이메일 발송 인터페이스 (LLM provider와 같은 추상화 철학).

파이프라인은 이 Protocol만 안다. 실제 전송 SDK(boto3/SES 등)는 senders/ 안에서만 import.
테스트는 FakeEmailSender를 주입해 실발송 0회를 보장한다.
"""

from typing import Protocol


class EmailError(Exception):
    """발송 실패. SES는 결정론적 지수 백오프로 재시도 (DESIGN §5 — 하루 1통이라 herd 없음)."""


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None: ...
