"""관심사 API 요청/응답 스키마 (Pydantic v2)."""

from pydantic import BaseModel, Field


class InterestCreate(BaseModel):
    keywords: list[str] = Field(..., min_length=1, description="등록할 관심 키워드들")


class InterestList(BaseModel):
    keywords: list[str]
