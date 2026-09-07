# 복습 노트 — lede

> 세션 기록. 짧게 유지한다. 상세 설명 대신 **다시 볼 것만.**
> 커리큘럼: [STUDY_CURRICULUM.md](./STUDY_CURRICULUM.md) · 면접: [INTERVIEW.md](./INTERVIEW.md) · 미도입: [TODO_MYPY.md](./TODO_MYPY.md)

---

## 진도

| 단계 | 상태 | 날짜 |
|---|---|---|
| 0 — 지도 그리기 | ✅ 완료 | 2026-09-07 |
| 1 — 현대 파이썬 문법 | ✅ 완료 | 2026-09-07 |
| 2 — async/await | ⬜ 다음 | |

---

## 0단계 — 지도

**프로젝트 전체 = `app/worker.py:243` 네 줄**

```python
async def run_pipeline(ctx: dict) -> dict:
    collected  = await collect_feeds(ctx)          # 수집  app/collect/
    summarized = await summarize_pending(ctx)      # 요약  app/summarize/ + app/llm/
    embedded   = await embed_pending(ctx)          # 임베딩 app/embedding/
    digested   = await build_and_send_digest(ctx)  # 발송  app/digest/ + app/email/
```

점수 = `app/scoring/` · 정규화 = `app/keywords.py` · 스케줄 = `app/scheduler.py` · API = `app/main.py`

테이블 9개: `users` `sources` `contents` `summaries` `user_interests` `user_events` `digests` `digest_items` `dead_letters`

> 면접에서 "구조 설명해주세요" → 이 4줄 + 각 줄마다 "여기서 실패하면?"

---

## 1단계 — 핵심 정리

### 타입 힌트

- 파이썬은 **검사하지 않는다**. 강제가 아니라 약속. 검사는 mypy의 몫
- 3.10+ 문법: `list[str]`, `str | None`, `list[tuple[int, float]]`
- **시그니처는 "입력 → 출력" 쌍으로 읽는다.** 중첩 깊이 변화가 함수의 역할:
  - 깊어짐 = 변환 (`list[str]` → `list[list[float]]`)
  - 얕아짐 = 집계 (`list[list[float]]` → `list[float]`)
  - 유지 = 필터·정렬
- `Mapped[X]`(SQLAlchemy 2.0)는 예외 — **여기선 타입이 실제 DDL을 만든다**
  (`Mapped[str]` → NOT NULL, `Mapped[datetime | None]` → NULL 허용)

### `| None` — 판별 질문: "값이 없는 상태가 정상인가?"

**쓰는 경우 5가지**
1. 외부가 안 줄 수 있음 — `published_at`(RSS가 pubDate 미제공), `nickname`
2. 아직 그 상태가 아님 — `sent_at`, `embedding`, `reading_time`
3. 찾았을 수도/못 찾았을 수도 — DB 조회 결과 (`User | None`) ← 실무에서 가장 많음
4. 구조적으로 해당 없음 — `DeadLetter.content_id` (잡 단위 실패)
5. 선택적 입력 — `FakeProvider(response=None)`

**쓰면 안 되는 경우**
- 도메인상 반드시 존재 — `title`, `content_hash`, `email`, `score`
- **컬렉션** — 리스트는 "없음"을 `[]`로 표현. `default_factory=list` 사용
  (`None`이면 `for k in keywords:`가 TypeError)

**의무 = 가드 절(guard clause)** — `if user is None: return ...` 로 위에서 쳐내고 본문은 평평하게

### `*` 키워드 전용 인자

```python
def f(*args)     # 임의 개수 수집
def f(*, a, b)   # 맨 별표 = 구분선. 뒤는 이름 필수. 받는 개수는 안 바뀜
def f(x, /, y, *, z)   # x=위치전용  y=둘다  z=키워드전용
```

- **왜:** `title`·`body`·`url`·`content_hash`가 전부 `str` → 순서 뒤바뀜을 파이썬도 mypy도 못 잡음
  (`url`↔`content_hash`가 바뀌면 UNIQUE가 URL 기준이 돼 **멱등성이 조용히 붕괴**)
- **대가 ①** 호출이 길어짐 → 인자 2개 이상 + 타입 겹칠 때만 쓴다
- **대가 ②** 인자 이름이 **공개 API**가 됨. "공개" = 실사용자 배포가 아니라
  **바꾸면 호출부가 깨진다**는 뜻. `*`가 이름을 "내부 구현"에서 "계약"으로 승격시킴

### 기타 문법

| 문법 | 뜻 |
|---|---|
| `...` (Protocol 본문) | 구현 없음 |
| `Field(...)` | Pydantic에서 **필수 값** (기본값 없음) |
| `default_factory=list` | 호출 때마다 새 리스트. `= []`는 모든 인스턴스가 공유하는 함정 |
| `@lru_cache` (`get_settings`) | 프로세스당 한 번만 생성 = 싱글턴 |
| 함수 안 `import` (factory) | lazy import — fake 경로에선 SDK를 아예 로드 안 함 |

### ★ 타입은 **모양**이지 **크기**가 아니다

"입력 N개면 출력도 N개"는 **타입으로 표현 불가.** `list[str]`은 0개도 100만 개도 같은 타입.

| | 무엇을 보나 | 개수 불일치 |
|---|---|---|
| mypy (실행 전) | 타입의 모양 | ❌ 불가능 |
| 런타임 코드 (`_parse_embeddings`) | 실제 값 | ✅ 여기가 잡음 |
| pytest | 그 코드가 제대로 잡는지 | 🔍 검증의 검증 |

### mypy와 Protocol

Protocol은 상속이 없어 **구현체 정합성을 아무도 검증하지 않는다.** 테스트는 Fake만 주입하므로
`AnthropicProvider`·`OllamaProvider`는 **pytest에서 한 번도 실행되지 않음.**
→ mypy가 그 구멍을 메운다. 검사 지점은 각 `factory.py`의 반환 타입. **이 레포는 아직 미도입.**

### `zip(strict=True)`

기본 `zip`은 **짧은 쪽에 맞춰 조용히 자른다** → 벡터 하나가 소리 없이 누락돼도 에러도 로그도 없음.
`strict=True`는 길이 불일치 시 `ValueError`. 발생 원인은 **provider가 "N개→N개" 계약을 어겼을 때**뿐.

**"예상된 실패는 삼키고, 계약 위반은 터뜨린다"** — `EmbeddingError`는 `continue`, `ValueError`는 전파.
데이터가 틀리는 것보다 멈추는 게 낫다.

### 자가 치유

```
ValueError → commit 도달 못 함 → 롤백 → embedding 은 여전히 NULL
→ 다음 실행의 select_needs_embedding() 이 다시 집어옴
```
**"아직 안 된 것"의 정의(`embedding IS NULL`)가 곧 재시도 큐.** 별도 플래그·재시도 목록 불필요.

### 임베딩

`embed` = 텍스트를 **의미 공간 좌표(1024차원)에 박아 넣는 것.** 그래야 "얼마나 가까운가"를 잴 수 있다.

| 쌍 | Jaccard | 코사인 |
|---|---|---|
| AI ↔ 인공지능 | 0.0 | **0.828** |
| 주식 ↔ 증시 | 0.0 | **0.757** |
| AI ↔ 떡볶이 | 0.0 | 0.452 |

표기 흔들림(`Docker`/`도커`)은 정규화가, 의미 동의어(`AI`/`인공지능`)는 임베딩이. **상보 관계.**

### 트레이드오프

> 하나를 얻으려면 하나를 내준다. **면접 정답 = 얻은 것 + 내준 것 + 메운 방법 (3단)**

| 결정 | 내준 것 | 메운 방법 |
|---|---|---|
| Protocol | 정합성 자동 검증 없음 | mypy (미도입) |
| Arq (vs Celery) | Flower 모니터링 UI | 구조화 로깅 + `dead_letters` 테이블 |
| RSS만 | 수집 소스 제한 | ToS 리스크 0으로 상쇄 |
| Jaccard | `AI↔인공지능` 못 잡음 | V3 임베딩 |
| 키워드 전용 인자 | 이름이 공개 API | 순서 버그 원천 차단으로 상쇄 |

---

## 오답 노트

| 내가 한 생각 | 실제 |
|---|---|
| 시그니처의 **반환 타입만** 읽음 | 입력→출력 쌍 + shape 변화까지 |
| `*`는 "아무 파라미터나 받겠다" | 그건 `*args`. 맨 `*`는 **구분선** |
| `*` 쓰면 모호해짐 | **반대.** 더 명확해짐 |
| 순서 뒤바뀜은 mypy가 잡음 | **못 잡음** (같은 타입끼리) |
| 개수(N) 일치를 mypy가 검사 | **불가능.** 타입에 길이 개념 없음 |
| `f(1,2)`는 "b가 없어서" 실패 | "**2를 놓을 자리가 없어서**" 먼저 실패 |
| 공개 API = 실사용자에게 공개 | **바꾸면 호출부가 깨진다**는 뜻 |

---

## 면접 답변 카드

**중복 차단** — "앱의 SELECT-후-INSERT가 아니라 DB UNIQUE 제약으로 걸었습니다. 앱에서 확인하면 동시 실행 시 레이스가 나는데, 제약은 DB가 원자적으로 막습니다."

**임베딩 근거** — "Jaccard가 `AI↔인공지능`에 0.0을 줬고 코사인은 0.828, 무관한 `AI↔떡볶이`는 0.452로 변별력이 있었습니다. 표기 변형은 정규화가, 의미 동의어는 임베딩이 담당합니다."

**타입 검사의 한계** — "'입력 N개면 출력 N개'는 타입으로 표현할 수 없어서, 진입점에 런타임 검증을 넣고 그 검증을 테스트로 고정했습니다."

**Protocol의 대가** — "Protocol은 상속이 없어 구현체 정합성이 런타임에도 테스트에서도 확인되지 않습니다. 테스트는 Fake만 주입하니까요. mypy를 CI에 넣는 게 그 짝인데, 지금은 그 구멍이 열려 있고 다음 작업입니다."

**조용한 실패 제거** — "`zip`은 짧은 쪽에 맞춰 조용히 자릅니다. 그러면 일부 글의 벡터가 소리 없이 누락되고 에러도 안 납니다. `strict=True`로 계약 위반을 즉시 예외로 만들었고, 이건 잡아서 무마하지 않고 잡을 실패시킵니다."

**자가 치유** — "실패 목록을 따로 관리하지 않고 '아직 안 된 것'의 정의(`embedding IS NULL`)가 곧 재시도 큐가 되게 했습니다."

---

## ★ "개선하고 싶은 점 있나요?" 답변 재료

> 면접 단골 질문. **자기 코드의 약점을 먼저 말하는 지원자는 강하게 기억된다** —
> 면접관은 "이 사람은 남의 코드도 이렇게 볼 수 있겠구나"로 읽는다.
> 형식: **무엇이 / 왜 지금은 괜찮고 / 언제 문제가 되며 / 어떻게 고칠지**

**① `embed_pending`의 커밋 타이밍**
> "`summarize_pending`은 재시도 전에 진행분을 커밋하는데(`worker.py:122`), `embed_pending`은 루프가 끝난 뒤 한 번만 커밋합니다. 중간 배치에서 실패하면 앞선 배치의 임베딩도 함께 롤백되죠. 임베딩은 로컬 Ollama라 비용이 0이어서 지금은 문제없지만, 유료 임베딩 API로 바꾸면 배치마다 커밋하도록 고쳐야 합니다."

**② mypy 미도입**
> "Protocol로 provider를 추상화했는데 정합성을 검증하는 도구가 없습니다. 테스트는 Fake만 주입해서 실제 provider는 한 번도 실행되지 않고요. CI에 `mypy app/`을 넣는 게 다음 작업입니다." → [TODO_MYPY.md](./TODO_MYPY.md)

**③ 점수 함수 관찰 트리거**
> "관심사가 많은 유저일수록 Jaccard 분모가 커져 점수가 깎이는 현상이 예상됩니다. `digest_items.score`에 선정 당시 점수를 스냅샷으로 남기고 있어서, 그게 측정되면 Tversky 비대칭형으로 전환할 계획입니다. 측정 전에 선제 도입은 하지 않았습니다." (DESIGN §5)

**④ 발송 시각·사용자 설정**
> "지금은 seed 유저 1명에 매일 08:00 고정입니다. 멀티유저가 되면 발송 시각을 사용자 설정으로 빼야 하고, SES도 샌드박스에서 프로덕션 액세스를 받아야 합니다." (DESIGN §8)

---

## 다음

- [ ] **2단계 async/await** — 이벤트 루프, `await`의 실체, I/O bound, `httpx.AsyncClient` 재사용, 블로킹 함정
- [ ] mypy 실제 도입 ([TODO_MYPY.md](./TODO_MYPY.md))
- [ ] `embed_pending` 배치별 commit 검토
