"""구조화 로깅(JSON) — Flower 대신 로그로 관측 (DESIGN §2). 외부 의존성 없음.

worker/scheduler/app가 lede.* 로그를 JSON 한 줄로 stdout에 출력한다.
logger.info("event", extra={...})로 넘긴 필드를 JSON에 그대로 포함 → 비용·잡·실패 파싱 가능.
"""

import json
import logging
import sys

# 표준 LogRecord 속성 집합 — 이 외의 키를 extra로 보고 JSON에 포함한다.
_STD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """lede.* 로거를 JSON으로 stdout에 출력. idempotent(중복 핸들러 방지).

    'lede' 로거에만 핸들러를 달고 propagate=False → arq/uvicorn 기본 로깅과 충돌 없음.
    """
    logger = logging.getLogger("lede")
    if any(getattr(h, "_lede_json", False) for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._lede_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
