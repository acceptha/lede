# lede — AI Newsletter Curator

> RSS 수집 → LLM 요약 → 관심사 점수 필터 → 일일 다이제스트 이메일을 자동화하는 **비동기 배치 파이프라인**.
> *Collects RSS, summarizes with an LLM, scores against your interests, and emails a daily digest.*

백엔드 포트폴리오 프로젝트입니다. 화려한 기능이 아니라 **비동기 파이프라인 설계 · 실패 처리 · 비용 최적화의 깊이**를 증명하는 것이 목적입니다.

설계 단일 진실 공급원(SSOT): [docs/DESIGN.md](docs/DESIGN.md) · 기획: [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)

---

## 이 레포가 증명하는 것

| 기둥 | 무엇을 / 어디서 |
|------|----------------|
| **비동기 파이프라인 설계** | API(FastAPI) / 워커(Arq) / 스케줄러(APScheduler)를 분리. 전 구간 `async`. `docker compose up` 한 줄로 재현 |
| **실패 처리** | 재시도 백오프(LLM=full jitter / RSS·SES=결정론적, 의도적 구분), 실패 격리, **dead-letter retry-then-park**, 구조화 JSON 로깅 |
| **비용 최적화** | LLM 추상화로 공급자 교체, `content_hash` 캐싱(재요약 0회), HTML 제거(토큰 절감), 읽기시간 직접 계산(LLM 미사용), 구조화 출력, 로컬 모델($0) |
| **idempotency** | 파이프라인 전체 재실행 안전 — `content_hash` UNIQUE(재요약 0), `(user_id, digest_date)` UNIQUE(중복 발송 0) |

---

## 아키텍처

```
            ┌─────────────┐
            │ APScheduler │  매일 정해진 시각 → run_pipeline을 Redis 큐에 등록 (알람시계)
            └──────┬──────┘
                   ▼
            ┌─────────────┐   collect_feeds → summarize_pending → build_and_send_digest
            │  Arq Worker │   (async 백그라운드 실행, 멱등)
            └──────┬──────┘
                   ▼
  RSS 수집 → contents(DB) → LLM 요약(캐싱) → 키워드 정규화
                                                │
                                                ▼
                              관심도 점수(Jaccard, top-N) → 일일 다이제스트 → Email
  ┌──────────────┐
  │  FastAPI App │  관심사 CRUD(/interests) · dead-letter 조회(/dead-letters) · /docs(Swagger=관리자 콘솔)
  └──────────────┘

  공통: PostgreSQL(영속) · Redis(Arq 큐 + 캐시)
  LLM: provider 추상화 → fake | anthropic(Claude Haiku) | ollama(로컬, 무료)
```

데이터 흐름: **수집 → 요약 → 점수(추천) → 전달** 전 과정 자동화.

---

## 빠른 시작

```bash
cp .env.example .env          # 필요 시 값 수정 (LLM_PROVIDER 등)
docker compose up -d --build  # postgres + redis + app + worker(+scheduler) 일괄 기동
```
- worker 컨테이너가 기동 시 **마이그레이션(alembic) + seed**를 자동 수행하고, 스케줄러(별도 프로세스)와 Arq 워커를 띄웁니다.
- API: http://localhost:8000/docs (Swagger UI = 관리자 콘솔), 헬스: `/health`

### LLM 공급자 선택 (`.env`의 `LLM_PROVIDER`)
| 값 | 비용 | 준비 |
|----|------|------|
| `fake` | $0 | 없음 (테스트·개발 기본) |
| `ollama` | $0 (로컬) | `ollama pull exaone3.5:2.4b` — [docs/OLLAMA.md](docs/OLLAMA.md) 참고 |
| `anthropic` | 유료 | `ANTHROPIC_API_KEY` 설정 (Claude Haiku) |

> 한국어 콘텐츠라 로컬은 한국어 특화 **EXAONE 3.5**를 기본 모델로 둡니다. 컨테이너에서 host의 Ollama를 쓰도록 `OLLAMA_BASE_URL=http://host.docker.internal:11434`로 연결됩니다.

---

## 핵심 설계 결정 (요약)

- **LLM 추상화** — SDK는 `app/llm/providers/`에서만 import. 파이프라인은 `LLMProvider` 프로토콜만 안다. 그래서 Anthropic↔Ollama 전환이 **코드 0줄 수정**. 테스트는 항상 `FakeProvider` 주입.
- **idempotency를 DB 제약으로** — `contents.content_hash` UNIQUE = 요약 캐시 키, `digests(user_id, digest_date)` UNIQUE = 발송 1회. `INSERT ... ON CONFLICT`로 재실행 안전.
- **점수 함수 = Jaccard** — `score>0` 중 top-N(기본 5), 동점은 `published_at` 최신순. 관심사·키워드는 **동일 정규화 함수**(소문자+별칭)로 같은 공간에. (한계·근거는 DESIGN §5)
- **실패 처리** — LLM 재시도엔 **full jitter**(thundering herd 방지), RSS·SES엔 **결정론적 백오프**(의도적 구분). 한 건 실패는 격리하고 계속, N회 초과 시 **dead-letter park**.
- **관측** — Flower 대신 **구조화 JSON 로그 + 작업 결과/dead-letter 테이블**.

---

## 측정된 숫자 (비용 최적화 근거)

- **테스트 비용 $0** — `pytest` 40개, `FakeProvider` 주입으로 **실 LLM 호출 0회**.
- **로컬 추론 $0** — Ollama(EXAONE 3.5 2.4b) 기사 1건 요약: prompt ~500–3700 tok / 출력 ~60–150 tok / **비용 $0(로컬)**. JSON 로그 예:
  ```json
  {"msg":"llm_usage","provider":"ollama","model":"exaone3.5:2.4b","prompt_tokens":2460,"eval_tokens":116,"cost_usd":0}
  ```
- **재요약 0회** — 같은 콘텐츠 재실행 시 `content_hash` 캐시로 LLM 재호출 0 (검증: 재실행 `summarized:0`).
- **중복 발송 0회** — 다이제스트 잡 재실행 시 `already_sent`로 재발송 없음.
- Anthropic 경로(Claude Haiku) 단가 $1/$5 per 1M tok — 크레딧 충전 시 동일 코드로 측정 가능.

---

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 헬스 체크 |
| GET/POST/DELETE | `/interests` | 관심 키워드 등록·조회·삭제 (정규화 적용) |
| GET | `/dead-letters` | 실패한 요약 작업 관측 |
| GET | `/docs` | Swagger UI (관리자 콘솔) |

---

## 명령어

```bash
docker compose up -d --build          # 전체 스택
pytest                                # 전체 테스트 (실 LLM 호출 0회)
pytest -x -q tests/test_pipeline.py   # 파이프라인 빠른 검증
alembic upgrade head                  # 마이그레이션
ruff check . && ruff format .         # 린트 + 포맷
```

---

## 기술 스택

Python 3.12 · FastAPI · Arq · APScheduler · PostgreSQL · Redis · SQLAlchemy(async)/asyncpg · Alembic · httpx · feedparser · Docker Compose · pytest · ruff

> Celery는 검토 후 의도적으로 기각(async 일관성). 근거: DESIGN §2.

---

## 스코프 / 로드맵

**MVP(현재)**: RSS 수집 + content_hash 중복 제거 / LLM 요약(캐싱) / 관심사 등록 + Jaccard top-N / 일일 다이제스트(idempotent) / 실패 처리(재시도·dead-letter) / 스케줄 자동화 / 구조화 로깅.

| 버전 | 계획 |
|------|------|
| 진행 중 | 본문 전문 RSS 다중 소스 확장 |
| V2 | 가입/로그인/JWT, 멀티유저, Slack/Discord 연동, SES 프로덕션 |
| V3 | 벡터 검색·유사 콘텐츠 추천 (Jaccard → tf-idf/임베딩) |
| V4 | `user_events` 기반 개인화 추천 |

상세: [docs/DESIGN.md](docs/DESIGN.md) §10

---

## 문서

- [docs/DESIGN.md](docs/DESIGN.md) — 기술 결정·메커니즘·성공 기준 (SSOT)
- [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) — 기획
- [docs/OLLAMA.md](docs/OLLAMA.md) — 로컬 LLM(Ollama) 설정
