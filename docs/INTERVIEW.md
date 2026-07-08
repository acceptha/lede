# lede — 예상 면접 질문 & 답변 포인트

> 이 프로젝트로 면접관이 물어볼 법한 질문 모음. 답변은 실제 구현·결정 근거로 정리(암기용 아니라 이해용).
> 관련 코드/문서를 함께 표기.

---

## A. 아키텍처 · 비동기

**Q1. 왜 API/워커/스케줄러를 분리했나요?**
- API는 즉시 응답해야 하는데 RSS 수집·LLM 요약·발송은 수 초~수십 초 걸리는 I/O 작업. → 무거운 일은 워커(Arq)에 위임, API(FastAPI)는 CRUD·조회만. 스케줄러(APScheduler)는 매일 정해진 시각에 잡을 큐에 등록하는 "알람시계". (DESIGN §2·§4)

**Q2. 왜 Celery가 아니라 Arq인가요?**
- FastAPI가 `async def`인데 워커까지 async(Arq)로 통일하면 코드 전체가 한 멘탈 모델. RSS·LLM 호출은 전부 네트워크 대기라 async 궁합이 좋음. Celery는 async↔sync 경계 마찰이 생김. (모니터링 화려함이 필요하면 Celery+Flower지만, 여기선 구조화 로깅+작업결과 테이블로 대체) — 의도적 선택. (DESIGN §2)

**Q3. 스케줄러를 왜 별도 컨테이너가 아니라 워커 컨테이너 내 프로세스로?**
- 전용 컨테이너는 배치 성격에 과함. compose worker 커맨드에서 `(python -m app.scheduler &) && exec arq ...`로 같은 이미지·컨테이너 안 별도 프로세스로 기동. 운영 시 Arq cron으로 흡수 가능.

**Q4. 동기 블로킹이 파이프라인에 섞이지 않게 어떻게 보장했나요?**
- DB는 async 드라이버(asyncpg), HTTP는 httpx async. feedparser 파싱은 순수 CPU(바이트→객체)라 네트워크는 async fetch로 분리(`fetch_feed`/`parse_feed`).

---

## B. LLM 추상화 · 비용 최적화

**Q5. LLM provider를 왜 추상화했고, 어떻게 검증했나요?**
- 파이프라인은 `LLMProvider` Protocol만 알고 SDK는 `app/llm/providers/`에서만 import. → Anthropic↔Ollama를 **코드 0줄 수정**으로 교체(실측). 테스트는 `FakeProvider` 주입으로 실호출 0회. (절대규칙 1)

**Q6. 비용을 어떻게 줄였나요?**
- ① `content_hash` 캐싱(같은 글 재요약 0회) ② HTML 제거 후 LLM 전달(토큰↓) ③ 읽기 시간은 LLM이 아니라 글자수÷속도로 직접 계산 ④ 저비용/로컬 모델 시작 ⑤ 구조화 출력(JSON)으로 파싱 안정. 캐싱 전/후를 실측: 3건 재요약 4,229토큰/79.7s → 재실행 0.

**Q7. content_hash 캐싱과 프롬프트 캐싱의 차이는?**
- content_hash 캐싱: 같은 콘텐츠면 요약 자체를 다시 안 함(DB, 가장 큰 절감). 프롬프트 캐싱: 반복되는 시스템 프롬프트 토큰 비용 절감(모델 단). 우리 시스템 프롬프트는 짧아 Haiku 최소 캐시 prefix(4096토큰)에 못 미쳐 실질 효과는 작음 → 주 레버는 content_hash라고 정직하게 문서화.

**Q8. 구조화 출력은 어떻게 강제했나요?**
- Anthropic: 강제 tool use(`tool_choice` 고정)로 `{summary_lines, keywords}` 받아 dict 검증. Ollama: `format`(JSON 스키마)로 제약. → `LLMSummary`(Pydantic)로 검증.

---

## C. 실패 처리

**Q9. 재시도 백오프를 경로별로 다르게 한 이유는? (핵심)**
- **LLM = full jitter**: 새 글 여러 개를 병렬 요약하다 공유 rate limit(429)에 걸리면 작업들이 동시에 실패→동시에 재시도하는 thundering herd 발생. 대기를 `random(0, base·2^n)`로 무작위화해 재시도 파도를 분산.
- **RSS·SES = 결정론적 백오프**: RSS는 호스트가 달라 한 대상에 안 몰리고, SES는 하루 1통이라 herd 없음 → 무작위화 불필요. (DESIGN §5, `app/retry.py`)

**Q10. 한 콘텐츠 요약이 실패하면 어떻게 되나요?**
- 실패 격리: 해당 콘텐츠만 dead-letter 기록 후 `continue`, 배치는 계속. 429(공유 한도)만 예외적으로 잡 전체를 jitter로 백오프·재시도.

**Q11. dead-letter를 어떻게 설계했나요? 무한 재시도는 어떻게 막나요?**
- `dead_letters(job_type, content_id, attempts, error)` upsert(대상당 1행, attempts 누적). `attempts >= 임계(기본 3)`이면 `select_pending`에서 제외(**park**). → 일시적 실패는 재실행으로 자가 치유, 영구 실패는 N회 후 park. `GET /dead-letters`로 관측. (커밋 `c0565ee`)

**Q12. 재시도가 안전한 근거는?**
- 모든 단계가 멱등. 재실행이 곧 재시도인데도 content_hash·발송 UNIQUE·embedding NULL 조회로 중복이 0. dead-letter park가 무한 루프를 막음.

---

## D. idempotency · 데이터 모델

**Q13. "언제든 재실행 가능"을 어떻게 보장했나요?**
- DB 제약으로: `contents.content_hash` UNIQUE(재요약 캐시 키), `digests(user_id, digest_date)` UNIQUE(발송 1회). `INSERT ... ON CONFLICT DO NOTHING RETURNING`로 신규/중복 판정. 통합 테스트로 자동 증명.

**Q14. content_hash는 무엇으로 계산하나요? URL이 아니라 왜 본문 해시?**
- 정규화(공백 접기)한 본문의 sha256. 같은 글이 표기 흔들림에 관계없이 같은 해시 → 중복 차단 + 요약 캐시 키. (`app/collect/hashing.py`)

**Q15. 마이그레이션은 어떻게 관리하나요?**
- Alembic(async). 수동 DDL 금지. `docker compose up` 시 worker가 `alembic upgrade head` 자동 실행. 스키마 변경은 반드시 마이그레이션으로.

---

## E. 점수 함수 · 추천

**Q16. 왜 Jaccard인가요? 한계는?**
- 0~1 정규화라 top-N 자르기가 직관적, 집합 크기 달라도 동작. 한계: tf·idf 무시, **정확 토큰 매칭**이라 표기 흔들림(`AI`≠`인공지능`)에 약함. IR 교과서(Manning 6장)가 지적하는 그 한계. (DESIGN §5)

**Q17. threshold가 아니라 top-N을 쓴 이유는?**
- 관심사 5개 × 키워드 4~5개 수준의 작은 집합에서 Jaccard는 0, 0.11, 0.25처럼 이산적. 절대 기준("0.3 이상")은 발송 분량이 날마다 널뜀. → `score>0` 중 top-N(기본 5), 동점은 `published_at` 최신순, 0건이면 스킵.

**Q18. 키워드 정규화를 왜 양쪽에 적용하나요?**
- LLM 키워드 출력과 `user_interests` 등록에 **동일 정규화 함수**(소문자화+별칭맵)를 태워야 두 집합이 같은 공간에. 한쪽만 하면 Jaccard가 표기 차이로 망가짐. (절대규칙 6)

**Q19. 임베딩 코사인은 언제 쓰고 Jaccard와 어떻게 공존하나요?**
- `SCORING_STRATEGY`로 교체. 임베딩은 토큰 안 겹쳐도 의미로 매칭(`AI↔인공지능` Jaccard 0 → 코사인 0.828). 알려진 표기 변형은 정규화(별칭맵), 의미 동의어는 임베딩 → **상보적**. 하이브리드가 최선(확장 여지).

---

## F. 벡터 검색 (V3)

**Q20. pgvector를 왜 도입했고 유사도는 어떻게 계산하나요?**
- 임베딩(bge-m3, 1024차원)을 `summaries.embedding vector(1024)`에 저장, 코사인 거리(`<=>`)로 최근접 검색. 관심사 키워드들을 임베딩해 centroid(평균 벡터)를 만들고 콘텐츠 임베딩과 코사인. (`app/embedding/`, `app/scoring/cosine.py`)

**Q21. 임베딩 차원을 하드코딩했는데 모델을 바꾸면?**
- `vector(1024)`는 bge-m3 기준. 모델 변경 시 차원이 달라져 마이그레이션 필요 — 주석에 명시. (트레이드오프 인지)

**Q22. 임베딩 실패는 어떻게 처리하나요?**
- 배치 단위 격리(실패 배치 skip), embedding이 NULL로 남아 다음 실행에 재시도(자가 치유). 로컬이라 rate limit 없어 park 불필요.

---

## G. 테스트 · CI

**Q23. 테스트 전략은?**
- 단위 54(순수 로직·API는 가짜 주입) + 통합 7(실 Postgres). pytest 마커로 분리. 단위는 DB 없이 빠르게, 통합은 `TEST_DATABASE_URL`로. **실 LLM 호출 0회**(FakeProvider).

**Q24. 통합 테스트 격리는 어떻게?**
- 전용 `lede_test` DB, 매 테스트 전 전 테이블 TRUNCATE, create_all은 멱등. repo에 세션 주입해 실 SQL(ON CONFLICT·UNIQUE·`<=>`)을 검증.

**Q25. CI 구성은?**
- GitHub Actions 2잡: `test`(단위, DB 불필요) + `integration`(postgres 서비스 `pgvector/pgvector:pg16`). push/PR마다 ruff+pytest 게이트.

---

## H. 운영 · 관측

**Q26. Flower 없이 어떻게 관측하나요?**
- stdlib JSON 포매터로 `lede.*` 로그를 stdout에(비용·토큰·잡 결과 파싱 가능) + `dead_letters` 테이블 + 잡 결과 dict. (DESIGN §2, 커밋 `42cf162`)

**Q27. `docker compose up` 한 줄로 어떻게 다 뜨나요?**
- worker 커맨드: `alembic upgrade head && python -m app.seed && (scheduler &) && exec arq`. postgres/redis healthcheck + `depends_on: service_healthy`로 순서 보장.

---

## I. 스코프 · 설계 판단

**Q28. 왜 크롤링 없이 RSS만?**
- ToS·차단 리스크. MVP는 RSS로 못박고, 본문 없는 소스(너겟 헤드라인형)나 RSS 없는 소스(뉴닉)는 스크래핑하지 않고 보류로 기록. (DESIGN §3-6, §11)

**Q29. 왜 seed 유저 1명? 인증은?**
- MVP는 단일 유저로 파이프라인 검증에 집중. 스키마는 멀티유저(`user_id` FK) 유지, 가입/JWT는 V2. 스코프 크리프 방지.

**Q30. 다시 만든다면 무엇을 바꾸겠나요? (열린 질문)**
- 예: run_pipeline이 배치 요약을 한 잡에서 처리 → 대량이면 콘텐츠 단위 잡으로 팬아웃; 임베딩 차원 하드코딩 대신 모델 메타 관리; 점수 threshold 관찰 트리거 자동화 등.

---

## J. 실전 트러블슈팅 (직접 겪은 것 — 강력 어필 포인트)

**Q31. 개발 중 겪은 까다로운 문제와 해결은?**
- **host 5432 포트 충돌**: 로컬 native PostgreSQL이 5432 점유 → Docker postgres 공개 포트를 5433으로 분리(원인을 프로세스로 규명 후).
- **arq job_timeout(300s) 초과**: run_pipeline이 콜드 Ollama 모델 로딩+배치 요약으로 300s 초과해 취소됨 → `job_timeout=1800` + Ollama `keep_alive`로 해결. (콜드/웜 차이를 실측으로 규명)
- **우아한형제들 RSS 403**: full-text지만 Cloudflare JS 챌린지로 봇 차단 → 헤드리스 우회는 스코프 밖이라 제외, 대신 토스·네이버 D2 채택. 브라우저형 UA로 다른 피드 차단 회피.
- **Postgres 이미지 교체 시 데이터**: alpine(musl)→pgvector(glibc) libc 차이로 collation 리스크 → dev 데이터라 볼륨 초기화 후 재부트스트랩(마이그레이션+seed 자동).

> 이 항목들은 "근본 원인을 규명하고 스코프를 지키며 해결"하는 태도를 보여주기 좋음.

---

## 한 줄 정리
> "기능 나열이 아니라 **비동기 파이프라인·실패 처리·비용 최적화**를 측정 가능한 형태로 증명했고, 설계 결정마다 이유와 트레이드오프를 문서(SSOT)에 남겼다."
