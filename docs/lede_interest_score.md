# 관심도 점수 계산 설계 — `lede`

> 성격: `DESIGN.md`의 보조 설계 문서 (관심사 기반 필터링의 점수 함수)
> 참조: `DESIGN.md` §3 #8(필터링/추천 통합), §4(아키텍처), §5(데이터 모델)
> 상태: MVP 확정 — **Jaccard 계수 1개**

---

## 1. 이 점수가 하는 일

`lede`의 MVP에서 "필터링(2.3)"과 "추천(2.4)"은 **하나의 점수 함수로 합쳐져 있다**(`DESIGN.md` §3 #8).
이 함수는 수집·요약된 콘텐츠가 사용자 관심사에 얼마나 맞는지를 숫자 하나로 매기고,
그 점수로 오늘치 다이제스트에 넣을 글을 거른다.

파이프라인 위치: Arq 워커에서 **요약 → 키워드 추출 직후**, (user, content)별로 계산(`DESIGN.md` §4).

---

## 2. 입력과 출력

| 구분 | 값 | 출처 |
|------|-----|------|
| 집합 A | 사용자 관심 키워드 (예: Python, AWS, Docker) | `user_interests.keyword` |
| 집합 B | 콘텐츠에서 LLM이 뽑은 키워드 | `summaries.keywords` |
| 출력 | 0~1 사이 점수 1개 | — |

MVP는 가중치 없는 평면 키워드 집합이다(관심사에 우선순위 없음).

---

## 3. 검토한 측도

| 방식 | 식 | 계열 | 성격 / 채택 여부 |
|------|-----|------|------------------|
| 교집합 크기 | `\|A∩B\|` | 기초 집합론 | 단순하지만 길이 편향 → 단독 사용 X |
| **Jaccard 계수** | `\|A∩B\| / \|A∪B\|` | 집합 유사도 | 0~1 정규화, 직관적 → **채택** |
| Overlap 계수 | `\|A∩B\| / min(\|A\|,\|B\|)` | 집합 유사도 | 작은 집합이 포함되면 1.0, 관대 → 보류 |
| Sørensen–Dice | `2\|A∩B\| / (\|A\|+\|B\|)` | 집합 유사도 | Jaccard의 단조변환, 교집합 가중 → 보류 |
| Tversky 지수 | `\|A∩B\| / (\|A∩B\| + α\|A∖B\| + β\|B∖A\|)` | 비대칭 일반화 | α·β로 비대칭 부여, 위 측도들의 상위 일반화 → MVP엔 과함 |

> 관계 메모: **α=β=1 → Jaccard, α=β=0.5 → Dice**. 즉 Tversky가 둘을 특수 케이스로 품는다.
> Jaccard와 Dice는 서로 단조변환 관계라 **점수 순위가 항상 같다.**

---

## 4. 추천 방식과 이유 — Jaccard 채택

**채택: Jaccard 계수.**

근거:
1. **정규화** — 0~1로 떨어져 threshold·top-N 자르기가 직관적이다.
2. **크기 불변** — 관심사 수와 콘텐츠 키워드 수가 달라도 공정하게 비교된다(합집합으로 나누므로).
3. **설명 가능성** — README/면접에서 한 줄로 근거를 댈 수 있다.

기각/보류한 이유:
- **Overlap 계수:** "유저 관심사가 콘텐츠 키워드에 다 포함되면 무조건 1.0"이 돼서 변별력이 떨어진다.
- **Sørensen–Dice:** Jaccard와 순위가 동일 → 굳이 바꿀 이유가 없다(설명이 더 단순한 쪽 선택).
- **Tversky:** 비대칭 가중이 필요한 단계가 아니다(MVP엔 과함). V3 이후 후보.

> 포트폴리오 포인트: 대안을 알고도 **의도적으로 Jaccard를 골랐다**는 서사가
> "그것밖에 몰라서 썼다"보다 강하다 — Arq vs Celery를 트레이드오프로 설명하는 것과 같은 결.

---

## 5. 진짜 함정 — 키워드 매칭 정규화

점수 공식은 쉽다. **조용히 깨지는 곳은 그 위의 "매칭"이다.**
LLM이 키워드를 자유 텍스트로 뱉기 때문에:

- 대소문자: `Python` vs `python`
- 표기 흔들림: `AWS` vs `Amazon Web Services`
- 부분 일치: 관심사 `AWS` ↔ 콘텐츠 `AWS Lambda` (정확히 안 같아 교집합에서 빠짐)

**처리(확정):** 교집합 계산 **전에** 양쪽을 정규화 — 최소한 소문자화 + 공백 trim.
**부분 일치(contains)는 MVP에서 채택하지 않는다** — `Go`가 `Google`에 걸리는 등 오탐을 부른다.
정확 토큰 매칭으로 시작하고 일부 누락은 감수한다.

---

## 6. 점수 활용 방식 *(미결 — 다음 결정)*

계산된 점수를 어떻게 자를지:
- **threshold 고정값** — 점수 ≥ 임계값인 글만 발송. 양 조절이 어려움(많거나 0건일 수 있음).
- **top-N** — 점수 상위 N개만 발송. 다이제스트 분량이 일정.

단일 seed 유저 + 하루치 다이제스트 한 통이라는 `lede` 맥락에선 **top-N이 분량 관리에 유리**해 보이나,
점수 분포를 측정한 뒤 확정한다.

---

## 7. 한계와 다음 단계

Jaccard는 **단어 빈도(tf)·희소성(idf)을 무시**하고, 정확 토큰 매칭이라 의미 유사를 못 잡는다.
정보검색 교과서가 정확히 이 한계를 지적하며 tf-idf·코사인 유사도로 넘어간다(아래 출처 [5], 6장).

`lede`에서 그 방향(가중 벡터·임베딩·의미 검색)은 **V3(벡터 검색)**이다(`DESIGN.md` §10).
행동 데이터 기반 가중은 **V4**. MVP는 키워드 겹침까지.

> 스코프 경계: "키워드 매칭이 빡빡한데 의미로 묶으면?" → 임베딩 = **V3**. MVP에서 끌어오지 않는다.

---

## 8. 참고 출처

각 출처를 **도래(어떻게 나왔나) → 요약(핵심) → 결말(어디로 갔나)** 으로 정리.

> 신뢰도 메모: [1] Jaccard, [2] Overlap, [5] IR 교과서는 1차 출처까지 확인.
> [3] Dice, [4] Tversky는 확립된 지식 기반. 특히 [2]의 인물 귀속은 통설 수준(아래 명시).

### [1] Jaccard 계수 — Jaccard (1901, 1912)
- **도래:** 스위스 식물학자 Paul Jaccard가 알프스 고산 식물 분포 비교를 위해 1901년 *coefficient de communauté*로 발표. (1884년 G. K. Gilbert가 기상예보 검증용으로 선행, 화학에선 Tanimoto가 독립 재발견.)
- **요약:** 교집합 ÷ 합집합. 0~1. "겹치는 양"을 합집합으로 정규화.
- **결말:** 생태학에서 출발해 IR·추천·텍스트 마이닝·ML의 사실상 표준 집합 유사도. **`lede` 채택 측도.**
- 인용: Jaccard, P. (1901). *Étude comparative de la distribution florale dans une portion des Alpes et des Jura.* Bulletin de la Société Vaudoise des Sciences Naturelles, 37, 547–579. (영문판: Jaccard, P. (1912). *The distribution of the flora in the alpine zone.* New Phytologist, 11(2), 37–50.)

### [2] Overlap 계수 — Szymkiewicz–Simpson
- **도래:** 1차 출처 불분명(위키피디아도 *citation needed*). 흔히 G. G. Simpson의 생물지리학 논문(1943·1947·1960, 대륙별 동물상 유사도)으로 거슬러 올라가며, IR 맥락의 "overlap" 용어는 McGill, Koll & Noreault (1979)에 등장.
- **요약:** 교집합 ÷ 작은 집합 크기. 한쪽이 통째로 포함되면 1.0. Jaccard보다 관대.
- **결말:** 크기 차 큰 집합 비교(작은 워크숍 vs 거대 학회 등)에 유용, 생물정보학·네트워크 분석에서 사용. `lede`에선 변별력 저하로 **보류.**

### [3] Sørensen–Dice 계수 — Dice (1945), Sørensen (1948)
- **도래:** 미국 생태학자 L. R. Dice(1945, 종 간 연관도)와 덴마크 식물학자 T. Sørensen(1948, 식물 군집 비교)이 독립적으로 고안.
- **요약:** 2 × 교집합 ÷ (A+B 크기). Jaccard와 단조변환 관계(순위 동일), 교집합에 2배 가중.
- **결말:** 생태학·이미지 분할(Dice 손실 ≈ F1)·NLP에서 사용. `lede`에선 Jaccard와 순위 동일 → **보류.**
- 인용: Dice, L. R. (1945). *Measures of the amount of ecologic association between species.* Ecology, 26(3), 297–302.

### [4] Tversky 지수 — Tversky (1977)
- **도래:** 인지심리학자 Amos Tversky가 "사람의 유사성 판단은 비대칭"이라는 관찰에서 특징 대비 모델로 제안.
- **요약:** 교집합 ÷ (교집합 + α·A만 + β·B만). α·β로 비대칭 부여. **Jaccard·Dice의 상위 일반화.**
- **결말:** 인지심리학 고전이자 비대칭 유사도가 필요할 때 사용. `lede` MVP엔 **과함**(가족 관계를 보여주는 참고로 수록).
- 인용: Tversky, A. (1977). *Features of similarity.* Psychological Review, 84(4), 327–352.

### [5] Introduction to Information Retrieval — Manning, Raghavan, Schütze (2008)
- **도래:** 스탠퍼드 C. Manning, P. Raghavan, 슈투트가르트 H. Schütze가 검색엔진 시대 IR을 정리한 표준 교과서. Cambridge University Press, 전문 무료 공개(nlp.stanford.edu/IR-book).
- **요약:** 색인·랭킹·tf-idf·벡터 공간 모델 전반. 6장에서 Jaccard의 스코어링 한계(tf·idf 무시, 길이 정규화 부족)를 지적하고 tf-idf·코사인으로 전환.
- **결말:** IR·NLP 입문의 정전. `lede`의 단계(MVP 키워드 겹침 → V3 벡터)가 이 교과서 서사와 일치 — "단순 겹침에서 시작해 측정 후 승급"이 정석임을 뒷받침.
- 인용: Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval.* Cambridge University Press. (6장 스코어링, 19장 near-duplicate/shingling.)
