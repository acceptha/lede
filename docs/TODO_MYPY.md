# TODO — mypy 정적 타입 검사 도입

> 상태: **미도입** (2026-09 기준)
> 성격: 의도적 기각이 아니라 **미완성 항목**. 넣어야 할 것을 아직 안 넣은 상태다.
> 관련: CLAUDE.md 절대규칙 1(LLM 추상화), DESIGN.md §2

---

## 1. 왜 필요한가 — Protocol 설계의 짝

이 프로젝트는 provider 추상화를 `typing.Protocol`(구조적 타이핑)로 구현했다.

```python
# app/llm/provider.py
class LLMProvider(Protocol):
    async def summarize(self, *, title: str, body: str) -> LLMSummary: ...
```

구현체(`FakeProvider`, `AnthropicProvider`, `OllamaProvider`)는 이 Protocol을
**상속하지 않는다.** 시그니처 모양만 맞으면 된다. 그래서 SDK 교체 비용이 0에 가깝다.

**대가:** 상속이 없으니 *"이 구현체가 정말 그 모양이 맞는지"* 를 확인해주는 주체가 없다.

| 검증 주체 | 이 문제를 잡는가 | 이유 |
|---|:---:|---|
| 파이썬 런타임 | ❌ | 타입 힌트를 검사하지 않는다 |
| pytest | ❌ | 절대규칙 1에 따라 **Fake만 주입**한다. 실제 provider는 한 번도 실행되지 않는다 |
| ruff (현재 CI) | ❌ | 린터·포매터. 타입 정합성은 검사 범위 밖 |
| **mypy** | ✅ | 실행 없이 시그니처를 Protocol과 대조 |

### 지금 검증되지 않는 코드

```
app/llm/providers/anthropic.py      ← pytest가 실행하지 않음
app/llm/providers/ollama.py         ← pytest가 실행하지 않음
app/embedding/providers/ollama.py   ← pytest가 실행하지 않음
```

이 세 파일의 `summarize` / `embed` 시그니처가 인터페이스와 어긋나도
**CI는 초록불이고, 운영에서 잡이 돌 때 처음 TypeError로 터진다.**

### mypy가 잡는 모습

```python
# app/llm/providers/anthropic.py 에서 인자명을 body → text 로 실수
async def summarize(self, *, title: str, text: str) -> LLMSummary: ...
```

```
$ mypy app/
app/llm/factory.py:19: error: Incompatible return value type
    (got "AnthropicProvider", expected "LLMProvider")
    Following member(s) of "AnthropicProvider" have conflicts:
        Expected: def (*, title: str, body: str) -> LLMSummary
        Got:      def (*, title: str, text: str) -> LLMSummary
```

`factory.py`의 반환 타입 선언(`-> LLMProvider`)이 검사 지점이 된다.
**Protocol 3세트(LLM·Email·Embedding) × 구현체 6개**를 사람 눈으로 대조하는 건 지속 불가능하다.

---

## 2. 도입 절차

### Step 1 — 의존성 + 설정 (`pyproject.toml`)

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",          # 추가
]

[tool.mypy]
python_version = "3.12"
files = ["app"]
# alembic 생성물은 보일러플레이트 — ruff와 동일하게 제외
exclude = ["^alembic/"]
# 점진 도입: 처음엔 아래 3개만 켜고, 통과하면 strict 쪽으로 조인다
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_optional = true

# 타입 스텁이 없는 서드파티는 무시 (없으면 import 에러로 도배된다)
[[tool.mypy.overrides]]
module = ["feedparser.*", "arq.*", "pgvector.*", "apscheduler.*"]
ignore_missing_imports = true
```

> **점진 도입 원칙:** 처음부터 `strict = true`로 켜면 오류 수백 개가 쏟아져
> 아무것도 못 한다. 위 최소 설정으로 **초록불을 먼저 만들고**, 그다음 커밋에서
> `disallow_untyped_defs` → `strict` 순으로 조인다. (한 번에 하나씩 = 커밋 단위 원칙)

### Step 2 — CI 스텝 추가 (`.github/workflows/ci.yml`)

```yaml
      - name: Lint (ruff)
        run: |
          ruff check .
          ruff format --check .

      - name: Type check (mypy)      # 추가 — ruff와 pytest 사이
        run: mypy app/

      - name: Test (unit, DB 불필요)
        run: pytest -q -m "not integration"
```

### Step 3 — 로컬 명령어 등록 (`CLAUDE.md` 명령어 섹션)

```bash
mypy app/                         # 정적 타입 검사 (Protocol 구현체 정합성)
```

---

## 3. 예상 걸림돌

| 걸림돌 | 대응 |
|---|---|
| 서드파티 스텁 없음 (feedparser, arq, pgvector, apscheduler) | 위 `ignore_missing_imports` 오버라이드 |
| SQLAlchemy 2.0 `Mapped[...]` | 2.0은 PEP 681을 지원해 mypy가 기본 인식. 별도 플러그인 불필요 |
| `ctx: dict`에서 꺼낸 값 (`ctx["llm_provider"]`) | `dict`는 값 타입이 `Any` → 검사가 느슨하다. `provider: LLMProvider = ctx[...]` 처럼 **명시 어노테이션**을 붙여야 검사 지점이 생긴다 (worker.py는 이미 그렇게 되어 있음) |
| Pydantic v2 | 공식 mypy 플러그인이 있으나 v2는 기본 지원이 좋아 초기엔 불필요 |
| 오류가 대량 발생 | `# type: ignore[에러코드]`로 임시 봉인 후 후속 커밋에서 제거. **파일 단위 무시는 지양** |

---

## 4. 도입 후 검증 (실제로 잡히는지 확인)

도구를 넣었으면 **일부러 깨뜨려서 잡히는지** 봐야 한다. 안 그러면 켜져 있는지도 모른다.

```bash
# 1) anthropic provider의 인자명을 body → text 로 임시 변경
# 2) mypy app/  → factory.py 에서 Incompatible return value type 이 떠야 정상
# 3) 되돌리기
```

이 확인을 거친 뒤에야 "CI가 Protocol 정합성을 지켜준다"고 말할 수 있다.

---

## 5. 면접 답변용

**Q. 타입 힌트를 이렇게 촘촘히 다셨는데 검사는 어떻게 하세요?**

> Protocol로 provider를 추상화했는데, Protocol은 상속을 쓰지 않으니 구현체가
> 인터페이스를 만족하는지 런타임에도 테스트에서도 확인되지 않습니다.
> 테스트는 비용 0을 위해 Fake만 주입하니까요.
> 그래서 mypy를 CI에 넣어 실행 없이 시그니처 정합성을 검증합니다.
> 설계로 얻은 유연성의 대가를 도구로 갚는 구조입니다.

**주의:** 도입 전에 이 답을 하면 거짓말이 된다. 도입 전이라면 이렇게:

> 아직 CI는 ruff와 pytest뿐입니다. Protocol을 쓰면 구현체 정합성을 아무도
> 검증하지 않는다는 구멍이 생기는데, 지금은 그게 열려 있는 상태입니다.
> mypy 도입이 다음 작업이고, 검사 지점은 각 factory의 반환 타입입니다.

**"모르고 안 넣은 것"과 "알고 아직 안 넣은 것"은 다르게 들린다.** 구멍의 위치를
정확히 짚을 수 있으면 후자로 들린다.

---

## 6. 체크리스트

- [ ] `pyproject.toml` dev 의존성 + `[tool.mypy]` 블록 추가
- [ ] `mypy app/` 로컬 실행 → 오류 목록 확보
- [ ] 오류 수정 (또는 `# type: ignore[코드]` 임시 봉인)
- [ ] `.github/workflows/ci.yml` 에 스텝 추가
- [ ] `CLAUDE.md` 명령어 섹션에 한 줄 추가
- [ ] **검증**: 일부러 시그니처를 깨서 mypy가 잡는지 확인
- [ ] 커밋: `chore(ci): add mypy static type check`

**커밋 메시지 본문 초안**

```
Protocol 기반 provider 추상화(절대규칙 1)는 상속이 없어 구현체가
인터페이스를 만족하는지 런타임·테스트 어디서도 검증되지 않는다.
테스트는 FakeProvider만 주입하므로 anthropic·ollama 구현체는
pytest에서 한 번도 실행되지 않는다. mypy를 CI에 넣어 실행 없이
시그니처 정합성을 검증한다.
```
