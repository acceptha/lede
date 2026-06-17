"""FastAPI 앱 진입점.

무거운 일(수집·요약·발송)은 직접 하지 않고 워커에 위임한다 (DESIGN §2 역할 분리).
API는 가벼운 CRUD(관심사 등록·조회)와 헬스 체크를 담당.
"""

from fastapi import FastAPI

from app.config import get_settings
from app.interests.router import router as interests_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    summary="AI Newsletter Curator — Swagger UI가 관리자 콘솔 (DESIGN §3-3)",
)

app.include_router(interests_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """기동 확인용 헬스 체크."""
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}
