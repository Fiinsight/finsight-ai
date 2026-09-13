# FinSight AI Service (finsight-ai)

FinSight(핀사이트)는 초보 투자자가 경제 뉴스를 쉽게 이해하고, 뉴스를 읽은 뒤 스스로 투자 판단을
연습해볼 수 있도록 돕는 서비스입니다. 이 저장소(`finsight-ai`)는 그중 **AI 서비스(FastAPI)** 부분으로,
뉴스 리라이팅 · 금융 용어 설명 · 판단 피드백 생성을 LLM 기반으로 담당하는 독립 마이크로서비스입니다.
사용자가 직접 호출하는 서버가 아니라, Spring Boot 백엔드가 내부적으로 호출하는 형태로 동작합니다.

## 이 서비스가 하는 일

### 1. `POST /ai/news/rewrite` — 뉴스 리라이팅

뉴스 제목/본문과 사용자 레벨(`beginner` / `normal` / `analyst`)을 입력받아, 해당 레벨에 맞게
재구성된 요약과 "이 뉴스가 왜 중요한지", 기사에 등장한 핵심 금융 용어 목록을 반환합니다.
내부적으로는 한 번의 LLM 호출로 초보자용·일반용·분석용 세 가지 버전을 모두 생성한 뒤, 요청받은
레벨의 버전만 골라 응답합니다.

### 2. `POST /ai/terms/explain` — 금융 용어 설명

용어와 기사 맥락을 입력받아 "정의 / 이 뉴스에서의 의미 / 시장 영향" 3단 구조로 설명합니다.
같은 용어를 같은 맥락에서 다시 물어보면, LLM을 다시 호출하지 않고 Chroma에 저장된 이전 응답을
그대로 재사용합니다(RAG 캐싱). 이는 같은 질문에 매번 비용을 지불하지 않도록 하기 위함입니다.

### 3. `POST /ai/feedback/judgement` — 판단 피드백

사용자가 뉴스를 보고 예측한 방향(UP/NEUTRAL/DOWN)과 실제 시장 결과를 비교해, 판단이 맞았는지
여부와 그 이유를 2~4개의 짧은 근거 목록으로 반환합니다.

## `USE_REAL_LLM` 스위치 — 비용은 여기서만 발생합니다

이 서비스는 **기본값이 목업(가짜 응답) 모드**입니다. `.env`의 `USE_REAL_LLM`이 `false`(기본값)인
동안에는 위 세 엔드포인트 모두 실제 LLM API를 전혀 호출하지 않고, 미리 준비된 자연스러운 한국어
응답을 반환합니다. 따라서 데모/스크린샷/프론트엔드·백엔드 연동 테스트를 API 키 없이, 비용 없이
바로 진행할 수 있습니다.

`.env`에서 `USE_REAL_LLM=true`로 바꾸고 `ANTHROPIC_API_KEY`를 채워 넣으면, 그 순간부터
`app/services/llm_client.py`가 실제 Anthropic(Claude) API를 호출합니다. 이때 사용할 모델은
`ANTHROPIC_MODEL` 환경변수로 지정하며 기본값은 저비용 모델인 `claude-haiku-4-5`입니다.

이 프로젝트에서 **금전적 비용이 발생하는 지점은 정확히 이 하나뿐**입니다 — `USE_REAL_LLM=true`이고
실제로 LLM 호출이 이루어지는 순간. 만약 실제 호출이 실패하더라도(키 오류, 네트워크 문제, 요청 한도
초과 등) 서비스는 500 에러를 내지 않고 경고 로그만 남긴 뒤 자동으로 목업 응답으로 대체합니다.

## Chroma 기반 RAG 캐싱 구조

`app/services/vector_store.py`는 Chroma 벡터 DB(`term_explanations` 컬렉션)를 이용해 용어 설명을
캐싱합니다. Chroma 자체는 무료로 로컬에서 돌릴 수 있는 벡터 DB이므로 `USE_REAL_LLM` 값과 관계없이
항상 연결을 시도합니다.

- 용어를 처음 물어보면: LLM(또는 목업)이 설명을 생성 → 그 결과를 임베딩과 함께 Chroma에 저장.
- 같은 용어 + 같은 맥락을 다시 물어보면: 임베딩 유사도 검색으로 캐시를 찾아 LLM을 재호출하지 않고
  즉시 응답.
- `USE_REAL_LLM=false`일 때는 임베딩도 텍스트 해시로 만든 결정적(deterministic) 가짜 벡터를
  사용합니다 — 같은 텍스트는 항상 같은 벡터가 되므로 저장/조회 흐름 자체는 실제와 동일하게
  검증할 수 있습니다. `USE_REAL_LLM=true`일 때는 OpenAI `text-embedding-3-small`로 실제 임베딩을
  생성합니다(이 호출도 실패 시 자동으로 가짜 임베딩으로 대체됩니다).
- Chroma 서버가 꺼져 있거나 `docker-compose`를 아직 안 띄운 경우에도 서비스는 죽지 않습니다.
  연결 실패를 감지하면 경고 로그를 한 번만 남기고, 메모리 안에서 동작하는 간단한 딕셔너리
  기반 저장소로 자동 전환하여 계속 동작합니다(재시작 시 캐시는 초기화됩니다).

## 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

헬스 체크(현재 `USE_REAL_LLM` 상태도 함께 확인 가능):

```bash
curl http://localhost:8001/health
# {"status":"ok","useRealLlm":false}
```

## 환경변수

필요한 환경변수는 로컬 `.env`에 설정하세요. 실제 API 키 값은 절대 저장소에 커밋하지 마세요.

| 변수명 | 기본값 | 설명 |
| --- | --- | --- |
| `USE_REAL_LLM` | `false` | `true`일 때만 실제 Claude API를 호출합니다. 비용이 발생하는 유일한 스위치입니다. |
| `ANTHROPIC_API_KEY` | (빈 값) | `USE_REAL_LLM=true`일 때 사용할 Anthropic API 키. |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | 실제 호출 시 사용할 모델 ID. 필요에 따라 쉽게 교체 가능. |
| `OPENAI_API_KEY` | (빈 값) | 용어 캐싱용 임베딩(`text-embedding-3-small`) 생성에 사용. `USE_REAL_LLM=true`일 때만 호출. |
| `CHROMA_HOST` | `localhost` | Chroma 서버 호스트. |
| `CHROMA_PORT` | `8000` | Chroma 서버 포트. |

## 프로젝트 구조

```
app/
  config.py              # 환경변수 로딩 (.env)
  main.py                # FastAPI 앱, 라우터 등록, /health
  routers/
    news.py               # POST /ai/news/rewrite
    terms.py               # POST /ai/terms/explain
    feedback.py             # POST /ai/feedback/judgement
  services/
    llm_client.py          # LLM 호출 단일 진입점 (목업 ↔ 실제 Claude 전환)
    vector_store.py         # Chroma RAG 캐싱 (실패 시 인메모리 폴백)
```
