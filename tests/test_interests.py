"""관심사 API 테스트 — repo를 FakeRepo로 오버라이드해 DB 없이 검증.

등록 시 정규화(규칙6)와 중복 제거가 일어나는지, 조회·삭제가 동작하는지 확인.
"""

import pytest
from fastapi.testclient import TestClient

from app.interests.router import get_interest_repo
from app.main import app


class FakeInterestRepo:
    def __init__(self) -> None:
        self._kw: set[str] = set()

    async def add(self, keywords: list[str]) -> None:
        self._kw.update(keywords)

    async def list(self) -> list[str]:
        return sorted(self._kw)

    async def remove(self, keyword: str) -> bool:
        if keyword in self._kw:
            self._kw.discard(keyword)
            return True
        return False


@pytest.fixture
def client():
    fake = FakeInterestRepo()
    app.dependency_overrides[get_interest_repo] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_normalizes_and_dedupes(client):
    resp = client.post("/interests", json={"keywords": ["Docker", "도커", "Python"]})
    assert resp.status_code == 200
    # Docker + 도커 → docker 하나로 합쳐짐
    assert resp.json()["keywords"] == ["docker", "python"]


def test_list_after_register(client):
    client.post("/interests", json={"keywords": ["AWS Lambda"]})
    resp = client.get("/interests")
    assert resp.json()["keywords"] == ["aws lambda"]


def test_remove_normalizes_keyword(client):
    client.post("/interests", json={"keywords": ["go", "rust"]})
    resp = client.delete("/interests/Go")  # 대문자 → 정규화 → go 삭제
    assert resp.status_code == 200
    assert "go" not in resp.json()["keywords"]
    assert "rust" in resp.json()["keywords"]


def test_empty_keywords_rejected(client):
    resp = client.post("/interests", json={"keywords": []})
    assert resp.status_code == 422  # min_length=1 검증
