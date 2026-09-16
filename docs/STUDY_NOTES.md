# 복습 노트 — lede

> 세션 기록. 짧게 유지한다. 상세 설명 대신 **다시 볼 것만.**
> 커리큘럼: [STUDY_CURRICULUM.md](./STUDY_CURRICULUM.md) · 면접: [INTERVIEW.md](./INTERVIEW.md) · 미도입: [TODO_MYPY.md](./TODO_MYPY.md)

---

## 진도

| 단계 | 상태 | 날짜 |
|---|---|---|
| 0 — 지도 그리기 | ✅ 완료 | 2026-09-07 |
| 1 — 현대 파이썬 문법 | ✅ 완료 | 2026-09-07 |
| 2 — async/await | 🔄 진행 중 | 2026-09-07~ |

---

## ⚠️ 이 프로젝트에 "있는 것" / "없는 것"

> 학습 중 교과서 패턴을 여럿 접했다. **우리 코드에 있는 것과 없는 것을 섞으면 면접에서 위험하다.**
> 없는 패턴을 먼저 꺼내면 *"그럼 구현하셨어요?"* 가 오고 거기서 막힌다.
> **기본 원칙: 파일과 줄 번호를 댈 수 있는 것만 "했습니다"라고 말한다.**

| 개념 | 상태 | 근거 / 비고 |
|---|:---:|---|
| `Protocol` 기반 provider 추상화 | ✅ | `app/llm/provider.py`, `email/sender.py`, `embedding/provider.py` |
| 키워드 전용 인자 `*` | ✅ | 거의 모든 함수 |
| `async with` · `zip(strict=True)` | ✅ | `worker.py:235`, `SessionFactory()` 전반 |
| `content_hash` UNIQUE 중복 차단 | ✅ | `models.py:65` |
| `digests(user_id, digest_date)` UNIQUE | ✅ | `models.py:115` |
| `digests.status` pending→sent | ✅ | `models.py:120`, `worker.py:198` |
| dead-letter + park | ✅ | `models.py:139`, `worker.py:110` |
| `Retry(defer=full_jitter)` | ✅ | `worker.py:124`, `retry.py` |
| 임베딩 + pgvector 코사인 | ✅ | `app/embedding/`, `scoring/cosine.py` |
| Arq Redis 키·in-progress 락·JobStatus | ✅ | 라이브러리 내부 (`.venv/arq/`)에서 확인 |
| **mypy** | ❌ | 미도입 — [TODO_MYPY.md](./TODO_MYPY.md) |
| **fan-out/fan-in (`gather` 수집)** | ❌ | 미적용 — [TODO_FANOUT.md](./TODO_FANOUT.md) |
| **멱등성 키 (Idempotency-Key)** | ❌ | 교과서 패턴. **채택 안 함** — SES 미지원 |
| **Outbox 패턴** | ❌ | 교과서 패턴. **채택 안 함** — 테이블+워커 추가 비용 |
| **SES 실발송** | ❌ | `FakeEmailSender`만 존재. `factory.py:15`가 그 외를 `ValueError` |
| 가입/로그인/JWT · 크롤링 · 관리자 프론트 | ❌ | 스코프 가드 (CLAUDE.md) |

### 발송 멱등성 — 우리 코드의 실제

**막는 장치는 두 개뿐이다.**

| # | 장치 | 위치 | 막는 것 |
|---|---|---|---|
| 1 | `(user_id, digest_date)` UNIQUE | `models.py:115` | 같은 날 다이제스트 **행**의 중복 생성 |
| 2 | `if digest.status == "sent"` | `worker.py:198` | 이미 보낸 다이제스트의 **재발송** |

**남은 구멍:** `sender.send()` 성공(`worker.py:205`)과 `session.commit()`(`worker.py:213`) 사이에
프로세스가 죽으면 `status`가 `pending`으로 남아 재발송된다.
외부 호출은 DB 트랜잭션에 넣을 수 없는 구조적 한계 (at-least-once).
**지금은 sender가 fake라 실제 문제가 아니다** — SES를 붙일 때 다뤄야 할 지점.

> **면접에서 말할 범위:** 위 두 장치까지가 "했습니다".
> *"완벽한가요?"* 를 물으면 그때 밀리초 창을 언급한다.
> **Outbox·멱등성 키는 묻지 않으면 꺼내지 않는다.**

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

### 소스 조사 결과 — 9곳 조사, 3곳 채택 (`app/seed.py`)

**채택 기준: 본문 전문(full-text)이 오는가.** 요약 파이프라인은 본문이 없으면 의미가 없다.

| 소스 | RSS | 본문 | 판정 | 사유 |
|---|:---:|:---:|---|---|
| **어피티** `uppity.co.kr/feed` | ✅ | ✅ 전문 | **채택** | RSS 2.0 + `content:encoded` (경제) |
| **토스** `toss.tech/rss.xml` | ✅ | ✅ 전문 | **채택** | `content:encoded` ~8500자. **브라우저형 UA 필요** |
| **네이버 D2** `d2.naver.com/d2.atom` | ✅ | ✅ 전문 | **채택** | Atom, 본문 포함 |
| 우아한형제들 | ✅ | ✅ 전문 | 보류 | **Cloudflare JS 챌린지로 403** — 헤드리스 우회는 스코프 밖 |
| 카카오 | ✅ | ❌ 발췌 | 보류 | `description` ~280자만, `content:encoded` 없음 |
| 너겟 | ✅ | ❌ 없음 | 보류 | 전 항목 `<description>` 빈 태그 |
| 캐릿 · 순살브리핑 · 뉴닉 | ❌ | — | 보류 | 공개 RSS 없음 (표준 경로 전부 404) |

> **면접 포인트:** *"9곳을 조사해 3곳만 채택했습니다. 기준은 '본문 전문이 있는가'였고, RSS가 있어도 발췌만 주면 요약할 게 없어서 뺐습니다. Cloudflare로 막힌 곳은 헤드리스로 뚫을 수 있지만 ToS 리스크가 있어 스코프 밖으로 뒀습니다."* — **안 한 것에 이유가 있다**가 드러난다.
> 경제 뉴스레터는 대부분 full-text RSS를 안 줘서, 멀티소스 확장은 기술 블로그로 갔다.

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

## 2단계 — async/await

### 기본

- **async = 동시성(concurrency), 병렬성 아님.** 스레드 1개로 돈다. CPU를 더 쓰는 게 아니라 **대기 시간을 겹치는** 것
- I/O bound(네트워크·DB·LLM 대기)에만 이득. CPU bound는 async로 안 빨라짐 → 멀티프로세싱 영역
- `await` = **"기다리는 동안 다른 일 하러 가도 됨"** 선언. 제어권을 이벤트 루프에 반납
- **`async def` 호출은 실행이 아니다** — 코루틴 객체(실행 계획서)만 반환. `await`를 붙여야 실행됨.
  빠뜨리면 요청이 아예 안 나가고 `RuntimeWarning: coroutine was never awaited`만 뜬다

### 동시성을 넣을 곳 / 넣지 말 곳

**원칙: 공유 자원을 건드리지 않는 구간만 동시에 돌린다.**

| 구간 | 공유 자원 | 동시 가능 |
|---|---|---|
| `fetch_feed` (네트워크) | 없음 | ✅ |
| `parse_feed` (계산) | 없음 | (겹칠 이유 없음) |
| `sink.add_if_absent` (DB) | **세션 1개 = 커넥션 1개** | ❌ |

`AsyncSession`은 커넥션 1개를 감싼다 → 코루틴 둘이 동시에 쓰면
`InvalidRequestError: concurrent operations are not permitted`.
세션을 코루틴마다 만들면 **커넥션 풀 고갈** + 트랜잭션 분할 문제로 옮겨갈 뿐.

- `asyncio.gather`는 **입력 순서**로 결과를 돌려준다 (완료 순 아님. 완료 순은 `as_completed`)
- `gather(..., return_exceptions=True)`면 예외도 결과 배열에 담겨 와서 **실패 분류 가능**
- **`gather`는 서로 독립일 때만.** `run_pipeline`이 순차인 이유는 **데이터 의존성**
  (수집 결과를 요약이 읽고, 요약 결과를 임베딩·발송이 읽는다)

### `Retry` vs `sleep` — 자원을 쥐고 기다리지 않는다

| | 이벤트 루프 | DB 커넥션 | 워커 슬롯 | 워커 재시작 시 |
|---|---|---|---|---|
| `time.sleep(30)` | **전체 정지** | 점유 | 점유 | 소멸 |
| `asyncio.sleep(30)` | 정상 | **점유** | **점유** | **소멸** |
| `raise Retry(defer=...)` | 정상 | 반납 | 반납 | **Redis에 남아 생존** |

**`sleep`은 자원을 쥔 채 기다리는 것, `Retry`는 자원을 놓고 큐에 순번을 맡기는 것.**

동작 원리: Arq 큐 = Redis **sorted set**(score = 실행 예정 시각).
`Retry`를 받으면 잡을 큐에서 지우지 않고 `zincrby`로 score를 `defer`만큼 밀어
"그 시각 이후에 다시 꺼내라"가 된다. (`arq/worker.py:613-617`, `708`)

### `with` vs `async with` — 이름 차이가 아니다

**`with`의 정체 = `try/finally`의 축약.** "어떤 경로로 블록을 나가도 정리한다"를 보장.

```python
async with httpx.AsyncClient() as c:   # 이것과
    ...
# ↓ 완전히 동일
c = httpx.AsyncClient()
try:
    ...
finally:
    await c.aclose()
```

> ⚠️ **"마지막 줄에 `await aclose()` 쓰면 된다"는 동등하지 않다** — 예외가 나면 그 줄에 도달하지 못한다. `try/finally`라야 동등하고, `async with`는 그것을 **빠뜨릴 수 없게** 만든 형태.

| | `with` | `async with` |
|---|---|---|
| 호출 메서드 | `__enter__`/`__exit__` | `__aenter__`/`__aexit__` |
| 정리 함수 | 일반 함수 | **코루틴** |
| 정리 중 양보 | ❌ 불가 | ✅ **가능** (실측 확인) |
| 쓸 수 있는 곳 | 어디서나 | `async def` 안에서만 |
| 잘못 쓰면 | — | `TypeError: does not support the context manager protocol` |

**정리 작업이 I/O일 수 있다**는 게 진짜 차이. `AsyncSession.__aexit__`는 미커밋 트랜잭션에
**ROLLBACK을 DB로 전송**하고 응답을 기다린다(= `await`) → 그동안 다른 코루틴이 돈다.

**왜 async 자원은 `async with`가 필수인가**

| | 깜빡 잊었을 때 |
|---|---|
| 동기 파일 | GC가 `__del__` → `close()` **자동 구제** |
| 비동기 클라이언트 | 정리가 코루틴 → **GC는 `await`를 할 수 없음** → **누수 확정** |

### 자원 고갈 — FD와 메모리는 다른 것

| | 메모리 | 파일 디스크립터(FD) |
|---|---|---|
| 정체 | 데이터를 담는 **공간**(바이트) | 커널이 열어준 것을 가리키는 **번호표**(정수) |
| 한도 | 물리 RAM | **프로세스당 개수** (`ulimit -n`, 보통 1024) |
| 관리 | GC가 대체로 알아서 | **직접 닫아야 함** |

클라이언트 객체는 몇 KB라 **메모리보다 FD가 먼저 고갈된다.**

| | Too many open files | OOM |
|---|---|---|
| 원인 | FD **개수** 초과 | 메모리 **용량** 초과 |
| 파이썬에서 | `OSError: [Errno 24]` | **아무것도 안 옴** |
| 예외로 잡히나 | ✅ | ❌ (`SIGKILL`) |
| 프로세스 | 살아 있음 | **즉사** — `finally`·`shutdown()`도 안 돎 |
| 로그 | 스택트레이스 | **없음.** 도커 `exit 137` |

→ FD 초과는 **시끄러운 실패**, OOM은 **조용한 실패**.
OOM으로 워커가 죽으면 `aclose()`도 롤백도 안 되고, Arq 잡은 in-progress로 남아 TTL 만료 후 재시도된다.

### Arq의 Redis 구조 (라이브러리 내부 — 우리가 정한 게 아니다)

```
arq:queue              ZSET.  score = 실행 예정 시각(ms)
arq:job:<id>           잡 정의(함수명·인자). TTL 기본 1일
arq:in-progress:<id>   처리 중 락. TTL = job_timeout + 10 = 1810초
arq:result:<id>        실행 결과
arq:retry:<id>         시도 횟수 ← ctx["job_try"]의 출처 (워커 재시작에도 유지)
arq:abort              취소 요청 집합
```

**in-progress 키 = 분산 락.** 값은 `b'1'`로 무의미, **존재 여부**만 본다.
워커는 잡을 집을 때 `watch`+`exists`로 확인하고 `psetex`로 찜한다 → 먼저 만든 워커가 주인.
(`worker.py:450-465`. 낙관적 잠금이라 워커 여러 대가 동시에 시도해도 하나만 성공)

**JobStatus는 저장되지 않고 키 3개로 계산된다** (`arq/jobs.py:152`)

| result 키 | in-progress 키 | 큐 score | 상태 |
|:---:|:---:|:---:|---|
| 있음 | — | — | `complete` |
| 없음 | 있음 | — | `in_progress` |
| 없음 | 없음 | **미래** | `deferred` ← `Retry(defer=...)`가 만드는 상태 |
| 없음 | 없음 | **과거** | `queued` |
| 없음 | 없음 | 없음 | `not_found` |

> **워커가 죽으면?** in-progress 키만 TTL로 사라지고 **잡은 큐 ZSET에 그대로 남아 있다**
> (`zrem`은 정상 완료 시에만 실행). 따라서 `not_found`가 아니라 **`queued`가 되어 재실행된다.**

### 큐의 상태 ≠ 도메인의 상태

| | 관리 주체 | 저장 위치 | 목적 | 값 |
|---|---|---|---|---|
| `JobStatus` | Arq | Redis (키 조합, **만료됨**) | 잡 실행 상태 | deferred/queued/in_progress/complete/not_found |
| `digests.status` | **우리 코드** | PostgreSQL (**영구**) | **발송 멱등성** | `pending` → `sent` (둘뿐) |

Redis 결과 키는 만료되므로 *"어제 보냈나?"*를 물을 수 없다.
**영구히 남아야 할 사실은 DB에 쓴다** → `digests(user_id, digest_date)` UNIQUE + status 전이.

> Redis의 잡 상태를 도메인 진실로 믿은 시스템은 Redis를 비우면 중복 발송을 한다.

### 실수를 문법으로 막는 패턴 (이 프로젝트가 반복하는 것)

| 문법 | 사람이 실수할 수 있는 것 | 언어로 막은 방법 |
|---|---|---|
| `*` (키워드 전용) | 같은 타입 인자의 순서 뒤바뀜 | 이름을 강제 |
| `async with` | `try/finally` 누락 | 정리를 블록에 예약 |
| `zip(strict=True)` | 길이 불일치를 조용히 넘김 | 예외로 승격 |

→ "코드 품질을 어떻게 지켰나요?"에 대한 답이 이 셋.

### 프로세스와 이벤트 루프 — 루프는 프로세스당 하나

```
컨테이너: app     ├ uvicorn app.main:app          루프 1 (상시)  ← FastAPI
컨테이너: worker  ├ alembic upgrade head          루프 없음 (sync, 부팅 1회)
                  ├ python -m app.seed            루프 1 → 끝나면 소멸 (부팅 1회)
                  ├ python -m app.scheduler &     루프 1 (상시)  ← asyncio.run
                  └ exec arq WorkerSettings       루프 1 (상시)  ← arq CLI가 생성
```

**상시 루프 3개. 서로 메모리를 공유하지 않고 Redis로만 통신한다.**
`scheduler.py:27`은 함수가 아니라 `"run_pipeline"` **문자열**만 enqueue하고,
`app.worker`를 import하지도 않는다. 워커는 `WorkerSettings.functions`에서 이름으로 찾아 실행.

**`asyncio.run`이 있는 곳 / 없는 곳**

| 모듈 | 진입점 | 루프를 만드는 주체 | 제공하는 것 |
|---|---|---|---|
| `main.py` | `uvicorn app.main:app` | **uvicorn** | `app` 객체 |
| `worker.py` | `arq app.worker.WorkerSettings` | **arq CLI** | `WorkerSettings` (설정 명세서) |
| `scheduler.py` | `python -m app.scheduler` | **우리** | — |
| `seed.py` | `python -m app.seed` | **우리** | — |

→ **프레임워크가 진입점을 제공하면 루프도 프레임워크가 만든다.**
그래서 `worker.py`에는 `__main__` 블록도 `asyncio.run`도 없다.

### `exec`가 정상 종료를 보장한다 (`docker-compose.yml:60`)

```sh
exec arq app.worker.WorkerSettings
```

`exec`는 프로세스를 새로 만들지 않고 **쉘의 내용물을 arq로 교체**한다 (PID 유지).

| | `exec` 있음 | `exec` 없음 |
|---|---|---|
| PID 1 | **arq** | sh (arq는 자식) |
| `docker stop` 시 | arq가 **SIGTERM** 직접 수신 | sh만 죽음 → PID 1 소멸 → 나머지 **SIGKILL** |
| `on_shutdown` / `aclose()` | ✅ 실행 | ❌ 안 됨 (FD 누수) |
| 처리 중이던 잡 | 깔끔히 반납 | in-progress 락이 **1810초 방치** |

> 둘 다 죽지만 **"인사하고 죽느냐, 뒤통수 맞고 죽느냐"** 의 차이.

### 스케줄러는 폴링하지 않는다 (`apscheduler/schedulers/asyncio.py:56-70`)

```python
def _start_timer(self, wait_seconds):
    self._timeout = self._eventloop.call_later(wait_seconds, self.wakeup)   # 예약
def wakeup(self):
    wait_seconds = self._process_jobs()     # 실행 + "다음까지 몇 초?" 계산
    self._start_timer(wait_seconds)         # 다시 예약  ← 스스로 재예약하는 연쇄
```

- `CronTrigger`가 **다음 발화 시각**을 계산 → **남은 초**(절대 시각 아님)로 변환 → `call_later`
- 시각 확인의 실체는 **이벤트 루프**: 가장 이른 마감을 OS에 넘기고(epoll 타임아웃) **잠든다** → 대기 중 CPU 0%
- `await asyncio.Event().wait()`(`scheduler.py:47`)는 시각과 무관 — **프로세스를 살려두는 장치**.
  없으면 `main()` 종료 → `asyncio.run`이 루프를 닫음 → 예약된 타이머까지 소멸
  → **"켜졌다는 로그는 찍히는데 아무 일도 안 일어나는"** 버그

### 이 프로젝트에서 async가 실제로 이득인 지점 (정직하게)

현재 규모(소스 3개, 유저 1명, 하루 잡 1개)에서는 **성능 이득이 거의 없다.**
큐에 `run_pipeline` 하나만 들어가고 그 안은 전부 순차이기 때문.

**진짜 채택 이유는 성능이 아니라 일관성:** API·워커·HTTP·DB를 전부 async로 통일해
`asyncio.run()`·`run_in_executor` 같은 **async↔sync 경계 코드가 아예 없다** (DESIGN §2).
이득이 실현되는 지점은 → 피드 fan-out, 잡 여러 개 동시 실행(`max_jobs=10`), 멀티유저 발송.

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
| `async def` 호출하면 실행됨 | **코루틴 객체만 반환.** 요청조차 안 나감 |
| `await` 없이 부르면 응답까지 멈춤 | 멈추지도 않음. **아무 일도 안 일어남** |
| `gather`는 완료 순으로 결과를 줌 | **입력 순서** 보장 (완료 순은 `as_completed`) |
| `async def`면 자동으로 동시 실행 | `for` + `await`는 **순차**. 동시성은 `gather`로 명시해야 생김 |
| `gather` 못 쓰는 이유 = 실패 분류 | `return_exceptions=True`로 가능. 진짜 이유는 **세션 공유** |
| `self._base_url` = 서버 자신에게 보냄 | `self`는 **객체 자신**(파이썬 문법). 로컬인 건 값이 `localhost`여서 |
| `async with`는 비동기 함수를 만든다 | **`try/finally`의 축약.** 정리를 보장하는 문법 |
| `with`/`async with`는 이름 차이만 | **정리 중 양보 가능 여부**가 실제로 다름 |
| 마지막 줄에 `aclose()` 쓰면 됨 | 예외 시 **도달 못 함**. `try/finally`라야 동등 |
| 워커가 죽으면 잡이 `not_found` | in-progress 키만 만료. 잡은 큐에 남아 **`queued`로 재실행** |
| 잡 상태를 우리가 정의했다 | Arq가 정의하고 **키 조합으로 계산**. 우리 것은 `digests.status`뿐 |
| 스케줄러가 워커를 실행한다 | **별개 프로세스.** Redis로만 통신, 문자열만 전달 |
| `Event().wait()`가 루프를 만든다 | 루프는 `asyncio.run`이 만듦. 이건 **프로세스를 살려둘 뿐** |
| 스케줄러가 주기적으로 시각을 확인 | **폴링 없음.** `call_later` 예약 + 이벤트 루프가 OS에 맡기고 잠듦 |
| `exec` 없으면 arq가 살아남는다 | 같이 죽되 **SIGKILL로 즉사** — 정리 코드가 안 돎 |
| 멱등성 키·Outbox가 우리 코드에 있다 | **없음.** 교과서 패턴. 위 "있는 것/없는 것" 표 참조 |

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

**⑤ 피드 수집 fan-out (동시 수집)**
> "현재 피드 수집은 `for` + `await`라 순차입니다. 소스가 3개뿐이라 실익이 1초 수준이어서인데, 늘어나면 `fetch_feed`만 `asyncio.gather`로 묶고 DB INSERT는 순차로 유지하는 fan-out/fan-in으로 바꿀 수 있습니다. `AsyncSession`은 커넥션 1개라 동시 사용이 안 되지만 네트워크 구간은 공유 자원이 없거든요. `fetch`·`parse`·`sink`가 이미 분리돼 있어서 구조 변경 없이 가능하고, 실패 분류는 `return_exceptions=True`로 합니다. 대가는 모든 피드 바이트를 동시에 메모리에 들고 있어야 한다는 것과, 같은 호스트에 몰릴 경우 `Semaphore`로 동시 개수를 제한해야 한다는 점입니다."

**④ 발송 시각·사용자 설정**
> "지금은 seed 유저 1명에 매일 08:00 고정입니다. 멀티유저가 되면 발송 시각을 사용자 설정으로 빼야 하고, SES도 샌드박스에서 프로덕션 액세스를 받아야 합니다." (DESIGN §8)

---

## 다음

- [ ] **2단계 마무리 실습** — sync vs async 시간 비교 ([PRACTICE.md](./PRACTICE.md) 2-1)
- [ ] **3단계 FastAPI** — `main.py` → `router.py` → `schema.py`, `Depends` 의존성 주입
- [ ] mypy 실제 도입 ([TODO_MYPY.md](./TODO_MYPY.md))
- [ ] `embed_pending` 배치별 commit 검토
