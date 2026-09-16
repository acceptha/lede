# 실습 노트 — 직접 돌려보고 눈으로 확인하기

> 개념은 [STUDY_NOTES.md](./STUDY_NOTES.md), 진도는 [STUDY_CURRICULUM.md](./STUDY_CURRICULUM.md).
> 이 문서는 **손으로 해보는 것만** 모았다. 읽어서 아는 것과 돌려봐서 아는 것은 다르다.
> 각 실습: **목표 → 명령 → 기대 결과 → 배우는 것**

환경: Windows / PowerShell. 파이썬은 `.venv\Scripts\python.exe`.
`docker-compose up`이 필요한 실습은 표시해둠.

---

## 1단계 실습

### 1-1. `await` 빼먹으면 무슨 일이 일어나나 (2분)

**목표:** `async def` 호출이 실행이 아니라는 것을 눈으로 본다.

```powershell
.venv\Scripts\python.exe -c @"
import asyncio
async def fetch(): 
    print('실행됨!')
    return 42
r = fetch()          # await 없이
print('반환값:', r)
"@
```

**기대 결과**
```
반환값: <coroutine object fetch at 0x...>
RuntimeWarning: coroutine 'fetch' was never awaited
```

**배우는 것:** `print('실행됨!')`이 **찍히지 않는다.** 함수 본문이 한 줄도 안 돌았다.
→ `async def` 호출은 **코루틴 객체(실행 계획서)만 반환**한다.

---

### 1-2. `*` 지우면 순서 뒤바뀜이 통과한다 (5분)

**목표:** 키워드 전용 인자가 막는 버그를 직접 만들어본다.

```powershell
.venv\Scripts\python.exe -c @"
def with_star(*, title: str, body: str):
    return f'제목={title[:10]} 본문={body[:10]}'
def without_star(title: str, body: str):
    return f'제목={title[:10]} 본문={body[:10]}'

t, b = '파이썬 비동기 입문', '오늘은 async에 대해 알아본다...'
print('올바름 :', without_star(t, b))
print('뒤바뀜 :', without_star(b, t))     # 에러 없이 통과!
try:
    with_star(b, t)
except TypeError as e:
    print('* 있음 :', type(e).__name__, e)
"@
```

**기대 결과:** `without_star(b, t)`는 **아무 에러 없이** 제목과 본문이 뒤바뀐 결과를 낸다.
`with_star`는 `TypeError`.

**배우는 것:** 같은 타입 인자의 순서 실수는 **파이썬도 mypy도 못 잡는다.**
`*` 한 글자가 그 버그를 언어 차원에서 봉쇄한다.

---

### 1-3. `zip`의 조용한 절단 (2분)

```powershell
.venv\Scripts\python.exe -c @"
rows = ['요약A', '요약B', '요약C']
vecs = [[0.1], [0.2]]                  # 하나 부족 (provider가 계약 위반)
print('strict 없음:', list(zip(rows, vecs)))
try:
    list(zip(rows, vecs, strict=True))
except ValueError as e:
    print('strict=True:', type(e).__name__, e)
"@
```

**기대 결과:** 앞은 `요약C`가 **조용히 사라진 결과**, 뒤는 `ValueError`.

**배우는 것:** 조용한 실패를 시끄러운 실패로 바꾸는 것이 `strict=True`의 목적.
없으면 그 글만 영원히 다이제스트에 안 뽑히고 **에러도 로그도 안 남는다.**

---

### 1-4. `async with`가 없으면 무엇이 깨지나 (3분)

```powershell
.venv\Scripts\python.exe -c @"
import asyncio, httpx
# ① 비동기 자원에 with를 쓰면?
try:
    with httpx.AsyncClient() as c: pass
except TypeError as e:
    print('with on AsyncClient:', e)

# ② __aexit__ 도중에 다른 코루틴이 도는가?
class Res:
    async def __aenter__(self): print('  enter'); return self
    async def __aexit__(self, *a):
        print('  cleanup start'); await asyncio.sleep(0.1); print('  cleanup done')
async def user():
    async with Res(): print('  working')
async def other():
    for i in range(3):
        await asyncio.sleep(0.04); print(f'  other tick {i}')
asyncio.run(asyncio.gather(user(), other()) if False else __import__('asyncio').gather)
"@
```

> 위 마지막 줄은 실행되지 않는 형태다. 아래처럼 파일로 저장해서 돌리는 편이 낫다:
> `python - < script.py` 또는 스크래치 파일 사용.

**기대 결과:** `with`는 `TypeError: 'AsyncClient' object does not support the context manager protocol`.
②는 `cleanup start` → `other tick 0/1` → `cleanup done` 순서 (정리 중에 양보!).

**배우는 것:** `async with`는 이름 차이가 아니라 **정리 중 양보 가능**이라는 실제 동작 차이.

---

## 2단계 실습 (async/await)

### 2-1. sync vs async 시간 비교 ★ (커리큘럼 권장, 10분)

**목표:** async의 이득이 **대기 시간 겹치기**임을 숫자로 본다.

스크래치 파일로 저장해서 실행:

```python
# bench.py
import asyncio, time, httpx, requests

URLS = [
    "https://uppity.co.kr/feed",
    "https://toss.tech/rss.xml",
    "https://d2.naver.com/d2.atom",
] * 3          # 9개 요청

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

def sync_run():
    t = time.perf_counter()
    for u in URLS:
        requests.get(u, headers=UA, timeout=15)
    return time.perf_counter() - t

async def async_seq():                      # for + await (현재 collect_feeds 방식)
    t = time.perf_counter()
    async with httpx.AsyncClient(headers=UA, timeout=15) as c:
        for u in URLS:
            await c.get(u)
    return time.perf_counter() - t

async def async_gather():                   # fan-out (TODO_FANOUT.md 방식)
    t = time.perf_counter()
    async with httpx.AsyncClient(headers=UA, timeout=15) as c:
        await asyncio.gather(*[c.get(u) for u in URLS])
    return time.perf_counter() - t

print(f"sync(requests)      : {sync_run():.2f}s")
print(f"async 순차(for+await): {asyncio.run(async_seq()):.2f}s")
print(f"async gather        : {asyncio.run(async_gather()):.2f}s")
```

**기대 결과** (네트워크 상황에 따라 다름)
```
sync(requests)      : 4.20s
async 순차(for+await): 4.10s     ← sync와 거의 같다!
async gather        : 0.70s     ← 여기서 이득
```

**배우는 것 (핵심)**
- **`async`만 붙여도 빨라지지 않는다.** `for` + `await`는 sync와 동작이 같다
- 이득은 **`gather`로 대기를 겹칠 때** 생긴다
- 그래서 현재 `collect_feeds`는 async지만 성능 이득이 없다 → [TODO_FANOUT.md](./TODO_FANOUT.md)

> `requests`가 없으면 `pip install requests`. 네트워크가 막혀 있으면 URL을 `httpbin.org/delay/1`
> 같은 것으로 바꾸거나, `asyncio.sleep`/`time.sleep`으로 대체해도 결론은 동일하다.

---

### 2-2. `time.sleep`이 이벤트 루프를 멈추는 것 보기 (5분)

```python
# block.py
import asyncio, time

async def worker(name, blocking):
    for i in range(3):
        if blocking:
            time.sleep(0.3)          # ❌ 루프 전체 정지
        else:
            await asyncio.sleep(0.3) # ✅ 양보
        print(f"  {name} step {i} @ {time.strftime('%H:%M:%S')}")

async def main(blocking):
    t = time.perf_counter()
    await asyncio.gather(worker("A", blocking), worker("B", blocking))
    print(f"총 {time.perf_counter()-t:.2f}s\n")

print("[asyncio.sleep — 양보함]");  asyncio.run(main(False))
print("[time.sleep — 블로킹]");     asyncio.run(main(True))
```

**기대 결과**
```
[asyncio.sleep] A와 B가 번갈아 출력, 총 0.9s
[time.sleep]    A가 3번 다 끝난 뒤 B 시작, 총 1.8s
```

**배우는 것:** 절대규칙 4("sync 블로킹 I/O 금지")가 존재하는 이유.
`async def` 안에 sync 함수 한 줄이 들어가면 **동시성이 전부 사라진다.**

---

### 2-3. `gather`는 완료 순인가 입력 순인가 (3분)

```python
# order.py
import asyncio

async def f(n, delay):
    await asyncio.sleep(delay)
    print(f"  완료: {n}")
    return f"결과{n}"

async def main():
    out = await asyncio.gather(f(1, 0.3), f(2, 0.1), f(3, 0.2))
    print("gather 반환:", out)

asyncio.run(main())
```

**기대 결과**
```
  완료: 2
  완료: 3
  완료: 1
gather 반환: ['결과1', '결과2', '결과3']     ← 입력 순서!
```

**배우는 것:** `gather`는 **입력 순서**를 보장한다 → `zip(sources, raws, strict=True)`가 안전한 이유.
완료 순으로 받으려면 `asyncio.as_completed`.

---

### 2-4. Redis에서 잡 상태 전이 관찰 ★ (docker 필요, 15분)

**목표:** `queued → in_progress → complete → not_found` 전이를 **키로** 확인한다.

터미널 1 — 스택 기동:
```powershell
docker-compose up
```

터미널 2 — Redis 감시:
```powershell
docker-compose exec redis redis-cli
```
```
127.0.0.1:6379> KEYS arq:*
```

터미널 3 — 잡 강제 실행 (스케줄 시각을 기다리지 않고):
```powershell
docker-compose exec worker python -c @"
import asyncio
from arq import create_pool
from arq.connections import RedisSettings
async def main():
    r = await create_pool(RedisSettings.from_dsn('redis://redis:6379/0'))
    job = await r.enqueue_job('run_pipeline')
    print('enqueued:', job.job_id)
asyncio.run(main())
"@
```

그다음 터미널 2에서 반복 조회:
```
KEYS arq:*
ZRANGE arq:queue 0 -1 WITHSCORES      # 큐에 든 잡 + 실행 예정 시각
TTL arq:in-progress:<job_id>          # 남은 락 시간 (1810부터 감소)
GET arq:retry:<job_id>                # 시도 횟수 = ctx["job_try"]
```

**기대 결과 (시점별)**

| 시점 | `KEYS arq:*` 결과 | 계산되는 상태 |
|---|---|---|
| 넣은 직후 | `arq:queue`, `arq:job:<id>` | `queued` |
| 실행 중 | + `arq:in-progress:<id>` | `in_progress` |
| 완료 | `arq:result:<id>` 만 | `complete` |
| 1시간 후 | (비어 있음) | `not_found` |

**배우는 것:** 상태는 **저장되지 않고 키 3개로 계산**된다. 아무도 상태를 "바꿔주지" 않는다.

---

### 2-5. 스케줄러에서 `Event().wait()`를 지워보기 (5분)

**목표:** 프로세스를 살려두는 장치가 없으면 스케줄러가 즉사하는 것을 본다.

`app/scheduler.py`의 마지막 줄을 임시로 주석 처리:
```python
    # await asyncio.Event().wait()  # 프로세스 유지
```
```powershell
docker-compose exec worker python -m app.scheduler
```

**기대 결과:** `scheduler started: daily run_pipeline at 08:00 Asia/Seoul` 로그를 찍고
**즉시 종료**된다. 에러 없이 조용히.

**배우는 것:** `scheduler.start()`는 타이머만 등록하고 반환한다.
`main()`이 끝나면 `asyncio.run`이 루프를 닫고 타이머도 함께 소멸한다.
→ **"켜졌다는 로그는 찍히는데 아무 일도 안 일어나는"** 가장 찾기 어려운 버그의 형태.

**끝나면 주석을 반드시 되돌린다.**

---

## 4·6단계 실습 (멱등성 · 실패 처리)

### 4-1. 멱등성 검증 — 두 번 돌려도 같은가 ★ (docker 필요, 15분)

**목표:** 성공 기준(DESIGN §9)의 "재요약 0회, 중복 발송 0회"를 직접 확인한다.

파이프라인을 **두 번** 실행하고 두 번째 결과를 비교한다 (2-4의 enqueue 명령 재사용).

```powershell
docker-compose exec postgres psql -U lede -d lede -c "SELECT count(*) FROM contents;"
docker-compose exec postgres psql -U lede -d lede -c "SELECT count(*) FROM summaries;"
docker-compose exec postgres psql -U lede -d lede -c "SELECT id, digest_date, status, sent_at FROM digests;"
```

**기대 결과**

| | 1회차 | 2회차 |
|---|---|---|
| `collect` | `new: N` | `new: 0, duplicate: N` |
| `summarize` | `summarized: N` | `summarized: 0` |
| `digest` | `status: sent` | `status: already_sent` |
| `digests` 행 수 | 1 | **1 (그대로)** |

**배우는 것:** 멱등성 3종 세트가 각각 어디서 막는지.
① `content_hash` UNIQUE ② `select_pending_contents`가 이미 요약된 것 제외
③ `digests(user_id, digest_date)` UNIQUE + `status == "sent"` 체크

---

### 6-1. dead-letter 관찰 — 일부러 실패시키기 ★ (커리큘럼 강력 추천, 20분)

**목표:** 실패 격리와 dead-letter park를 눈으로 본다.

`app/llm/providers/fake.py`를 임시 수정:

```python
import random
from app.llm.provider import LLMError

class FakeProvider:
    async def summarize(self, *, title: str, body: str) -> LLMSummary:
        self.call_count += 1
        if random.random() < 0.34:                     # 3번 중 1번 실패
            raise LLMError("의도적 실패 (실습)")
        ...
```

파이프라인을 3~4회 실행하고 매번 확인:

```powershell
docker-compose exec postgres psql -U lede -d lede -c "SELECT job_type, content_id, attempts, left(error,40) FROM dead_letters ORDER BY attempts DESC;"
```
또는 Swagger에서 `GET /dead-letters`.

**기대 결과**
- 1회차: 일부 콘텐츠가 `dead_letters`에 `attempts=1`로 기록되고, **나머지는 정상 요약됨** (실패 격리)
- 재실행: 실패했던 것만 다시 시도되어 `attempts`가 2, 3으로 증가
- `attempts >= 3`(`DEADLETTER_MAX_ATTEMPTS`): **park되어 더 이상 시도하지 않음**
- 파이프라인은 한 번도 멈추지 않는다

**배우는 것:** 절대규칙 5(실패 격리)와 무한 재시도 방지(park).
**끝나면 `fake.py`를 반드시 되돌린다** (`git checkout app/llm/providers/fake.py`).

---

### 6-2. `Retry` + `deferred` 상태 잡아보기 (15분)

**목표:** `Retry(defer=...)`가 Redis score를 미는 것을 확인한다.

`fake.py`가 `LLMRateLimitError`를 던지게 임시 수정:

```python
from app.llm.provider import LLMRateLimitError
...
raise LLMRateLimitError("429 (실습)")
```

실행 직후 Redis에서:
```
ZRANGE arq:queue 0 -1 WITHSCORES     # score가 미래 시각으로 밀렸는지
GET arq:retry:<job_id>               # 2, 3, 4로 증가
EXISTS arq:in-progress:<job_id>      # 0 — 대기 중엔 락을 놓는다!
TIME                                 # 지금 시각과 비교 → score가 크면 deferred
```

**배우는 것:** `sleep`으로 기다리지 않고 **자원을 놓고 큐에 순번을 맡기는** 것의 실체.
`full_jitter` 덕에 실행할 때마다 defer 값이 달라지는 것도 확인해볼 것.

**끝나면 되돌린다.**

---

## 3단계 실습 (FastAPI)

### 3-1. Swagger를 관리자 콘솔로 써보기 (docker 필요, 10분)

```
http://localhost:8000/docs
```

- `POST /interests` 로 관심사 등록 (`Python`, `도커`, `AI` 등)
- **대소문자·한글 별칭을 일부러 섞어 넣고** `GET /interests`로 정규화 결과 확인
  (`도커` → `docker` 로 바뀌는지)
- `GET /dead-letters` 로 실패 목록 조회

**배우는 것:** DESIGN §3-3 "관리자 페이지 대신 Swagger UI".
그리고 절대규칙 6(키워드 정규화)이 등록 시점에 적용되는 것.

---

## 8단계 실습 (점수 전략)

### 8-1. Jaccard ↔ 임베딩 전략 갈아끼우기 (docker + Ollama 필요, 20분)

`.env`에서:
```
SCORING_STRATEGY=jaccard      →  embedding
EMBEDDING_PROVIDER=fake       →  ollama
```

같은 콘텐츠·같은 관심사로 파이프라인을 돌리고 `digest_items.score`를 비교:

```powershell
docker-compose exec postgres psql -U lede -d lede -c "SELECT di.content_id, di.score, c.title FROM digest_items di JOIN contents c ON c.id=di.content_id ORDER BY di.score DESC;"
```

**기대 결과:** Jaccard는 0.0 / 0.11 / 0.25 처럼 **이산적**, 코사인은 0.4~0.9 사이 **연속적**.
Jaccard가 0점 준 글이 코사인에서는 뽑히는 경우가 있는지 확인.

**배우는 것:** `digest_items.score` 스냅샷이 존재하는 이유 — **전략 비교의 측정 데이터**.
DESIGN §5 실측(`AI↔인공지능` 0.828 vs Jaccard 0.0)을 내 데이터로 재현.

---

## mypy 실습

### M-1. Protocol 정합성이 실제로 잡히는지 (15분)

[TODO_MYPY.md](./TODO_MYPY.md)대로 mypy를 설치한 뒤:

1. `app/llm/providers/anthropic.py`의 `summarize` 인자명을 `body` → `text`로 임시 변경
2. `pytest` 실행 → **통과한다** (Fake만 쓰니까)
3. `mypy app/` 실행 → `factory.py`에서 `Incompatible return value type` 에러
4. 되돌린다

**배우는 것:** 테스트가 잡지 못하는 영역이 있고, mypy가 그 구멍을 메운다.
**"pytest 통과 = 안전"이 아니다.**

---

## 실습 원칙

1. **코드를 임시 수정하는 실습은 끝나고 반드시 되돌린다** — `git status`로 확인, `git checkout <파일>`로 복구
2. **기대 결과와 다르면 그게 더 좋은 공부다** — 왜 다른지 추적한다
3. **숫자를 기록한다** — 면접에서 "측정했습니다"라고 말할 근거가 된다 (예: 2-1의 초 단위 결과)
4. 실습 결과 중 특이한 것은 [STUDY_NOTES.md](./STUDY_NOTES.md) 오답 노트에 추가한다
