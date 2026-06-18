# Ollama 도입 가이드 — 로컬 LLM provider

> `lede`의 요약 단계에서 쓰는 LLM을 **로컬·무료**로 돌리기 위한 Ollama 설정 문서.
> 작성: 2026-06 / 대상: 로컬 개발 환경(Windows)

---

## 1. 왜 Ollama인가 (선택 이유)

### 배경
- 요약 품질·비용 측정을 위해 실제 LLM provider가 필요했고, 1순위로 **Anthropic(Claude Haiku)** 을 붙였다.
- 그러나 **Anthropic API 결제가 막혀**(크레딧 충전 불가) 실제 호출이 `400 (credit balance too low)`로 차단됐다.
- 결제 없이 쓸 수 있는 대안을 검토했다.

### 검토한 선택지

| 옵션 | 비용 | 키/결제 | 한국어 | 특징 |
|------|------|---------|--------|------|
| Anthropic (Claude) | 유료 | 크레딧 필요 | 우수 | 결제 막혀 보류 |
| Gemini 무료 티어 | $0(한도) | 무료 키(카드 불필요) | 우수 | 클라우드, 키 발급 필요 |
| **Ollama (로컬)** | **$0** | **불필요** | 양호(모델 따라) | **완전 로컬 API**, 결제·키 없음 |

### 채택: Ollama
1. **비용 $0 · 결제/키 불필요** — 내 PC에서 모델이 직접 돌아간다.
2. **로컬 API** — `localhost:11434`에 REST 서버를 띄우므로, 기존에 Anthropic API로 보내던 요청을 **내 PC 안 서버로 보내는 것**으로 바뀔 뿐이다. (사용자가 원했던 "로컬에서 api 쓰는 방법"이 정확히 이것)
3. **LLM 추상화의 값어치 증명** — 파이프라인 코드는 `LLMProvider` 프로토콜만 알기 때문에, provider만 갈아끼우면 **코드 0줄 수정**으로 전환된다 (절대규칙 1).
4. **재현성** — docker-compose 재현 철학과도 맞고, 인터넷 없이도(모델 다운로드 후) 동작한다.
5. **데이터 로컬** — 본문이 외부로 나가지 않는다.

> 비유: docker가 컨테이너를 로컬에서 돌리듯, Ollama는 LLM을 로컬에서 돌린다.

### 모델 선택: EXAONE 3.5 (한국어 특화)
수집 콘텐츠(어피티 등)가 **한국어**라, 한국어 능력이 요약 품질을 좌우한다.

| 모델 | 크기 | 한국어 | 비고 |
|------|------|--------|------|
| **`exaone3.5:2.4b`** | ~1.6GB | 최상 | LG 한국어 특화. **기본 채택** |
| `exaone3.5:7.8b` | ~4.8GB | 최상 | 품질↑, 사양 여유 있으면 |
| `qwen2.5:3b` | ~2GB | 양호 | 범용 다국어 대안 |

→ 한국어 뉴스 요약이라 **EXAONE 3.5 2.4b**를 기본값으로 둔다. `OLLAMA_MODEL` 환경변수로 교체 가능.

---

## 2. 설치 방법 (Windows)

### 2-1. Ollama 설치
```powershell
winget install Ollama.Ollama
```
- `winget`이 없으면 https://ollama.com/download/windows 에서 설치 프로그램 사용.
- 설치 후 Ollama는 **백그라운드 서비스 + 트레이 아이콘**으로 자동 실행되며 `localhost:11434`에서 서빙한다.
- ⚠️ 설치 직후 **새 터미널 창**을 열어야 `ollama` 명령이 PATH에 잡힌다.

### 2-2. 한국어 모델 다운로드 (~1.6GB)
```powershell
ollama pull exaone3.5:2.4b
```
- 진행률 바가 끝까지 가고 `success`가 떠야 완료.

### 2-3. 설치 확인
```powershell
ollama list                       # 목록에 exaone3.5:2.4b가 보이면 성공
curl http://localhost:11434/api/tags   # {"models":[...]} 에 모델이 있으면 정상
```
> `{"models":[]}` 이면 서버는 떠 있지만 모델이 아직 안 받아진 상태 → `ollama pull` 재실행.

---

## 3. 프로젝트 연동

코드는 이미 `app/llm/providers/ollama.py`에 구현돼 있다. **환경변수만 설정**하면 된다.

`.env` (gitignore됨):
```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:2.4b
```

- **호스트(내 PC)에서 워커/스크립트 실행 시**: 위 그대로 (`localhost:11434`).
- **docker 컨테이너(worker)에서 host의 Ollama 사용 시**: 컨테이너 안에서는 `localhost`가 컨테이너 자신을 가리키므로 host를 가리키게 바꾼다.
  ```
  OLLAMA_BASE_URL=http://host.docker.internal:11434
  ```

### 동작 방식 (요약)
```
summarize_pending 잡
  └─ summarize_content(title, body, provider)
       └─ provider.summarize(title, text)   ← OllamaProvider
            └─ POST localhost:11434/api/chat
               { model, messages, format(JSON 스키마), stream:false }
            ← {"message":{"content": "<스키마에 맞는 JSON>"}}
       → LLMSummary(summary_lines, keywords)
```
- 구조화 출력은 Ollama의 `format`(JSON 스키마)으로 강제 → `LLMSummary`로 검증.
- 비용 $0, rate limit 없음. 실패는 모두 `LLMError`로 격리되고, 잡 재실행이 곧 재시도(멱등성).

---

## 4. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `curl_exit=7` / connection refused | Ollama 미실행 | 트레이 확인 또는 `ollama serve` |
| `{"models":[]}` | 모델 미다운로드 | `ollama pull exaone3.5:2.4b` |
| `404 model not found` | 모델명/태그 불일치 | `ollama list`의 이름과 `OLLAMA_MODEL` 일치 |
| 첫 호출 타임아웃 | 모델 메모리 로딩(느림) | 타임아웃 여유(기본 120s) / 한 번 워밍업 |
| 컨테이너에서 연결 안 됨 | `localhost`가 컨테이너 자신 | `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| 한국어 요약 품질 아쉬움 | 작은 모델 한계 | `exaone3.5:7.8b` 등 상위 모델로 교체 |

---

## 5. 참고
- Ollama: https://ollama.com
- EXAONE 3.5 (LG AI Research): Ollama 라이브러리의 `exaone3.5` 태그
- 코드: `app/llm/providers/ollama.py`, 분기: `app/llm/factory.py`, 설정: `app/config.py`
- 설계상 LLM의 역할·추상화: [DESIGN.md](./DESIGN.md) §5
