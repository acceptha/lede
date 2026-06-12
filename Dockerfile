# app·worker 공용 이미지. 실행 커맨드는 docker-compose에서 분기한다.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 소스 전체를 복사한 뒤 설치 (setuptools가 app 패키지를 찾을 수 있어야 함)
COPY . .
RUN pip install --upgrade pip && pip install ".[dev]"

# 기본은 API. worker는 compose에서 command 오버라이드
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
