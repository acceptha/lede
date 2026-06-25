"""dead-letter 조회 API — 실패한 작업 관측 (Swagger=관리자 콘솔, DESIGN §2·§3-3)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.deadletter.repository import DeadLetterRepository, SqlDeadLetterRepository
from app.deadletter.schema import DeadLetterOut

router = APIRouter(prefix="/dead-letters", tags=["dead-letters"])


def get_deadletter_repo(
    session: AsyncSession = Depends(get_session),
) -> DeadLetterRepository:
    return SqlDeadLetterRepository(session)


@router.get("", response_model=list[DeadLetterOut])
async def list_dead_letters(
    repo: DeadLetterRepository = Depends(get_deadletter_repo),
) -> list[DeadLetterOut]:
    return await repo.list()
