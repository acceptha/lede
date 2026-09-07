# 학습 커리큘럼 — lede 코드베이스 완전 정복

> 목적: 기획·설계는 내 머리에서 나왔지만 코드는 Claude가 작성했다.
> 이 문서는 코드에 들어간 개발 요소·스킬을 단계별로 학습해 "내 것"으로 만들기 위한 커리큘럼이다.
> 기간: 약 6~8주 (단계당 0.5~1.5주)

## 학습 방법 (모든 단계 공통)

각 단계는 세 스텝으로 진행한다:

1. **개념 학습** — 해당 주제를 외부 자료로 공부
2. **파일 정독** — 이 레포의 실제 파일을 한 줄씩 읽으며 "왜 이렇게 썼는지" 설명해보기
3. **검증 실습** — 파일을 지우고 `tests/`만 보며 재구현 (pytest 통과 = 졸업)

> 클로드가 짠 코드를 내 것으로 만드는 가장 확실한 방법은 **빈 화면 재구현**이다.
> 테스트가 전부 갖춰져 있어서 가능한 공부법이다.

---

## 0단계 — 지도 그리기 (반나절)

설계 문서의 각 문장이 코드 어디에 사는지 연결한다.

- [x] DESIGN.md §4 다이어그램 ↔ `app/` 디렉터리 매핑
  - 수집 = `app/collect/` · 요약 = `app/summarize/` + `app/llm/`
  - 점수 = `app/scoring/` · 발송 = `app/digest/` + `app/email/`
- [x] `app/worker.py`의 `run_pipeline()` 읽기 — 파이프라인 전체가 4줄로 요약됨

---

## 1단계 — 현대 파이썬 문법 (1주)

이 코드의 파이썬은 "학원 파이썬"과 다르다. 여기서 막히면 뒤가 전부 안 읽힌다.

- [x] 타입 힌트 — `list[tuple[int, float]]`, `str | None` (3.10+ 문법)
- [x] **`Protocol` (구조적 타이핑)** — `app/llm/provider.py`(22줄)가 교과서.
      절대규칙 1("파이프라인은 인터페이스만 안다")이 이 파일 하나로 구현됨.
      ABC 상속 대신 Protocol을 쓴 이유 조사 (구현체가 인터페이스를 import조차 안 해도 됨)
- [x] 예외 계층 설계 — `LLMError` ← `LLMRateLimitError` 상속.
      왜 429만 분리했는지는 6단계의 복선
- [x] Pydantic v2 — `app/config.py`(pydantic-settings, 환경변수→설정 객체),
      `app/llm/schema.py`(LLM JSON 출력 검증)

**검증 질문**: Protocol과 ABC의 차이는? FakeProvider가 LLMProvider를 상속하지
않는데 왜 타입 체크를 통과하나?

---

## 2단계 — async/await (1주, 가장 중요한 기초)

이 프로젝트의 정체성. 절대규칙 4("sync 블로킹 I/O 금지")가 존재하는 이유를 이해한다.

- [ ] 이벤트 루프, 코루틴, `await`의 실체
      (직관: **await = "기다리는 동안 다른 일 하러 가도 됨" 선언**)
- [ ] I/O bound vs CPU bound — RSS/LLM/메일이 전부 I/O bound라 async가 유리한 이유
- [ ] `httpx.AsyncClient` — `app/collect/rss.py`.
      클라이언트를 워커 startup에서 한 번 만들어 재사용하는 이유 (커넥션 풀)
- [ ] 함정 학습 — async 함수 안에서 `requests`나 `time.sleep()`을 쓰면 생기는 일
      (이벤트 루프 블로킹)

**실습**: 같은 URL 10개를 sync(requests)와 async(httpx)로 받아 시간 비교 스크립트 작성.

---

## 3단계 — FastAPI + API 레이어 (0.5~1주)

이 프로젝트의 API는 의도적으로 얇다 (무거운 일은 전부 워커로). 그래서 입문용으로 좋다.

**왜 FastAPI인가** (면접 답변 골격):
1. `async def` 네이티브 — I/O bound 파이프라인과 궁합
2. Pydantic 요청/응답 검증 자동
3. Swagger UI 공짜 — 관리자 프론트 대신 `/docs` 사용 (DESIGN §3-3)
4. 워커(Arq)까지 async 통일 → 코드 전체가 하나의 멘탈 모델 (Celery 기각 사유와 동일)

- [ ] `app/main.py`(30줄) → `app/interests/router.py` → `app/interests/schema.py` 정독
- [ ] 라우터 분리(`include_router`), Pydantic 스키마, 자동 Swagger
- [ ] `Depends` 의존성 주입 — DB 세션 주입 방식 확인
- [ ] "왜 API가 수집·요약을 직접 안 하나?" → DESIGN §2 역할 분리를 코드로 확인

**실습**: `docker-compose up` 후 `/docs`에서 관심사 CRUD를 직접 조작.
새 엔드포인트(예: 다이제스트 조회) 하나를 직접 추가.

---

## 4단계 — DB 레이어: SQLAlchemy 2.0 async + Alembic + Repository 패턴 (1~1.5주)

- [ ] SQLAlchemy 2.0 스타일 — `select()`, `session.execute`, `scalars()`.
      구식 `session.query()`와 다름. 튜토리얼도 2.0 기준으로 볼 것
- [ ] async 세션 — `app/db/base.py`, `app/db/session.py`. 드라이버가 asyncpg인 이유
- [ ] **Repository 패턴** — `app/*/repository.py` 전부 이 패턴.
      "SQL은 repository에만, 서비스 로직은 SQL을 모른다."
      분리 이유: 테스트에서 repository만 가짜로 교체 가능
- [ ] Alembic — `alembic/versions/`를 시간순으로 읽으면 스키마 변천사가 보임.
      `autogenerate`가 해주는 것과 못 해주는 것
- [ ] **DB 제약으로 지키는 무결성** — `digests(user_id, digest_date)` UNIQUE.
      중복 방지를 앱 코드가 아닌 DB 제약으로 거는 이유 (동시 실행 레이스에도 안전)

**검증 질문**: 파이프라인이 동시에 두 번 실행되면 다이제스트가 두 통 발송되나?
어느 줄이 막나? (답: DB UNIQUE 제약 + `worker.py`의 status "sent" 체크)

---

## 5단계 — 백그라운드 작업: Redis + Arq + APScheduler (1주)

포트폴리오의 몸통. `app/worker.py`를 한 줄씩 정독하는 단계.

- [ ] 작업 큐가 필요한 이유 — "API는 즉시 응답, 무거운 일은 워커로".
      큐가 없으면 뭐가 문제인지부터
- [ ] Redis의 이중 역할 — Arq 작업 큐 브로커 + 캐시
- [ ] Arq 메커니즘 — `WorkerSettings`, `ctx`(잡 컨텍스트)로 provider·HTTP 클라이언트를
      주입하는 패턴(`startup()`), `job_try`, `Retry(defer=...)`
- [ ] APScheduler — `app/scheduler.py`.
      스케줄러는 "일을 하는 게 아니라 큐에 등록만 한다"는 역할 구분
- [ ] Celery 비교 — 왜 Arq인지 자기 언어로 설명 (면접 단골. DESIGN §2)

---

## 6단계 — 실패 처리와 멱등성 (1.5주, 이 포트폴리오의 하이라이트)

면접에서 "가장 어려웠던 부분"으로 말할 재료가 전부 여기 있다.

- [ ] 재시도 + 백오프 — `app/retry.py`(24줄). 지수 백오프, **full jitter**,
      thundering herd. 원전: AWS 블로그 "Exponential Backoff and Jitter" 필독
- [ ] **왜 LLM만 jitter이고 RSS/SES는 아닌가** — LLM은 공유 rate limit(429)이라
      동시 재시도가 파도를 만들지만, RSS는 호스트가 제각각·SES는 하루 1통.
      "불필요한 무작위화를 안 하는 분별"까지가 설계 (DESIGN §5)
- [ ] 실패 격리 — `summarize_pending()`: 한 건 실패 → dead-letter 기록 → `continue`.
      반면 429 → 잡 전체 백오프. **같은 함수 안에서 예외 타입으로 대응이 갈리는 것**이
      1단계 예외 계층의 회수
- [ ] Dead-letter + park — N회 실패 콘텐츠는 `parked_content_ids`로 제외 → 무한 재시도 방지
- [ ] **멱등성 3종 세트** — ① 수집 = content_hash 중복 차단,
      ② 요약 = `add_if_absent`, ③ 발송 = UNIQUE 제약 + status 전이(pending→sent).
      각 잡마다 "두 번 실행하면?" 자문
- [ ] 커밋 타이밍 — "진행분 보존 후 잡 단위 백오프": 재시도 전에 먼저 commit하는 이유

**실습(강력 추천)**: FakeProvider를 "3번 중 1번 랜덤 실패"로 고쳐 파이프라인을 돌리고,
dead-letter에 뭐가 쌓이고 재실행 시 뭐가 복구되는지 직접 관찰.

---

## 7단계 — 아키텍처 패턴 + 테스트 전략 (1~1.5주)

- [ ] **Ports & Adapters (헥사고날)** — 이 프로젝트의 뼈대 패턴.
      `provider.py`(포트) + `providers/anthropic.py`·`providers/fake.py`(어댑터)
      + `factory.py`(선택). LLM·이메일·임베딩 세 곳 모두 같은 구조 —
      하나를 이해하면 셋이 다 읽힘
- [ ] 의존성 주입 — 프레임워크 없이 함수 파라미터(`collect_source(fetch=, sink=)`)와
      Arq ctx로 하는 DI. 본질: "테스트에서 진짜를 가짜로 바꿔 끼우기 위한 장치"
- [ ] 테스트 — `tests/conftest.py`: pytest fixture, `pytest.mark.integration`,
      TEST_DATABASE_URL 없으면 통합 테스트 skip, TRUNCATE 격리.
      `tests/test_pipeline.py`: LLM 실호출 0회로 파이프라인 전체 검증

**검증 질문**: pytest 실행 중 실제 LLM이 절대 호출되지 않는다는 걸
코드 구조가 어떻게 보장하나?

---

## 8단계 — 운영: Docker + 로깅 + V3 임베딩 (1주)

- [ ] `docker-compose.yml` — 4개 컨테이너(app/worker/postgres/redis)의 관계,
      `depends_on`, 볼륨, healthcheck. `Dockerfile` 레이어 캐싱
- [ ] `app/logging_config.py` — 구조화(JSON) 로깅. 왜 print가 아닌지,
      왜 Flower 대신 "로그 + 작업 결과 테이블"인지 (DESIGN §2)
- [ ] V3 (여유 있을 때) — `app/embedding/` + `app/scoring/cosine.py`:
      임베딩, 코사인 유사도, pgvector.
      왜 Jaccard가 `AI↔인공지능`을 놓치는지 (DESIGN §5 실측: 0.828 vs Jaccard 0.0)

---

## 진행 팁

1. **순서를 지킬 것** — 1→2단계 없이 5단계(Arq)로 가면 `worker.py`가 안 읽힌다.
   반대로 1·2단계가 탄탄하면 나머지는 패턴 인식에 가깝다.
2. **졸업 기준은 빈 화면 재구현** — 난이도 순 추천:
   `retry.py` → `scoring/jaccard.py` → `keywords.py` → `collect/service.py`
3. **면접 Q&A 문서와 교차 검증** — 각 단계를 마칠 때마다 docs의 면접 준비 문서를
   "답 안 보고" 먼저 말해본 뒤 대조.
4. **커밋 히스토리도 교재** — `git log --oneline --reverse`로 처음부터 읽으면
   "수직 슬라이스 → 살 붙이기" 진행 순서 자체가 학습 자료.

## 진도 기록

| 단계 | 시작일 | 완료일 | 재구현한 파일 | 메모 |
|------|--------|--------|----------------|------|
| 0 | 2026-09-07 | 2026-09-07 | — | worker.py `run_pipeline()` 4줄 = 프로젝트 전체. 테이블 9개 확인 |
| 1 | 2026-09-07 | 2026-09-07 | (재구현 미실시) | 타입 힌트 shape 읽기 / `\| None` 5패턴 / 키워드 전용 인자 `*` / Protocol↔mypy 관계. 복습: STUDY_NOTES.md |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
