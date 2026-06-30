"""통합 테스트용 픽스처 — 실 Postgres(TEST_DATABASE_URL)에 대해 동작.

TEST_DATABASE_URL이 없으면 integration 마커 테스트는 skip(단위 테스트는 DB 없이 그대로).
격리: 매 테스트 전에 전 테이블 TRUNCATE. create_all은 checkfirst로 멱등.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401  (테이블 등록)
from app.db.base import Base

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    """TEST_DATABASE_URL 없으면 integration 테스트 skip."""
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL 미설정 — 통합 테스트 skip")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # 멱등(checkfirst)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with maker() as cleaner:
        await cleaner.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await cleaner.commit()

    async with maker() as session:
        yield session
    await engine.dispose()
