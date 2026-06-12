"""뼈대 스모크 테스트 — /health 응답 확인. LLM 실호출 0회 (CLAUDE.md 절대규칙 1)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "lede"
