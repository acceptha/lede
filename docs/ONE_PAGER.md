# lede — AI Newsletter Curator · One-Pager

**RSS 수집 → LLM 요약 → 관심사 점수 필터 → 일일 다이제스트 이메일** 을 자동화하는 비동기 배치 파이프라인.
백엔드 3역량(**비동기 파이프라인 · 실패 처리 · 비용 최적화**)을 깊게 증명한 개인 프로젝트.
`Python 3.12 · FastAPI · Arq · APScheduler · PostgreSQL/pgvector · Redis · Docker` · Repo: github.com/acceptha/lede

---

### 핵심 (30초 요약)
- **비동기 3분할**(API·워커·스케줄러) + `docker compose up` **한 줄 재현**(마이그레이션·seed·스케줄러 자동)
- **provider 3중 추상화**(LLM·임베딩·이메일) → 공급자 **코드 0줄 수정** 교체, 테스트 **비용 $0**
- **idempotency를 DB 제약으로**(content_hash·발송 UNIQUE) → 재요약 0 · 중복 발송 0
- **실패 처리**: 재시도(LLM=jitter / RSS·발송=결정론) · 실패 격리 · **dead-letter retry-then-park** · JSON 관측
- **점수 전략 교체**: Jaccard(토큰) ↔ 임베딩 코사인(의미), pgvector 저장

### 측정 (근거)
| | LLM 호출 | 토큰 | 시간 |
|---|:---:|:---:|:---:|
| 캐시 미적용(재요약) | 3 | 4,229 | 79.7s |
| 캐시 적용(재실행) | **0** | **0** | ~0s |

의미 매칭: `AI↔인공지능` Jaccard **0.0** → 임베딩 코사인 **0.828** (토큰 안 겹쳐도 의미로 매칭)

### 규모/품질
테스트 **61개**(단위 54 + 통합 7) · GitHub Actions **CI 2잡 녹색** · 기능 단위 증분 커밋(conventional commits)

### 파이프라인
`collect_feeds → summarize_pending → embed_pending → build_and_send_digest` (매일 스케줄, 전 단계 멱등)

### 더 보기
README(전체) · docs/DESIGN.md(설계 SSOT) · docs/PORTFOLIO.md(상세 정리) · docs/OLLAMA.md(로컬 LLM)
