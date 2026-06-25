"""dead-letter API 응답 스키마."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeadLetterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_type: str
    content_id: int | None
    error: str
    attempts: int
    created_at: datetime
    updated_at: datetime
