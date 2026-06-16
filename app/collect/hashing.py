"""본문 해시 — 중복 차단 + 요약 캐시 키 (CLAUDE.md 절대규칙 2).

같은 글이면 표기 흔들림(공백·개행)에 관계없이 같은 해시가 나오도록 정규화한 뒤 sha256.
"""

import hashlib


def normalize_text(text: str) -> str:
    """연속 공백/개행을 단일 공백으로 접고 양끝을 다듬는다."""
    return " ".join(text.split())


def compute_content_hash(body: str) -> str:
    """정규화된 본문의 sha256 16진수(64자). contents.content_hash와 길이 일치."""
    return hashlib.sha256(normalize_text(body).encode("utf-8")).hexdigest()
