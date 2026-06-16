"""키워드 정규화 단위 테스트 — 점수 함수 정규화 케이스 (대소문자·한/영 별칭, 절대규칙 6)."""

from app.keywords import normalize_keyword, normalize_keywords


def test_lowercases():
    assert normalize_keyword("Docker") == "docker"
    assert normalize_keyword("PYTHON") == "python"


def test_korean_alias_maps_to_canonical():
    assert normalize_keyword("도커") == "docker"
    assert normalize_keyword("람다") == "aws lambda"
    assert normalize_keyword("k8s") == "kubernetes"


def test_whitespace_collapsed():
    assert normalize_keyword("  AWS   Lambda ") == "aws lambda"


def test_normalize_keywords_dedupes_across_aliases():
    # Docker + 도커 → 같은 canonical → 하나로 합쳐짐, 순서 보존
    assert normalize_keywords(["Docker", "도커", "Python"]) == ["docker", "python"]


def test_normalize_keywords_drops_empty():
    assert normalize_keywords(["", "  ", "Go"]) == ["go"]
