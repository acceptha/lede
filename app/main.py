"""FastAPI 앱 진입점.

무거운 일(수집·요약·발송)은 직접 하지 않고 워커에 위임한다 (DESIGN §2 역할 분리).
이 단계에서는 부팅 확인용 /health 만 노출한다.
"""

from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    summary="AI Newsletter Curator — Swagger UI가 관리자 콘솔 (DESIGN §3-3)",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """기동 확인용 헬스 체크."""
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}
