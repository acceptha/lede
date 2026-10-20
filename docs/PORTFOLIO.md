# lede — 포트폴리오 정리본

> **RSS 수집 → LLM 요약 → 관심사 점수 필터 → 일일 다이제스트 이메일**을 자동화하는 비동기 배치 파이프라인.
> Repo: https://github.com/acceptha/lede · 언어: Python 3.12 · 기간 산출물: `docker compose up` 한 줄 재현

---

## 1. 무엇을, 왜

개발자·직장인이 구독만 하고 안 읽는 뉴스레터·아티클을, **수집 → 요약 → 추천 → 전달**로 자동 큐레이션해 정보 과부하를 줄이는 개인용 배치 파이프라인.

**포트폴리오 목적**: 화려한 기능이 아니라 백엔드 핵심 역량을 *깊게* 증명한다.
- 🧩 **비동기 파이프라인 설계** (API / 워커 / 스케줄러 분리)
- 🛡 **실패 처리** (재시도·백오프·격리·dead-letter·관측)
- 💰 **비용 최적화** (LLM 추상화·캐싱·로컬 모델·측정)

---

## 2. 핵심 성과 (한눈에)

| 항목 | 값 |
|------|-----|
| 커밋 | 기능 단위 conventional commits, 증분 개발 (`git log --oneline`) |
| 이메일 발송 | 렌더링·발송 idempotency·재시도까지 구현. **실 sender(SES)는 미구현** — 현재 `FakeEmailSender` |
| 테스트 | **61개** (단위 54 + 통합 7), CI에서 자동 실행 |
| CI | GitHub Actions 2잡(unit·integration) 녹색 |
| LLM 비용(테스트) | **$0** — 가짜 provider 주입, 실 호출 0회 |
| LLM 비용(운영) | **$0** — 로컬 모델(Ollama) 또는 저비용 API 선택 |
| 재현성 | `docker compose up` 한 줄 = 마이그레이션·seed·스케줄러·워커 자동 |

---

## 3. 기술적 하이라이트 (깊이)

### ① LLM/임베딩/이메일 3중 provider 추상화
- 파이프라인 코드는 인터페이스(Protocol)만 알고, SDK는 `providers/` 안에서만 import.
- **효과**: 요약 provider를 Anthropic → Ollama로 **코드 0줄 수정**으로 교체(실측). 테스트는 Fake 주입으로 비용 0.
- 같은 패턴을 **LLM·임베딩·이메일** 세 곳에 반복 → 교체 가능한 설계의 일관성.

### ② idempotency를 DB 제약으로 못박음
- `contents.content_hash` UNIQUE = 요약 캐시 키, `digests(user_id, digest_date)` UNIQUE = 발송 1회.
- `INSERT ... ON CONFLICT`로 **파이프라인을 언제 재실행해도** 재요약 0·중복 발송 0. (통합 테스트로 자동 증명)

### ③ 경로별로 다른 재시도 전략 (분별)
- **LLM = full jitter**: 공유 rate limit(429)에 병렬 요약이 동시 재시도하는 thundering herd를 무작위 대기로 분산.
- **RSS·이메일 발송 = 결정론적 백오프**: herd가 없어 무작위화 불필요.
- 왜 다른지를 코드·문서에 근거로 명시(DESIGN §5).

### ④ dead-letter "retry-then-park"
- 실패한 요약을 `dead_letters`에 upsert(attempts 누적), N회 초과 시 **park**(재시도 제외)해 무한 루프 방지.
- 일시적 실패는 재실행으로 자가 치유, 영구 실패는 기록+격리. `GET /dead-letters`로 관측.

### ⑤ 관측 = 구조화 로그 + 작업 결과 테이블 (Flower 없이)
- stdlib JSON 포매터로 `lede.*` 로그를 stdout에 (비용·토큰·잡 결과 파싱 가능).
- 예: `{"msg":"llm_usage","provider":"ollama","prompt_tokens":2460,"cost_usd":0}`

### ⑥ 교체 가능한 점수 전략 (V3 벡터 방향)
- `SCORING_STRATEGY`로 **Jaccard(토큰 겹침) ↔ 임베딩 코사인(의미)** 교체.
- 임베딩은 pgvector에 저장, 코사인 거리로 최근접 검색.
- **payoff 실측**: `AI↔인공지능`은 토큰이 안 겹쳐 Jaccard 0인데 코사인 0.828 → 의미로 매칭.

---

## 4. 아키텍처

```
 APScheduler ──(매일 정해진 시각, run_pipeline enqueue)──▶ Redis 큐
                                                            │
 Arq Worker ◀───────────────────────────────────────────────┘
   └ collect_feeds → summarize_pending → embed_pending → build_and_send_digest
        ↓              ↓ (LLM)             ↓ (임베딩)        ↓ (점수 → 이메일)
   contents(DB) → summaries(캐싱) → pgvector → digests

 FastAPI App: /interests(관심사) · /dead-letters(관측) · /docs(Swagger=관리자 콘솔)
 공통: PostgreSQL(+pgvector) · Redis(큐+캐시)
```
**분리 원칙**: API는 즉시 응답, 무거운 일(수집·요약·임베딩·발송)은 전부 워커/스케줄러로 위임.

---

## 5. 측정 결과 (근거)

**content_hash 캐싱 전/후** (EXAONE 3.5 로컬, 3건):

| | LLM 호출 | 토큰 | 시간 |
|---|:---:|:---:|:---:|
| 캐시 미적용(재요약) | 3 | 4,229 | 79.7s |
| **캐시 적용(재실행)** | **0** | **0** | ~0s |

**Jaccard vs 임베딩 코사인** (bge-m3 로컬):

| 관심사 ↔ 콘텐츠 | Jaccard | 코사인 |
|---|:---:|:---:|
| AI ↔ 인공지능 | 0.000 | **0.828** |
| 주식 ↔ 증시 | 0.000 | **0.757** |

---

## 6. 기술 스택

**언어/프레임워크**: Python 3.12 · FastAPI(API) · Arq(async 워커) · APScheduler(스케줄러)
**데이터**: PostgreSQL + pgvector · Redis · SQLAlchemy(async)/asyncpg · Alembic
**AI**: LLM 추상화(Anthropic Claude Haiku / Ollama EXAONE 3.5) · 임베딩(Ollama bge-m3)
**수집/HTTP**: httpx(async) · feedparser
**운영/품질**: Docker Compose · GitHub Actions(CI) · pytest · ruff

> Celery는 검토 후 async 일관성을 위해 의도적으로 기각(DESIGN §2).

---

## 7. 어떻게 리뷰하나

1. **README.md** — 프로젝트 요약·아키텍처·측정 숫자·빠른 시작 (시작점).
2. **실행**: `cp .env.example .env && docker compose up -d --build` → http://localhost:8000/docs (Swagger).
3. **설계 깊이**: `docs/DESIGN.md` (SSOT) — 기술 결정·메커니즘·성공 기준(§9)·소스 조사(§11).
4. **빌드 과정**: `git log --oneline` — 기능 하나씩 증분 커밋으로 추적 가능.
5. **테스트/CI**: `pytest` (로컬), GitHub Actions 탭(자동).
6. **로컬 LLM**: `docs/OLLAMA.md` — Ollama 설정.

---

## 8. 확장 로드맵

| 버전 | 내용 |
|------|------|
| V2 | 가입/로그인/JWT, 멀티유저, Slack/Discord/Telegram 연동, SES 프로덕션 |
| V3 심화 | 유사 콘텐츠 추천, 코사인 threshold 튜닝, Jaccard+임베딩 하이브리드 |
| V4 | `user_events` 기반 개인화 추천 |

---

## 9. 개발 방식

- **수직 슬라이스 우선**: "동작하는 한 줄기"(수집→요약→전달)를 먼저 관통 후 살 붙임.
- **증분 + 테스트 동반**: 기능마다 단위/통합 테스트, CI 게이트.
- **문서가 SSOT**: 설계 결정을 코드보다 먼저 DESIGN.md에 기록·갱신.
- **측정 기반**: "저비용 모델 시작, 측정 후에만 승급" 등 비용을 숫자로 관리.
