"""관심사 등록/조회 API (Swagger UI = 관리자 콘솔, DESIGN §3-3).

등록·삭제 시 동일 정규화 함수를 적용(규칙6) → 점수 함수와 같은 키워드 공간 보장.
repo는 Depends로 주입 → 테스트는 FakeRepo로 오버라이드(DB 없이 검증).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.interests.repository import InterestRepository, SqlInterestRepository
from app.interests.schema import InterestCreate, InterestList
from app.keywords import normalize_keyword, normalize_keywords

router = APIRouter(prefix="/interests", tags=["interests"])


def get_interest_repo(
    session: AsyncSession = Depends(get_session),
) -> InterestRepository:
    return SqlInterestRepository(session)


@router.post("", response_model=InterestList)
async def register_interests(
    body: InterestCreate,
    repo: InterestRepository = Depends(get_interest_repo),
) -> InterestList:
    await repo.add(normalize_keywords(body.keywords))
    return InterestList(keywords=await repo.list())


@router.get("", response_model=InterestList)
async def list_interests(
    repo: InterestRepository = Depends(get_interest_repo),
) -> InterestList:
    return InterestList(keywords=await repo.list())


@router.delete("/{keyword}", response_model=InterestList)
async def remove_interest(
    keyword: str,
    repo: InterestRepository = Depends(get_interest_repo),
) -> InterestList:
    await repo.remove(normalize_keyword(keyword))
    return InterestList(keywords=await repo.list())
