# 설계 문서 — AI Newsletter Curator (`lede`)

> 생성: office-hours 세션 (2026-06-11)
> 개정: v1.1 (2026-06-12) — 다이제스트 스키마 모순 해소, 점수 적용 정책 확정, 성공 기준 보강
> 상태: APPROVED
> 모드: Builder (백엔드 포트폴리오)
> 참조 기획서: [PROJECT_PLAN.md](./PROJECT_PLAN.md)

이 문서는 `PROJECT_PLAN.md`의 기획을 검토한 뒤 **확정한 기술 결정과 보완 사항**을 담는다.
기획서는 "무엇을 만들 것인가"이고, 이 문서는 "어떻게 만들 것인가 + 왜 그렇게 정했는가"이다.

---

## 1. 문제 정의

개발자·직장인은 뉴스레터·블로그·기술 아티클을 잔뜩 구독하지만 실제로 읽는 비율은 낮다.
**RSS로 수집 → LLM으로 요약 → 관심사 점수로 필터 → 하루치 다이제스트 이메일**로 묶어 보내는
배치 파이프라인으로 정보 과부하를 줄인다.

**진짜 목표(포트폴리오 관점):** 단순 기능 나열이 아니라 다음을 *깊게* 증명한다.
- API 서버 / 워커 / 스케줄러를 분리한 비동기 파이프라인 설계
- LLM 추상화 + 비용 최적화 (캐싱, 저비용 모델, 토큰 절약)
- 실패 처리(재시도·백오프·idempotency)와 데이터 중복 제거
- docker-compose 기반 재현 가능한 운영 환경

---

## 2. 확정 기술 결정

| 항목 | 확정 | 이유 |
|------|------|------|
| 언어 | Python 3.12+ | 3.7 EOL → 최신 LTS급 |
| API 서버 | **FastAPI** | async, Pydantic 검증, 자동 OpenAPI 문서 |
| 워커 | **Arq** | async 네이티브 → API와 동일한 멘탈 모델로 코드 통일 |
| 스케줄러 | **APScheduler** | MVP엔 충분. **worker 컨테이너 내 별도 프로세스로 기동** (전용 컨테이너 불필요). 운영 시 Arq cron으로 흡수 가능 |
| DB | **PostgreSQL** | |
| 캐시 / 브로커 | **Redis** | Arq 작업 큐 + 캐시 겸용 |
| AI | **LLM 추상화 레이어** | 저비용 모델 시작, 프롬프트 캐싱, 공급자 교체 가능 |
| 컨테이너 | **Docker / docker-compose** | app + worker + postgres + redis 일괄 기동 |
| 테스트 | **pytest + 가짜 LLM provider 주입** | 비용 0원으로 파이프라인 검증 |

### 왜 Arq인가 (vs Celery)
FastAPI(`async def`)와 워커를 둘 다 async로 통일하면 코드 전체가 한 가지 멘탈 모델로 읽힌다.
RSS 긁기·LLM 호출은 전부 네트워크 대기(I/O)라 async 궁합이 좋다. Celery를 쓰면 async↔sync
경계 관리라는 마찰이 생긴다. (단, 재시도/모니터링 시각화를 전면에 내세우고 싶다면 Celery+Flower가
더 화려하다 — 의도적으로 Arq를 택했고, 모니터링은 구조화 로깅 + 작업 결과 테이블로 대체한다.)

### 컴포넌트 역할 (3장 다이어그램의 코드 관점 해석)
```
APScheduler (스케줄러)   정해진 시각에 작업을 Redis 큐에 등록      ← 알람시계
        │
        ▼
Arq (워커)               큐에서 꺼내 실제 실행                      ← 요리사
        │                 ├─ collect_feeds()    RSS 수집
        │                 ├─ summarize(content) LLM 요약
        │                 └─ send_digest(user)  메일 발송
        ▼
FastAPI (API)            사용자/관심사 CRUD, 다이제스트 조회        ← 홀 서버
                          무거운 일은 직접 안 하고 워커에 위임
Redis                    작업 대기열 + 캐시                         ← 주문 전표 게시판
```

---

## 3. 도전한 전제와 보완 결정

기획서를 검토하며 짚은 빈틈과, 그에 대한 확정 처리.

| # | 짚은 점 | 확정 처리 |
|---|---------|-----------|
| 1 | Flask/FastAPI 미결정 | **FastAPI 확정** (위 2장) |
| 2 | `users`에 인증·가입 흐름 없음 | **MVP는 단일 유저(seed)로 시작. 스키마는 멀티유저(`user_id` FK 유지). 가입/로그인/JWT는 V2** |
| 3 | "관리자 페이지"는 스코프 크리프 | **별도 프론트 화면 X → FastAPI 자동 Swagger UI를 관리자 콘솔로 사용** |
| 4 | 실패 처리 부재 | **재시도/백오프, dead-letter, 발송 idempotency 명시 (5장)** — 포트폴리오의 진짜 볼거리 |
| 5 | 테스트 전략 없음 | **pytest + 가짜 LLM provider 주입. LLM 추상화가 여기서 값을 함** |
| 6 | 크롤링 ToS/차단 리스크 | **MVP는 RSS만으로 못 박음. Medium·네이버블로그 스크래핑 미약속** |
| 7 | 상시 EC2는 배치에 과함 | **docker-compose 재현 + 아키텍처 문서. 상시배포 안 함 (필요 시 Lambda+EventBridge)** |
| 8 | 필터링(2.3)과 추천(2.4)이 MVP에선 동일 기능 | **MVP는 점수 함수 하나(키워드 겹침). `user_events`는 깔아두되 행동기반 추천은 V4** |

---

## 4. 시스템 아키텍처

```
            ┌─────────────┐
            │ APScheduler │  매일 N시 → 작업을 Redis 큐에 등록
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │  Arq Worker │  async 백그라운드 실행
            └──────┬──────┘
                   ▼
  RSS 수집 → contents(DB) → LLM 요약(캐싱) → 키워드 추출
                                                │
                                                ▼
                                  관심도 점수 계산(키워드 겹침)
                                                │
                                                ▼
                                  일일 다이제스트 → Email(AWS SES)

  ┌──────────────┐
  │  FastAPI App │  사용자/관심사 CRUD + 다이제스트 조회 + /docs(Swagger)
  └──────────────┘

  공통: PostgreSQL(영속), Redis(큐+캐시)
```

**분리 원칙:** API는 즉시 응답, 무거운 일(수집·요약·발송)은 전부 워커로 위임.

---

## 5. 데이터 모델 & 핵심 메커니즘

기획서 5장을 기준으로, 확정된 메커니즘을 덧붙인다.

| 테이블 | 핵심 컬럼 | 메커니즘 |
|--------|----------|----------|
| `users` | id, email, nickname, created_at | MVP는 seed 1명. 비밀번호/인증은 V2 |
| `sources` | id, source_name, source_url, source_type | RSS URL 등록 |
| `contents` | id, source_id, title, content, original_url, published_at, **content_hash** | `content_hash`로 중복 차단 + 요약 캐시 키 |
| `summaries` | id, content_id, summary, keywords, reading_time | 본문 해시 기준 캐싱 → 같은 글 재요약 금지. **keywords는 JSONB 배열**(정규화된 canonical 태그, 필요 시 GIN 인덱스) |
| `user_interests` | id, user_id, keyword | 점수 계산 입력. **등록 시 키워드 정규화 함수 적용** (아래 적용 정책 참고) |
| `user_events` | id, user_id, content_id, event_type(view/click/save), created_at | V4 추천 엔진용 데이터 적재 (MVP는 쌓기만) |
| `digests` | id, user_id, **digest_date**, status, sent_at | 하루 한 통 발송 단위. **(user_id, digest_date) UNIQUE = 발송 idempotency의 실체** |
| `digest_items` | id, digest_id, content_id, **score** | 그날 다이제스트에 담긴 글 + 선정 당시 점수 스냅샷 → 점수 함수 품질 회고·V3/V4 개선의 측정 데이터 |

> **v1.1 변경:** 기존 `notifications(id, user_id, content_id, send_type, status)`를 `digests` + `digest_items`로 교체.
> 이전 스키마는 건별 발송 모델이라 (1) 문서가 약속한 (user, digest-date) 유니크 제약을 걸 컬럼이 없었고,
> (2) "하루치 한 통" 다이제스트(한 발송 = 여러 콘텐츠) 모델과 구조가 맞지 않았다. `send_type`(채널)은 멀티채널이 생기는 V2에서 `digests`에 복원.

### 비용 최적화 (확정)
- LLM 호출은 인터페이스로 추상화 → 모델 교체 + 테스트 더블 주입
- 요약·키워드는 저비용 모델(flash/mini/nano급)로 시작, 측정 후에만 승급
- **프롬프트 캐싱**으로 반복 시스템 프롬프트 비용 절감
- **예상 읽기 시간은 LLM이 아니라** 본문 글자수 ÷ 분당 속도로 직접 계산
- 출력은 **구조화(JSON)** 로 받아 파싱
- `content_hash` 캐싱으로 동일 콘텐츠 재요약 0회

### 실패 처리 (확정 — 신규)
- **재시도/백오프:** LLM·SES·RSS 호출은 Arq의 재시도 + 지수 백오프
  - **LLM 요약 경로엔 full jitter 적용** — 새 글 다수를 병렬로 요약하다 공유 rate limit(429)에 걸리면 작업들이 동시에 실패→동시에 재시도하며 thundering herd가 발생한다. 대기 시간을 `random(0, base × 2**attempt)`로 무작위화(full jitter)해 재시도 파도를 흩뿌린다. (Arq `Retry(defer=...)`에 이 값을 실어 보냄)
  - **RSS·SES엔 jitter 미적용 (의도된 생략)** — RSS는 피드마다 호스트가 달라 한 대상에 몰리지 않고, SES는 하루 1통(단일 유저)이라 herd가 없다. 불필요한 무작위화를 피하는 분별이지 누락이 아니다. → 두 경로는 결정론적 지수 백오프 그대로.
- **dead-letter:** N회 실패한 작업은 실패 상태로 기록(`summaries`/작업 결과)하고 파이프라인은 계속 진행 (한 건 실패가 전체를 막지 않음)
- **idempotency:** 파이프라인 재실행해도 (1) 요약은 `content_hash`로, (2) 발송은 `digests`의 (user_id, digest_date) 유니크 제약으로 중복 방지

### 관심도 점수 함수 (확정 — 키워드 겹침)

`user_interests.keyword`(집합 A)와 `summaries.keywords`(집합 B)를 비교해 숫자 하나를 만든다.
MVP는 **Jaccard 계수 하나로 못 박는다.** 아래는 검토한 측도와 그 출처.

| 방식 | 식 | 계열 | 성격 / 채택 여부 |
|------|-----|------|------------------|
| 교집합 크기 | `\|A∩B\|` | 기초 집합론 | 단순하지만 길이 편향 → 단독 사용 X |
| **Jaccard 계수** | `\|A∩B\| / \|A∪B\|` | 집합 유사도 | 0~1 정규화, 직관적 → **채택** |
| Overlap 계수 | `\|A∩B\| / min(\|A\|,\|B\|)` | 집합 유사도 | 작은 집합이 포함되면 1.0, 관대 → 보류 |
| Sørensen–Dice | `2\|A∩B\| / (\|A\|+\|B\|)` | 집합 유사도 | Jaccard의 단조변환, 교집합 가중 → 보류 |
| Tversky 지수 | `\|A∩B\| / (\|A∩B\| + α\|A∖B\| + β\|B∖A\|)` | 비대칭 일반화 | α·β로 비대칭 부여, 위 측도들의 상위 일반화 → MVP엔 과함 |

**채택: Jaccard.** 이유 (1) 0~1 정규화라 threshold·top-N 자르기가 직관적, (2) A·B 크기가 달라도 동작, (3) README에 한 줄로 근거 설명 가능.
Overlap 계수는 "유저 관심사가 콘텐츠 키워드에 다 포함되면 무조건 1.0"이라 변별력이 떨어져 보류.

**한계(중요):** Jaccard는 키워드 빈도(tf)·희소성(idf)을 무시하고, 정확 토큰 매칭이라 표기 흔들림에 약하다.
IR 교과서가 정확히 이 한계를 지적하며 tf-idf·코사인 유사도로 넘어간다(Manning et al. 2008, 6장).
`lede`에서 그 방향(가중 벡터·임베딩)은 **V3(벡터 검색)**이다. MVP는 키워드 겹침까지.

#### 적용 정책 (확정 — v1.1 신규)

측도(Jaccard)만큼 중요한 것이 **입력 품질과 절단 방식**이다. 다음 세 가지를 MVP에 포함한다.

1. **키워드 정규화 (통제 어휘)** — Jaccard의 최대 약점인 표기 흔들림(`도커`/`Docker`/`docker`, `람다`/`AWS Lambda`)은
   V3 임베딩 없이 생성 시점에 막는다. LLM 요약 프롬프트에서 키워드를 **canonical 형태(영문 소문자, 별칭 통일)**로
   출력하도록 강제하고, `user_interests` 등록 시에도 **동일한 정규화 함수**(소문자화 + 별칭 매핑 테이블)를 태워
   두 집합을 같은 공간에 놓는다. 토큰 비용 증가 거의 없음.
2. **선정 정책: 절대 threshold 대신 top-N** — 관심사 5개 × 콘텐츠 키워드 4~5개 수준의 작은 집합에서
   Jaccard 값은 0, 0.11, 0.25처럼 이산적이다. 절대 기준("0.3 이상")은 발송 분량이 날마다 널뛴다.
   **`score > 0` 중 상위 N건(기본 N=5), 동점은 `published_at` 최신순**으로 확정. 해당 글이 0건인 날은 발송 스킵.
   선정된 점수는 `digest_items.score`에 스냅샷으로 기록한다.
3. **관찰 트리거 (전환 조건 명시)** — 관심사가 많은 유저일수록 분모(합집합)가 커져 점수가 전반적으로
   깎이는 현상이 *측정되면*, 위 표의 Tversky 지수에서 α=0, β=1로 둔 비대칭형 `|A∩B|/|B|`
   ("콘텐츠 키워드 중 관심사에 닿는 비율")로 전환을 검토한다. 측정 전 선제 도입은 하지 않는다 — 본 문서의
   "측정 후에만 승급" 원칙과 동일.

#### 참고 출처
- **Jaccard 계수:** Jaccard, P. (1901). *Étude comparative de la distribution florale dans une portion des Alpes et des Jura.* Bulletin de la Société Vaudoise des Sciences Naturelles, 37, 547–579. (영문판: Jaccard, P. (1912). *The distribution of the flora in the alpine zone.* New Phytologist, 11(2), 37–50.)
- **Overlap 계수 (Szymkiewicz–Simpson):** 이름 귀속은 통설 수준이며 1차 출처가 불분명(위키피디아도 citation needed). 흔히 Simpson의 생물지리학 논문(1943·1947·1960)으로 거슬러 올라가고, IR 맥락의 "overlap" 용어는 McGill, Koll & Noreault (1979)에 등장.
- **Sørensen–Dice 계수:** Dice, L. R. (1945). *Measures of the amount of ecologic association between species.* Ecology, 26(3), 297–302.
- **Tversky 지수:** Tversky, A. (1977). *Features of similarity.* Psychological Review, 84(4), 327–352.
- **IR 관점 · Jaccard의 스코어링 한계 · tf-idf/코사인:** Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval.* Cambridge University Press. (6장 스코어링, 19장 near-duplicate/shingling. 전문 무료: nlp.stanford.edu/IR-book)

---

## 6. 검토한 접근 방식

### Approach A — 수직 슬라이스 우선 (채택) ✅
- **요약:** RSS 1개 → DB → 요약 1건 → 내 메일. 파이프라인 뼈대를 끝까지 관통 후 살 붙이기.
- **효과:** 가장 위험한 "수집→요약→전달 연결"을 1주 안에 검증. 이후 확장은 저위험.
- **재사용:** 기획서 7장 0단계가 이미 이 전략.

### Approach B — 기능별 수평 구축
- **요약:** 수집 모듈 완성 → 요약 모듈 완성 → 발송 모듈 완성 순으로.
- **단점:** 끝까지 연결되기 전엔 동작하는 게 없음. 통합 시점에 위험이 몰림. **기각.**

### Approach C — LLM 없이 규칙 기반 먼저
- **요약:** 요약을 LLM 대신 추출 요약(문장 스코어링)으로 먼저, 나중에 LLM 교체.
- **장점:** 비용 0으로 파이프라인 검증.
- **판단:** 불필요. LLM 추상화 레이어 + 가짜 provider로 같은 효과를 더 깔끔하게 얻음. 보류.

**채택: Approach A.** 포트폴리오에서 "동작하는 한 줄기"가 "미완성 여러 줄기"를 이긴다.

---

## 7. 빌드 순서

### 0단계 — 수직 슬라이스 (약 1주)
1. RSS 피드 **하나** 수집
2. DB에 원문 저장 (`content_hash` 포함)
3. LLM으로 3줄 요약 1건 생성 (추상화 레이어 통해)
4. 결과를 **내 이메일로** 발송 (SES)
- 동시에: docker-compose 뼈대(app+worker+postgres+redis), pytest 첫 통과

### MVP (약 2~4주)
- RSS 다중 소스 수집 + 중복 제거(URL 정규화 + content_hash)
- LLM 요약 (캐싱 적용)
- 관심사 등록 + 단순 점수 기반 필터링 (점수 함수 1개 + 키워드 정규화 + top-N 선정)
- Email 일일 다이제스트 발송 (idempotent)
- 실패 처리(재시도/백오프/dead-letter)
- Swagger UI = 관리자 콘솔
- pytest 커버리지 (가짜 LLM provider)

---

## 8. 배포 / 운영

- **docker-compose up** 한 줄로 전체 스택 재현 (app + worker + postgres + redis)
- README에 아키텍처 다이어그램 + 분리 설계 근거
- 기획서의 AWS EC2/RDS/S3는 **"이런 클라우드 아키텍처를 안다"는 설계 의도**로 README에 명시 (실제 상시배포는 안 함)
- 라이브 URL이 필요해지면 → 배치 성격에 맞는 **Lambda + EventBridge(cron)** 를 후속 마일스톤으로 (비용 거의 0). MVP 범위 아님.

### 이메일 발송 주의 (SES)
- SES는 초기 **샌드박스 모드** — 인증된 주소로만 발송 가능. MVP("내 메일")엔 무관.
- 멀티유저(V2) 전환 시 SES 프로덕션 액세스 승인 필요 → 알려진 게이트로 기록.

---

## 9. 성공 기준

- [ ] `docker-compose up` 한 줄로 전체 스택 기동
- [ ] RSS 다중 소스 → 요약 → 일일 다이제스트 이메일이 스케줄대로 자동 발송
- [ ] 같은 콘텐츠 재실행 시 재요약 0회, 중복 발송 0회 (idempotency 검증)
- [ ] 관심사와 키워드가 전혀 겹치지 않는 콘텐츠는 다이제스트에 미포함 (점수 함수 단위 테스트, 정규화 케이스 — 대소문자·한/영 별칭 — 포함)
- [ ] LLM 호출 실패가 전체 파이프라인을 멈추지 않음 (재시도 후 dead-letter)
- [ ] pytest가 가짜 LLM provider로 비용 0원에 파이프라인 통과
- [ ] LLM 비용을 측정된 숫자로 README에 제시 (캐싱 전/후 비교)

---

## 10. 향후 고도화 (기획서 8장 유지)

| 버전 | 내용 |
|------|------|
| V2 | 가입/로그인/JWT 인증, 멀티유저, Slack/Discord/Telegram 연동, SES 프로덕션 |
| V3 | 벡터 검색, 유사 콘텐츠 추천 |
| V4 | `user_events` 기반 개인화 추천 엔진, AI 에이전트 큐레이션 |
| V5 | SaaS 공개, 유료 구독 모델 검토 |

---

## 11. 미해결 질문

- LLM 공급자 1순위? (비용·한국어 요약 품질 고려 — 측정 후 결정)
- 다이제스트 발송 시각 (매일 1회·top-5는 확정, 시각과 사용자 설정은 V2)
- RSS 첫 소스 후보 (Velog/티스토리 등 한국어 기술블로그 중 RSS 안정적인 것)
- 통제 어휘(canonical 태그) 초안 확보 방법 — 수동 시드 목록 vs 첫 수집분 키워드에서 추출 후 정리

---

## 12. 세션에서 관찰한 점

- "비동기 파이프라인"을 내세우면서 워커는 sync(Celery)로 두는 흔한 함정을 피하고, FastAPI를 정하자마자 워커까지 async(Arq)로 통일하는 판단을 했다. 멘탈 모델 일관성을 중요하게 본다는 신호.
- 기획서 v1.1에 이미 `content_hash` 중복 차단, 요약 캐싱, 읽기 시간 직접 계산, LLM 추상화가 들어 있었다. 비용을 "측정 가능한 숫자"로 만들 줄 아는 사람의 설계.
- 결정을 던졌을 때 바로 고르지 않고 "Arq와 Celery는 어디에 쓰이는거야"를 먼저 물었다. 이름이 아니라 역할을 이해한 뒤 고르려는 태도 — 코드에서 우유부단함이 안 드러나는 사람의 습관.
