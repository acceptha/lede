"""ORM 모델 — DESIGN §5 데이터 모델을 그대로 옮긴 단일 진실 공급원.

idempotency의 실체인 두 제약을 처음부터 박는다 (CLAUDE.md 절대규칙 2):
- contents.content_hash UNIQUE      → 같은 글 재요약 0회의 캐시 키
- digests (user_id, digest_date) UNIQUE → 중복 발송 0회
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interests: Mapped[list["UserInterest"]] = relationship(back_populates="user")
    digests: Mapped[list["Digest"]] = relationship(back_populates="user")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(Text)
    # RSS / (V2+에서 crawl 등). MVP는 RSS만.
    source_type: Mapped[str] = mapped_column(String(50), default="rss")

    contents: Mapped[list["Content"]] = relationship(back_populates="source")


class Content(Base):
    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 본문 해시 — 중복 차단 + 요약 캐시 키 (절대규칙 2)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    source: Mapped[Source] = relationship(back_populates="contents")
    summary: Mapped["Summary | None"] = relationship(back_populates="content", uselist=False)


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"), unique=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    # 정규화된 canonical 키워드 배열 (DESIGN §5 — 필요 시 GIN 인덱스)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # 글자수 ÷ 분당 속도로 직접 계산 (LLM에 묻지 않음, 절대규칙 3). 단위: 분
    reading_time: Mapped[int | None] = mapped_column(Integer)

    content: Mapped[Content] = relationship(back_populates="summary")


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_user_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # 등록 시 정규화 함수 적용 (소문자화 + 별칭 매핑) — 점수 함수 입력
    keyword: Mapped[str] = mapped_column(String(100), index=True)

    user: Mapped[User] = relationship(back_populates="interests")


class UserEvent(Base):
    __tablename__ = "user_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"))
    # view / click / save — MVP는 적재만, 추천 활용은 V4
    event_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Digest(Base):
    __tablename__ = "digests"
    # 발송 idempotency의 실체 (절대규칙 2)
    __table_args__ = (UniqueConstraint("user_id", "digest_date", name="uq_user_digest_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    digest_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="digests")
    items: Mapped[list["DigestItem"]] = relationship(back_populates="digest")


class DigestItem(Base):
    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id", ondelete="CASCADE"))
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"))
    # 선정 당시 점수 스냅샷 — 점수 함수 품질 회고 / V3·V4 측정 데이터
    score: Mapped[float] = mapped_column()

    digest: Mapped[Digest] = relationship(back_populates="items")
