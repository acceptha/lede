"""dead-letter API 테스트 — repo를 FakeRepo로 오버라이드해 DB 없이 검증."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.deadletter.router import get_deadletter_repo
from app.main import app


class _Row:
    def __init__(self, job_type, content_id, error, attempts):
        self.job_type = job_type
        self.content_id = content_id
        self.error = error
        self.attempts = attempts
        self.created_at = datetime(2026, 6, 23, tzinfo=UTC)
        self.updated_at = datetime(2026, 6, 23, tzinfo=UTC)


class FakeDeadLetterRepo:
    def __init__(self, rows):
        self._rows = rows

    async def record(self, *, job_type, content_id, error):
        self._rows.append(_Row(job_type, content_id, error, 1))

    async def list(self):
        return self._rows


@pytest.fixture
def client_with_rows():
    def _make(rows):
        app.dependency_overrides[get_deadletter_repo] = lambda: FakeDeadLetterRepo(rows)
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_list_dead_letters_returns_rows(client_with_rows):
    rows = [_Row("summarize", 7, "ollama request failed", 3)]
    resp = client_with_rows(rows).get("/dead-letters")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["job_type"] == "summarize"
    assert body[0]["content_id"] == 7
    assert body[0]["attempts"] == 3
    assert "ollama" in body[0]["error"]


def test_list_dead_letters_empty(client_with_rows):
    resp = client_with_rows([]).get("/dead-letters")
    assert resp.status_code == 200
    assert resp.json() == []
