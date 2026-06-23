"""구조화 로깅 단위 테스트 — JSON 포매터 출력 검증 (네트워크/DB 0)."""

import json
import logging

from app.logging_config import JsonFormatter, setup_logging


def _record(**extra) -> logging.LogRecord:
    rec = logging.LogRecord(
        name="lede.test",
        level=logging.INFO,
        pathname="f.py",
        lineno=1,
        msg="llm_usage",
        args=None,
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_formats_base_fields_as_json():
    out = JsonFormatter().format(_record())
    data = json.loads(out)
    assert data["msg"] == "llm_usage"
    assert data["level"] == "INFO"
    assert data["logger"] == "lede.test"
    assert "ts" in data


def test_includes_extra_fields():
    out = JsonFormatter().format(_record(provider="ollama", cost_usd=0, prompt_tokens=499))
    data = json.loads(out)
    assert data["provider"] == "ollama"
    assert data["cost_usd"] == 0
    assert data["prompt_tokens"] == 499


def test_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        rec = logging.LogRecord("lede.test", logging.ERROR, "f", 1, "err", None, sys.exc_info())
    data = json.loads(JsonFormatter().format(rec))
    assert "ValueError" in data["exc"]


def test_setup_logging_is_idempotent():
    setup_logging()
    setup_logging()
    handlers = [h for h in logging.getLogger("lede").handlers if getattr(h, "_lede_json", False)]
    assert len(handlers) == 1
