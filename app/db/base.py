"""async SQLAlchemy 베이스 — DeclarativeBase + 엔진/세션 팩토리.

DB는 async 드라이버(asyncpg)로만 접근한다 (CLAUDE.md 절대규칙 4).
엔진 생성은 lazy라 import 시점에 실제 연결하지 않는다.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스. Alembic은 이 metadata를 대상으로 마이그레이션을 생성한다."""


engine = create_async_engine(settings.database_url, future=True)

SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
