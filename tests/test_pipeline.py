"""run_pipeline 오케스트레이터 단위 테스트 — 세 단계를 순서대로 부르는지 검증.

세 잡을 가짜로 치환(monkeypatch)해 DB·LLM·네트워크 없이 순서·전달만 본다.
"""

import app.worker as w


async def test_run_pipeline_runs_steps_in_order(monkeypatch):
    calls: list[str] = []

    async def fake_collect(ctx):
        calls.append("collect")
        return {"new": 3}

    async def fake_summarize(ctx):
        calls.append("summarize")
        return {"summarized": 3}

    async def fake_digest(ctx):
        calls.append("digest")
        return {"status": "sent", "items": 2}

    monkeypatch.setattr(w, "collect_feeds", fake_collect)
    monkeypatch.setattr(w, "summarize_pending", fake_summarize)
    monkeypatch.setattr(w, "build_and_send_digest", fake_digest)

    result = await w.run_pipeline({"job_try": 1})

    # 수집 → 요약 → 다이제스트 순서
    assert calls == ["collect", "summarize", "digest"]
    # 각 단계 결과가 합쳐져 반환
    assert result["collect"]["new"] == 3
    assert result["summarize"]["summarized"] == 3
    assert result["digest"]["status"] == "sent"
