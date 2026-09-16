# TODO — 피드 수집 fan-out (동시 수집)

> 상태: **미적용** (2026-09 기준). 현재 `collect_feeds`는 `for` + `await` 순차 수집.
> 성격: 성능 개선. **지금은 실익이 없어 미룬 것** — mypy(미완성 항목)와 성격이 다르다.
> 관련: CLAUDE.md 절대규칙 4·5, DESIGN.md §2 · §5

---

## 1. 현재 구조

```python
# app/worker.py:69-86
async with SessionFactory() as session:
    sources = (await session.execute(select(Source))).scalars().all()
    sink = SqlContentSink(session)
    for src in sources:
        try:
            result = await collect_source(source_id=src.id, feed_url=src.source_url,
                                          fetch=fetch, sink=sink)
        except httpx.HTTPError as exc:
            failures.append(f"{src.source_url}: {exc!r}")
    await session.commit()
```

`for` + `await`는 **순차**다. 피드 1번이 끝나야 2번이 시작된다.
소스 N개 × 응답 0.5초 = **0.5N초**.

---

## 2. 왜 그냥 `gather`로 감쌀 수 없나 — `AsyncSession` 제약

```python
# ❌ 이렇게 하면 깨진다
await asyncio.gather(*[collect_source(..., sink=sink) for s in sources])
```

`AsyncSession` 하나 = **DB 커넥션 하나 = 한 번에 쿼리 하나**.
`collect_source` 안에서 `sink.add_if_absent()`가 같은 세션을 쓰므로,
두 코루틴이 동시에 INSERT하면:

```
sqlalchemy.exc.InvalidRequestError:
    This session is provisioning a new connection; concurrent operations are not permitted
```

**코루틴마다 세션을 새로 만드는 것도 답이 아니다** — 세션 = 커넥션이라
소스 50개면 커넥션 50개를 동시에 요구해 **풀이 고갈**된다. 트랜잭션도 쪼개진다.

---

## 3. 해법 — fan-out / fan-in

**원칙: 공유 자원을 건드리지 않는 구간만 동시에 돌린다.**

| 구간 | 공유 자원 | 동시 가능 |
|---|---|---|
| `fetch_feed` (네트워크) | 없음 | ✅ **여기만 동시화** |
| `parse_feed` (순수 계산) | 없음 | 겹칠 이유 없음 (CPU라 이득 없음) |
| `sink.add_if_absent` (DB) | 세션 1개 | ❌ 순차 유지 |

`app/collect/rss.py`가 이미 `fetch_feed`(async, 네트워크만)와 `parse_feed`(sync, 계산만)를
분리해뒀기 때문에 **구조 변경 없이 가능하다.**

### 적용 후 형태 (초안)

```python
async def collect_feeds(ctx: dict) -> dict:
    job_try: int = ctx.get("job_try", 1)
    client: httpx.AsyncClient = ctx["http_client"]
    summary = {"sources": 0, "new": 0, "duplicate": 0, "failed": 0}
    failures: list[str] = []

    async with SessionFactory() as session:
        sources = (await session.execute(select(Source))).scalars().all()

        # ① fan-out — 네트워크만 동시에 (DB 미접근)
        sem = asyncio.Semaphore(MAX_CONCURRENT_FETCH)

        async def fetch_one(url: str) -> bytes:
            async with sem:                       # 동시 개수 제한
                return await fetch_feed(url, client)

        raws = await asyncio.gather(
            *[fetch_one(s.source_url) for s in sources],
            return_exceptions=True,               # 실패해도 나머지 계속
        )

        # ② fan-in — DB는 순차 (세션 하나, 트랜잭션 하나)
        sink = SqlContentSink(session)
        for src, raw in zip(sources, raws, strict=True):   # gather는 입력 순서 보장
            if isinstance(raw, Exception):
                failures.append(f"{src.source_url}: {raw!r}")
                continue
            for entry in parse_feed(raw):
                inserted = await sink.add_if_absent(
                    source_id=src.id, title=entry.title, body=entry.body,
                    url=entry.url, published_at=entry.published_at,
                    content_hash=compute_content_hash(entry.body),
                )
                summary["new" if inserted else "duplicate"] += 1
            summary["sources"] += 1
        await session.commit()

    summary["failed"] = len(failures)
    if failures and job_try < MAX_TRIES:
        raise Retry(defer=deterministic_backoff(job_try))
    return summary
```

**핵심 세 가지**
- `return_exceptions=True` — 예외가 결과 배열에 담겨 와서 **소스별 실패 분류가 그대로 유지**된다 (절대규칙 5)
- `zip(..., strict=True)` — `gather`는 **입력 순서**로 결과를 돌려주므로 `sources`와 1:1 대응이 보장된다. 어긋나면 즉시 예외
- `Semaphore` — 동시 요청 수 상한. 같은 호스트에 몰리는 것과 커넥션 폭주를 막는다

---

## 4. 대가 (트레이드오프)

| 대가 | 설명 | 완화 |
|---|---|---|
| **메모리** | 모든 피드 바이트를 동시에 보유. 소스 3개면 무시, 500개면 문제 | `Semaphore` + 필요 시 청크 단위 처리 |
| **상대 서버 부하** | 같은 호스트의 피드가 여럿이면 동시 요청이 몰림 | `Semaphore`, 호스트별 제한 |
| **코드 복잡도** | `isinstance(raw, Exception)` 분기 추가 | 불가피 |
| **`collect_source` 사용처 변화** | 현재는 fetch+parse+sink를 한 함수가 조립. fan-out 시 fetch가 밖으로 나옴 | `collect_source`를 유지하려면 `raw`를 받는 형태로 시그니처 변경 필요 |

> 마지막 항목이 실제 작업의 대부분이다. `collect_source(fetch=, sink=)`의
> 의존성 주입 형태를 유지할지, `collect_entries(raw, sink)`로 쪼갤지 결정해야 한다.

---

## 5. 언제 적용하나 (전환 조건)

**지금은 하지 않는다.** 소스 3개 × 0.5초 = 1.5초 → 0.5초, **1초 절약**.
하루 1회 도는 배치이고, 뒤따르는 LLM 요약이 건당 수십 초라 무의미하다
(`job_timeout = 1800`이 그 증거).

**적용 트리거 — 아래 중 하나가 관측되면:**
- 소스가 **10개 이상**으로 늘어남
- `collect_feeds` 소요 시간이 파이프라인 전체에서 유의미한 비중을 차지
- 수집 주기가 하루 1회 → 시간당으로 짧아짐

> DESIGN §5의 "측정 후에만 승급" 원칙과 같다. 측정 전 선제 최적화는 하지 않는다.

---

## 6. 선행 작업 ⚠️

**`collect_feeds`에는 현재 단위 테스트가 없다.** (`tests/test_pipeline.py`는 이 함수를
monkeypatch로 가짜 대체할 뿐이고, 내부 로직을 검증하지 않는다.)

리팩터링 전에 테스트를 먼저 붙인다 — **테스트 없이 동시성 코드를 고치면 안 된다.**

- [ ] `collect_feeds` 단위 테스트 추가 (가짜 fetch + 가짜 sink)
  - 소스 3개 중 1개가 `httpx.HTTPError`를 던져도 나머지 2개가 수집되는가 (실패 격리)
  - `failed` 카운트가 맞는가
  - 재실행 시 `duplicate`로 세는가 (멱등성)
- [ ] 그다음 fan-out 적용, 위 테스트가 그대로 통과하는지 확인

---

## 7. 체크리스트

- [ ] `collect_feeds` 단위 테스트 선행 작성
- [ ] `MAX_CONCURRENT_FETCH` 상수 추가 (`app/worker.py`)
- [ ] `collect_source` 시그니처 결정 (fetch 분리 여부)
- [ ] fan-out/fan-in 적용
- [ ] 테스트 통과 확인 (`pytest -x -q tests/test_pipeline.py`)
- [ ] `ruff check . && pytest` 후 커밋

**커밋 메시지 초안**

```
perf(collector): fetch feeds concurrently, keep DB writes serial

AsyncSession은 커넥션 1개를 감싸므로 여러 코루틴이 동시에 INSERT하면
concurrent operations 예외가 난다. 네트워크 구간(fetch_feed)만
asyncio.gather로 묶고 DB 쓰기는 순차로 유지한다(fan-out/fan-in).
소스별 실패 격리는 return_exceptions=True로 보존한다 (DESIGN §5).
```

---

## 8. 면접 답변용

**Q. async를 쓰셨는데 어디를 동시에 돌리셨나요?**

> 지금은 어디도 동시에 돌지 않습니다. 소스 3개, 유저 1명, 하루 잡 1개라 실익이 없어서
> 순차로 뒀습니다. 동시화할 지점은 정해뒀습니다 — `fetch_feed`만 `gather`로 묶고
> DB 쓰기는 순차로 유지하는 fan-out/fan-in입니다. `AsyncSession`은 커넥션 1개라
> 동시 사용이 안 되지만 네트워크 구간은 공유 자원이 없거든요.
> `fetch`·`parse`·`sink`를 처음부터 분리해둬서 구조 변경 없이 가능합니다.

**포인트:** "안 했다"가 아니라 **"안 한 이유와 할 방법을 안다"**로 들리게 한다.
동시성을 무조건 넣는 사람은 위 §2의 세션 예외를 운영에서 만난다.
