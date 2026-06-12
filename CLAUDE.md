# lede — AI Newsletter Curator

RSS 수집 → LLM 요약 → 관심사 점수 필터 → 일일 다이제스트 이메일을 자동화하는 배치 파이프라인.
백엔드 포트폴리오 프로젝트. 화려한 기능보다 **비동기 파이프라인 설계, 실패 처리, 비용 최적화의 깊이**를 증명하는 것이 목적.

상세 설계는 아래 문서가 단일 진실 공급원(SSOT)이다. 이 파일과 충돌하면 설계 문서를 따르고, 이 파일의 갱신을 제안하라.

- 기획(무엇을): @docs/PROJECT_PLAN.md
- 설계(어떻게/왜): @docs/DESIGN.md

## 현재 단계

**0단계 — 수직 슬라이스** (DESIGN.md §7)
RSS 피드 1개 → DB 저장(content_hash 포함) → LLM 요약 1건 → 내 이메일로 발송.
이 한 줄기를 끝까지 관통하는 것이 목표. 이 단계에서 다중 소스, 점수 함수, 사용자 API는 만들지 않는다.

<!-- 단계 전환 시 이 섹션만 갱신: 0단계 → MVP → V2... -->

## 기술 스택 (확정 — 변경 제안 금지)

- Python 3.12+ / **FastAPI** (API) / **Arq** (워커) / **APScheduler** (스케줄러, worker 컨테이너 내 별도 프로세스)
- PostgreSQL (영속) / Redis (Arq 큐 + 캐시)
- Docker / docker-compose (app + worker + postgres + redis)
- 테스트: pytest + **가짜 LLM provider 주입**
- Celery는 검토 후 의도적으로 기각됨 (DESIGN.md §2). 제안하지 말 것.

## 명령어

```bash
docker-compose up                 # 전체 스택 기동 (성공 기준: 이 한 줄로 재현)
docker-compose up -d postgres redis   # 로컬 개발 시 인프라만
pytest                            # 전체 테스트 (LLM 실호출 0회여야 함)
pytest -x -q tests/test_pipeline.py   # 파이프라인 빠른 검증
alembic upgrade head              # DB 마이그레이션 적용
alembic revision --autogenerate -m "msg"  # 마이그레이션 생성
ruff check . && ruff format .     # 린트 + 포맷
```

<!-- 실제 파일 구조가 잡히면 명령어를 현행화할 것 -->

## 절대 규칙

1. **LLM 추상화**: LLM SDK(openai, anthropic 등)는 `app/llm/providers/` 안에서만 import한다. 파이프라인 코드는 provider 인터페이스만 안다. 테스트는 항상 FakeProvider를 주입한다 — pytest 실행 중 실제 LLM 호출이 1회라도 발생하면 버그다.
2. **Idempotency**: 파이프라인은 언제든 재실행 가능해야 한다. 요약은 `content_hash`로 캐싱(같은 글 재요약 0회), 발송은 `digests(user_id, digest_date)` UNIQUE 제약으로 중복 방지. 새 작업을 추가할 때마다 "두 번 실행하면?"을 자문하라.
3. **비용**: 예상 읽기 시간은 LLM에 묻지 않는다 — 글자 수 ÷ 분당 속도로 계산. 요약은 저비용 모델로 시작, 측정 없이 상위 모델로 승급 금지. LLM 출력은 구조화(JSON)로 받는다.
4. **async 일관성**: API와 워커 모두 async. 파이프라인에 sync 블로킹 I/O를 넣지 않는다 (DB는 async 드라이버, HTTP는 httpx async).
5. **실패 격리**: 한 콘텐츠의 요약 실패가 파이프라인 전체를 멈추면 안 된다. N회 재시도 후 dead-letter 기록하고 계속 진행. LLM 호출 재시도에만 full jitter 적용, RSS·SES는 결정론적 백오프 (DESIGN.md §5 — 의도된 구분).
6. **키워드 정규화**: LLM 키워드 출력과 `user_interests` 등록에 동일한 정규화 함수(소문자화 + 별칭 매핑)를 적용한다. 한쪽만 정규화하면 점수 함수가 망가진다.

## 스코프 가드 (하지 말 것)

- 크롤링/스크래핑 코드 작성 금지 — MVP는 **RSS만** (ToS 리스크, DESIGN.md §3-6)
- 가입/로그인/JWT 구현 금지 — MVP는 seed 유저 1명, 인증은 V2
- 관리자 프론트엔드 금지 — FastAPI 자동 Swagger UI(`/docs`)가 관리자 콘솔
- 벡터 검색/임베딩/행동 기반 추천 금지 — V3/V4. MVP 점수 함수는 **Jaccard + top-N(기본 5) + published_at 동점 처리** 하나로 못 박음
- AWS 상시 배포 코드 작성 금지 — docker-compose 재현이 산출물
- `user_events`는 적재만 한다. MVP에서 읽어서 추천에 쓰지 않는다.

## 코드 컨벤션

- 타입 힌트 필수, Pydantic v2로 요청/응답 및 LLM 출력 스키마 검증
- 설정은 환경변수 → pydantic-settings. 시크릿 하드코딩 금지, `.env`는 gitignore
- DB 스키마 변경은 반드시 Alembic 마이그레이션으로 (수동 DDL 금지). 테이블 정의는 DESIGN.md §5를 따른다
- 구조화 로깅(JSON) — 모니터링 도구 대신 로그 + 작업 결과 테이블로 관측 (Flower 안 씀)

## Git 규칙

이 레포는 포트폴리오다 — **커밋 히스토리도 산출물**이다. 리뷰어가 읽는다는 전제로 커밋하라.

- 메시지: conventional commits. scope 사용 — `feat(collector):`, `feat(llm):`, `fix(digest):`, `test(scoring):`, `chore(docker):`, `docs:`
- 제목은 영어 명령형 50자 이내. 본문에는 "왜"를 쓴다 (무엇은 diff가 말해준다). 설계 결정과 연결되면 본문에 `DESIGN.md §N` 참조
- 커밋 단위: 하나의 논리적 변경 = 하나의 커밋. "여러 작업을 한 덩어리로" 커밋하지 말 것. 마이그레이션은 그것을 사용하는 코드와 같은 커밋에
- 커밋 전 `ruff check . && pytest` 통과 필수. 깨진 상태로 커밋하지 않는다
- 커밋 메시지에 Claude 코오서/Generated-with 푸터 붙이지 않는다
- `git push`는 명시적으로 요청받았을 때만. `--force`, `--no-verify`, 히스토리 재작성(rebase/amend로 푸시된 커밋 수정) 금지
- `.env`, 시크릿, `__pycache__` 등은 커밋 금지 — 스테이징 전 `git status`로 확인

## 작업 방식

- 새 기능 전에 DESIGN.md의 해당 섹션을 먼저 확인하고, 설계와 다르게 구현해야 한다면 코드부터 쓰지 말고 이유를 설명하라
- 설계 결정 변경이 필요하면 DESIGN.md 수정을 먼저 제안 (문서가 SSOT)
- 성공 기준(DESIGN.md §9)에 영향을 주는 변경은 해당 항목을 명시적으로 언급
- 모든 파이프라인 작업(collect/summarize/send)에는 단위 테스트를 함께 작성. 점수 함수 테스트에 정규화 케이스(대소문자, 한/영 별칭) 포함
