# 포트폴리오 — 수임

> **테마: "실패와 비용까지 설계하고, 숫자로 증명하는 Python 백엔드 개발자"**
>
> GitHub: https://github.com/acceptha/lede · Email: siha@ssrinc.co.kr

---

## 원페이지 요약

**핵심 역량**: 비동기 파이프라인 설계 · 실패 처리(재시도/격리/dead-letter) · LLM 비용 최적화

**기술 스택**: Python 3.12 · FastAPI · Arq(async 워커) · APScheduler · PostgreSQL(+pgvector) · Redis · SQLAlchemy(async)/Alembic · httpx · Docker Compose · GitHub Actions · pytest(61개, LLM 실호출 0회)

**핵심 성과 3줄**
1. LLM 요약 파이프라인에 `content_hash` 캐싱 적용 → 재실행 시 LLM 호출 **3회 → 0회, 4,229토큰 → 0토큰, 79.7초 → ~0초** (실측)
2. LLM 경로에만 full jitter, RSS·이메일 발송은 결정론적 백오프로 재시도 전략을 경로별 분리 설계 → rate limit(429) 동시 재시도(thundering herd) 구조적 차단
3. LLM/임베딩/이메일 3중 provider 추상화 → Anthropic ↔ Ollama 교체 시 파이프라인 코드 **0줄 수정**, 테스트 LLM 비용 **$0**

---

## 대표 프로젝트: lede — AI 뉴스레터 큐레이터

### "재실행해도 안전하고, 실패해도 멈추지 않고, 비용은 숫자로 관리되는 배치 파이프라인"

**개요**
- 2026.06 ~ 2026.07 (4주) / 1인 개발 (설계·구현·테스트·문서 100%)
- Python 3.12, FastAPI, Arq, APScheduler, PostgreSQL(+pgvector), Redis, Docker Compose, GitHub Actions

**문제 (Situation/Task)**

구독한 뉴스레터·기술 블로그를 쌓아두기만 하고 읽지 못하는 정보 과부하를 해결하기 위해, RSS 수집 → LLM 요약 → 관심사 점수 필터 → 일일 다이제스트 이메일을 자동화. 단, LLM API는 호출당 과금이고 배치는 실패·재실행이 일상이므로 **"재실행 안전성(idempotency)과 비용 통제 없이는 운영 불가능한 파이프라인"**이라는 제약을 핵심 문제로 정의.

**해결 (Action) 1 — async 일관성을 기준으로 워커 선택 (Celery 기각)**

- RSS 수집·LLM 호출·메일 발송이 전부 네트워크 대기(I/O 바운드)임을 확인하고, FastAPI(async)와 워커의 멘탈 모델 통일을 위해 **Celery를 검토 후 기각하고 Arq 채택**. Celery는 재시도·모니터링(Flower) 생태계가 강하지만 async↔sync 경계 관리 마찰이 발생 — 모니터링은 구조화 JSON 로깅 + 작업 결과 테이블로 대체하는 트레이드오프를 문서화(DESIGN §2)
- API(FastAPI) / 워커(Arq 잡 6개) / 스케줄러(APScheduler, enqueue만 담당) 3-프로세스 분리. API는 즉시 응답, 무거운 작업은 전부 워커로 위임

```
APScheduler ──(매일 08:00, run_pipeline enqueue)──▶ Redis 큐 ──▶ Arq Worker
  collect_feeds → summarize_pending → embed_pending → build_and_send_digest
     contents(DB)     summaries(캐싱)     pgvector        digests(발송 1회 보장)

FastAPI: /interests(관심사 CRUD) · /dead-letters(관측) · /docs(Swagger)
```

**해결 (Action) 2 — idempotency를 코드가 아닌 DB 제약으로 강제**

- 요약 캐시: `contents.content_hash` UNIQUE + `INSERT ... ON CONFLICT` → 같은 글 재요약 0회
- 발송: `digests(user_id, digest_date)` UNIQUE → 하루 1통 보장. "재시도를 못 하게 막는 게 아니라, 재시도해도 안전하게" 설계

**해결 (Action) 3 — 실패 유형별로 다른 재시도 전략**

- **LLM 경로 = full jitter** (`random(0, base × 2^attempt)`): 병렬 요약이 공유 rate limit(429)에 걸리면 동시 실패→동시 재시도하는 thundering herd 발생 → 무작위 대기로 분산
- **RSS·이메일 발송 경로 = 결정론적 지수 백오프**: 피드마다 호스트가 다르고 발송은 하루 1통이라 herd가 없음 → 무작위화는 불필요한 복잡도. 누락이 아닌 의도적 구분임을 설계 문서에 명시 (발송 sender는 현재 Fake — SES 실발송은 미구현)
- 요약 3회 실패 시 `dead_letters` 테이블에 park(retry-then-park) → 한 콘텐츠의 영구 실패가 파이프라인 전체를 멈추지 않음. `GET /dead-letters`로 관측

**해결 (Action) 4 — LLM 비용을 추상화·캐싱·측정으로 통제**

- LLM/임베딩/이메일 3중 Protocol 추상화: SDK import는 `providers/` 내부로 격리, 파이프라인은 인터페이스만 의존. 테스트는 FakeProvider 주입(호출 횟수·입력 본문 검증 가능)
- 예상 읽기 시간은 LLM에 묻지 않고 글자 수 ÷ 분당 속도로 계산, HTML 태그 제거 후 입력 → 토큰 절감. 출력은 강제 tool use로 구조화(JSON) 수신
- 저비용 모델(Claude Haiku) 시작 + 로컬 모델(Ollama EXAONE 3.5, $0) 옵션. 프롬프트 캐싱도 설정했으나 시스템 프롬프트가 최소 캐시 단위에 못 미쳐 실효는 작음 — 주 절감 레버는 content_hash 캐싱

**결과 (Result)** — 액션 ↔ 수치 1:1

| 액션 | Before → After (측정 방법) |
|---|---|
| content_hash 캐싱 | 재실행 시 LLM 호출 3회 → **0회**, 4,229토큰 → **0**, 79.7s → **~0s** (구조화 로그의 `llm_usage` 집계, EXAONE 3.5 로컬 3건) |
| FakeProvider 주입 | 테스트 61개 전체 실행 중 LLM 실호출·비용 **0** (provider `call_count`로 검증) |
| provider 추상화 | Anthropic → Ollama 교체 시 파이프라인 코드 수정 **0줄** (env 1줄) |
| UNIQUE 제약 idempotency | 파이프라인 2회 연속 실행 시 재요약 0회·중복 발송 0회 (실 Postgres 통합 테스트로 자동 증명) |
| 임베딩 점수 전략 추가(V3) | 토큰이 안 겹치는 `AI↔인공지능` 매칭 Jaccard 0.000 → 코사인 **0.828** (bge-m3, pgvector) |

**배운 점 (Takeaway)**

재시도·캐싱·중복 방지는 코드 로직보다 DB 제약과 큐의 계약으로 강제할 때 깨지지 않는다. 다시 한다면 dead-letter 재처리(수동 replay) API를 첫 슬라이스에 포함시킬 것.

---

## 기술적 깊이 — 관심사 점수 함수의 의사결정 과정

**한 페이지 메시지: "선제 도입 대신, 전환 조건을 정의해두는 방식으로 복잡도를 관리했다"**

- 집합 유사도 5종(교집합 크기, Jaccard, Overlap, Sørensen–Dice, Tversky)을 수식·특성으로 비교 후 **Jaccard 채택**: 0~1 정규화로 top-N 컷이 직관적이고, 집합 크기가 달라도 동작 (Jaccard 1912, Manning IR 2008 인용)
- Jaccard의 한계(표기 흔들림 — `AI` vs `인공지능`은 점수 0)를 문서에 먼저 기록하고, 해결책(임베딩 코사인)은 V3로 미룸. 대신 **관찰 트리거**("관심사 많은 유저의 점수 하락이 측정되면 Tversky 전환 검토")를 정의
- 양쪽 입력(LLM 키워드 출력, 유저 관심사 등록)에 동일한 정규화 함수(소문자화+한/영 별칭 매핑)를 적용 — 한쪽만 정규화하면 점수가 조용히 망가지는 버그를 테스트로 고정
- V3에서 `SCORING_STRATEGY` env 하나로 Jaccard ↔ 임베딩 코사인 교체 가능하게 구현, 한계를 실측(0.000 → 0.828)으로 해소

---

## 개발 방식 · 협업 습관

- **문서가 SSOT**: 기술 결정을 코드보다 먼저 DESIGN.md에 대안 비교와 함께 기록. 구현이 설계와 달라지면 문서를 먼저 수정
- **수직 슬라이스 우선**: "수집→요약→발송" 한 줄기를 먼저 관통 후 확장. 커밋 히스토리가 이 순서 그대로 남아 있음 (conventional commits, 커밋 본문에 설계 조항 참조)
- **리뷰 가능한 산출물**: `docker compose up` 한 줄 재현, CI(GitHub Actions ruff+pytest 2잡), 예상 면접 Q&A 문서(docs/INTERVIEW.md)까지 리뷰어 관점으로 준비

---

## 마무리

배치 파이프라인의 가치는 기능이 아니라 **실패했을 때의 행동과 재실행했을 때의 안전성**에 있다고 믿습니다. 측정 없이 최적화하지 않고, 결정에는 기각한 대안을 남기는 방식으로 일합니다.

GitHub: https://github.com/acceptha/lede · Email: siha@ssrinc.co.kr
