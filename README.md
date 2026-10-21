# FinSight AI·딥러닝 서비스

> 2026 졸업작품 FinSight의 FastAPI AI 마이크로서비스

FinSight는 경제 뉴스를 초보자도 이해할 수 있게 바꾸고, 뉴스의 근거를 바탕으로 투자 판단을 연습하도록 돕는 서비스입니다. 이 저장소는 Spring Boot 백엔드가 내부적으로 호출하는 AI 계층입니다.

## 현재 제공하는 기능

- `POST /ai/news/rewrite`: beginner / normal / analyst 수준별 뉴스 재작성
- `POST /ai/terms/explain`: 금융 용어의 정의·기사 맥락·시장 영향 설명
- `POST /ai/feedback/judgement`: 사용자의 판단과 실제 결과를 비교한 피드백
- Chroma 기반 용어 설명 캐시와 서버 장애 시 인메모리 폴백
- 무료로 실행할 수 있는 한국어 뉴스 감성 분류·의미 검색 baseline

## 비용 없이 동작하는 구조

기본값은 `USE_REAL_LLM=false`입니다. 이 상태에서는 외부 LLM을 호출하지 않고 검증용 응답을 사용하므로 API 키와 결제 없이 앱·백엔드 연동을 테스트할 수 있습니다. 실제 LLM은 명시적으로 스위치를 켜고 키를 넣었을 때만 사용합니다.

실제 모델 호출은 provider 계정/프로젝트의 요금제에 따라 비용이 발생할 수 있습니다. Gemini도 계정·모델별 무료 한도와 유료 한도가 다르므로 무료라고 가정하지 않습니다. `USE_REAL_LLM=true`를 직접 설정하기 전에는 외부 LLM을 호출하지 않습니다. 실제 호출에는 요청 시간 제한과 자동 재시도 비활성화를 적용하고, 실패 시 fallback 응답을 반환합니다.

임베딩은 LLM 호출과 별도 과금 경로입니다. `USE_REAL_LLM=true`만으로 OpenAI 임베딩이 켜지지 않으며, `USE_REAL_EMBEDDINGS=true`와 `OPENAI_API_KEY`를 모두 설정해야만 호출됩니다. 기본값은 false입니다.

## 딥러닝 계획

GPU 서버가 없어도 데이터 정리, 평가셋 작성, baseline 학습, API 연결 테스트는 노트북에서 진행할 수 있습니다. 학교 GPU 서버를 사용하게 되면 다음 순서로 확장합니다.

1. 한국어 금융 뉴스에 상승·중립·하락 라벨을 만들고 시간 순서로 train/validation/test를 분리합니다.
2. 사전학습 한국어 문장 모델을 뉴스 분류에 fine-tuning해 키워드 규칙 baseline과 비교합니다.
3. 문장 임베딩과 FAISS/Chroma 검색으로 비슷한 과거 뉴스와 판단 사례를 찾습니다.
4. 모델의 예측, 근거 문장, 유사 사례를 함께 반환해 사용자가 결과를 검증할 수 있게 합니다.
5. 정확도만 보지 않고 F1, 시간 누수 여부, 근거의 일관성, 실제 판단 피드백 품질을 평가합니다.

딥러닝이 수익률을 보장하는 구조는 아닙니다. 이 프로젝트에서는 예측을 단정하는 대신 뉴스 이해와 판단 회고를 돕는 보조 모델로 사용합니다.

## 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

헬스 체크:

```bash
curl http://localhost:8001/health
# llmEnabled=false, llmFallback=true, llmMode="fallback"이면 외부 LLM 비활성 상태
```

ML 의존성은 필요할 때만 설치합니다.

```bash
pip install -r requirements-ml.txt
python scripts/train_sentiment.py
```

## 주요 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `USE_REAL_LLM` | `false` | 실제 LLM 호출 여부. 비용 발생 가능성이 있는 스위치 |
| `LLM_PROVIDER` | `claude` | `claude`/`gemini` 또는 배치 전용 `ollama`; 기본 비용 플래그는 false |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `20` | 외부 LLM의 최대 요청 시간(초), 자동 재시도 없음 |
| `ANTHROPIC_API_KEY` | 빈 값 | 실제 LLM을 선택했을 때만 사용 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | 실제 호출 모델 |
| `GEMINI_API_KEY` | 빈 값 | Gemini를 명시적으로 선택·활성화했을 때만 사용 |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | 실제 호출 모델 |
| `USE_REAL_EMBEDDINGS` | `false` | OpenAI 유료 임베딩 별도 opt-in |
| `OPENAI_API_KEY` | 빈 값 | `USE_REAL_EMBEDDINGS=true`일 때만 임베딩에서 사용 |
| `ML_SENTIMENT_MODEL_PATH` | 빈 값 | 학습한 감성 모델 경로 |
| `CHROMA_HOST` / `CHROMA_PORT` | `localhost` / `8000` | 선택적 로컬 벡터 저장소 |

실제 키와 학습 산출물은 저장소에 커밋하지 않습니다.

`/health`의 `llmEnabled`, `llmFallback`, `llmMode`, `llmProvider`, `realEmbeddingsEnabled`는 현재 설정 모드를 표시하며 키 값은 노출하지 않습니다. LLM 호출은 제한 시간 내 실패하거나 quota/rate limit 오류가 나면 기존 안전 응답으로 되돌아갑니다. 이 저장소 테스트는 provider SDK를 모킹하므로 실제 API나 유료 quota를 호출하지 않습니다.

## 프로젝트 구조

```text
app/                  FastAPI 앱과 AI 라우터
app/services/         LLM 진입점, 벡터 캐시, 뉴스 분석
ml/                   감성 분류·검색 baseline
scripts/              로컬/학교 GPU 학습 스크립트
datasets/             비식별화된 샘플·스키마
tests/                API와 서비스 테스트
```

## 앞으로의 계획

- 실제 뉴스·판단 데이터 수집 동의와 비식별화 정책 확정
- 시간 기반 평가셋과 재현 가능한 학습 설정 추가
- 감성 분류 결과를 백엔드 뉴스 도메인과 연결
- 유사 뉴스 근거를 피드백 화면에 노출
- 학교 GPU 학습 모델을 CPU 추론 가능한 artifact로 export

### Backend local retrieval adapter (free fallback)

`POST /v1/search` accepts the backend's authorized `documents`, `kind`,
`query`, `topK`, time window and case owner. It preserves document IDs,
source URLs and actual publication times, returns at most 600-character
excerpts and sorts by lexical score. This is explicitly `RULE_FALLBACK`,
not a semantic-model result. No provider calls, model downloads or persistent
user-record index are involved. Missing publication times exclude news/case
candidates; case search requires matching owners.

Run the adapter on the backend's existing local port:

```sh
USE_REAL_LLM=false USE_REAL_EMBEDDINGS=false .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Set `FINSIGHT_LOCAL_ML_ENABLED=true` and
`FINSIGHT_LOCAL_ML_BASE_URL=http://127.0.0.1:8002` in the backend environment
when using this free adapter. Explicit process variables override `.env`,
so setting both cost flags to false cannot be undone by `.env` loading.

### 무료 수준별 학습 설명

`POST /ai/news/learning` (`title`, `body`, `level`)은 기사 발췌의 문장 수와
초급 표현을 조정하고 별도 읽기 가이드를 반환합니다. `mode=RULE_FALLBACK`이며
딥러닝 생성 결과가 아닙니다. 수치·출처를 만들어내지 않고 발췌는 600자로 제한합니다.
사용자 답변과 복습 상태는 백엔드가 계정별로 저장하며 AI 서비스에는 전송하지 않습니다.


### 차트 도슨트 (`POST /ai/chart/docent`)

지점별 DIRECT/MARKET/NONE 규칙 설명과 최대 3건 뉴스 근거를 반환합니다. 기본 `DOCENT_WITH_LLM=false`이며 다른 LLM 플래그와 독립적입니다. 켜더라도 KST 하루 `MAX_DAILY_DOCENT_CALLS=30`과 기존 공통 호출 상한을 함께 적용하고 분봉은 항상 RULE입니다. 숫자·인과 단정 검증 실패와 오류는 RULE로 저장하며 같은 키를 다시 호출하지 않습니다.

`DOCENT_LEDGER_PATH` 기본값 `data/chart_docent.sqlite3`를 지속 볼륨에 보관해야 재시작 후에도 결과/일일 한도를 유지합니다. 키는 종목·시점·기간·대표 뉴스·수준입니다. RULE로 먼저 저장된 키는 플래그 변경만으로 업그레이드하지 않습니다. 실제 초기 LLM 생성에는 비용이 발생할 수 있습니다. 테스트는 mock만 사용합니다.


### 구조화된 판단 피드백

`POST /ai/feedback/judgement`는 `verdict`, `headline`, `summary`, `reasons:[{title,detail}]` 2~3개, `nextTip`을 반환합니다. 기사 리드·사용자 근거·실제 비교 데이터를 각각 사용하고, 무근거 칭찬/새 수치/인과 단정을 막습니다. 방향 일치라도 절대 변동률 1.0% 이하이면 PARTIAL입니다. UNKNOWN은 판정하지 않고 verdict=null입니다.

기존 `feedback`, `is_aligned`, `next_learning_point` 별칭을 유지합니다. USE_REAL_LLM=false 기본 규칙 모드와 기존 상한은 그대로이며, 실제 LLM 테스트는 mock만 사용합니다. 선택적 지수 비교 수치가 없으면 생성하지 않습니다.

## ML4 · 배치 전용 Ollama 리라이팅 (선택)

기존 `REWRITE_WITH_LLM` 기본값은 false, `USE_REAL_LLM` 기본값도 false입니다. provider=ollama는 **수집 후 별도 배치에서만** 사용합니다. `/ai/news/rewrite` 등 앱 요청은 Ollama를 실행하지 않고 EXCERPT를 반환하며, 백엔드는 배치가 DB에 저장한 REWRITTEN 결과를 표시합니다. 다른 기능은 Ollama 설정에서 유료 제공자로 넘어가지 않습니다.

아래는 사용자가 로컬에서 실행하는 설치 안내입니다. 이 PR/CI에서 설치·다운로드·실제 생성은 실행하지 않았습니다.

```sh
brew install ollama
ollama pull qwen2.5:7b
ollama serve
# Ollama 실행 상태에 따라 기존 서버를 그대로 사용합니다.
```

환경 파일을 수정하지 않고 별도 배치 터미널에서 다음 값을 export합니다:

```sh
export USE_REAL_LLM=false
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
export REWRITE_WITH_LLM=true
```

OLLAMA_BASE_URL 기본값은 http://localhost:11434, OLLAMA_MODEL 기본값은 빈 값입니다. base URL은 localhost/127.0.0.1/::1의 HTTP(S)만 허용하며 HTTP 리디렉션을 따르지 않습니다. SDK/유료 API/다운로드 경로는 추가하지 않았습니다. DB 배치만 실행할 환경에는 선택 드라이버 `pip install 'psycopg[binary]>=3.2,<4'`가 필요합니다. DB 접속 변수는 이미 export된 DB_URL/DB_USERNAME/DB_PASSWORD를 사용하며 값을 출력하지 않습니다.

```sh
# 새 수집 cohort를 명시합니다. 기본은 대상 건수만 확인(모델 호출/DB 쓰기 없음).
python -m scripts.rewrite_news_batch --since 2026-10-13T09:00:00+09:00 --limit 10
# 운영자가 새 대상만 확인한 뒤 명시적으로 적용할 때 사용하는 명령입니다.
python -m scripts.rewrite_news_batch --since 2026-10-13T09:00:00+09:00 --limit 10 --apply --output artifacts/rewrite-quality.jsonl
python -m scripts.check_level_quality --input artifacts/rewrite-quality.jsonl --output artifacts/level-quality.md
```

예시 since는 그대로 복사하지 말고 **새로 수집하기 시작한 시각**을 지정하세요. 기존 기사 전체 재생성 명령은 제공하지 않습니다. 이미 REWRITTEN인 DB 기사와 영속 ledger에서 처리한 기사에는 모델을 다시 호출하지 않습니다. 처리 완료된 EXCERPT도 다음 배치에서 건너뛰며, 명시한 범위의 최신 1000건 중 아직 처리하지 않은 최대 limit건을 선택합니다. 프로세스 상한에 도달하면 미처리 기사를 예약하지 않고 배치를 멈춥니다. EXCERPT로 수집된 새 기사만 명시한 범위에서 처리합니다. 기사당 3수준 JSON을 한 번에 생성하고 JSON 파싱 실패에만 1회 재시도합니다. 숫자·부호/문장 수/해요체/분석 칸 중복/투자 권유 검증 실패 및 타임아웃은 EXCERPT로 남습니다. 요청 타임아웃은 120초, 기존 일일 기사 상한(기본 50)과 공유 프로세스 호출 상한(기본 20)을 유지합니다. JSON 재시도도 프로세스 상한에 포함됩니다.

원문·제목·저장값이 생성 중 바뀐 행은 저장하지 않습니다. ledger와 DB를 한 트랜잭션으로 묶지 않으므로 모델 결과를 ledger에 남긴 뒤 DB 저장이 실패한 경우 같은 입력으로 재실행해 저장만 복구할 수 있습니다. 이미 처리한 같은 기사의 입력이 바뀌면 재생성하지 않고 배치 대상에서 제외합니다. ledger 파일은 지속 저장해야 기사당 재호출 제한을 유지할 수 있습니다.

품질 비교 도구의 --input 모드는 저장된 최대 10개 기사에서 원문/3수준 발췌/3수준 LLM의 3열 표만 만들며 모델을 호출하지 않습니다. 기존 --title/--body/--base-url 통계 검사 모드는 유지합니다. 실제 한국어 품질·사실 보존은 사용자가 로컬에서 비교해야 합니다. 처리 시간은 측정하지 않았습니다. 테스트는 Ollama HTTP mock만 사용하고 CI는 모델을 다운로드하거나 Ollama 서버를 실행하지 않습니다.

API 형식 참고: [Ollama generate](https://docs.ollama.com/api/generate).

### Optional judgement feedback polishing

`FEEDBACK_WITH_LLM=false` is the default. Rule feedback compares the article signal, user reason and the same target/index closing interval, and returns the backend-selected `conceptTerm`/`conceptDefinition`. No model is called by default.

Opt-in supports only the existing Gemini provider, with a separate KST ledger capped at 50 attempts/day, cached identical results, the existing 20-call process ceiling, and the shared rewrite lock/minimum interval. The feedback key includes `FEEDBACK_PROMPT_VERSION` and the KST date: the same input/prompt version calls the model at most once per day. A rejected model response keeps RULE for that day's input; changing the prompt version bypasses older wording without resetting the daily cap. A non-Gemini provider, provider/ledger failure, invalid JSON, invented numbers, missing source quotes or praise without a user reason returns RULE. Claude/OpenAI dispatch is not enabled by this flag. `USE_REAL_LLM` remains independent. Gemini usage may incur charges; the user decides whether to add `FEEDBACK_WITH_LLM=true` to `.env` with the existing Gemini provider/key configured. No real call or environment-file change was made for this feature.

Backend request adds `concept_term`, `concept_definition`, `judgement_id`; response adds `conceptTerm`, `conceptDefinition`, `mode`. Definitions are sourced from the local dictionary and are never generated. Model tests use HTTP/provider mocks and temporary ledgers.

The prompt supplies decision facts rather than a full rule answer: verdict, original lead, checked rationale quality, market relation and a possible miss cause. The model must explain who did what in this article and its possible earnings/cost/demand/rate channel. NO_SIGNAL with an individual move points to other company/industry news; other market relations point to outside market/order-flow factors with data limits.

Before validation, missing article quotations and neutral-band guidance are added only within sentence limits. A repeated last article sentence is removed only if at least two article sentences remain; quoted periods are preserved. Numeric, verdict, source and coaching checks remain mandatory. Rejection codes use WARNING logs without the user's rationale text. First reason detail allows 2–4 sentences, rationale coaching 1–3, and market comparison 1–2 (3 for beginner's separate closing-price definition). General learning principles are conditional explanations, never assertions of new company results, investor trades or a confirmed cause.

After deciding on the optional flag, stop the old AI process and start it from this repository with `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001`. Follow the backend README's stop → clean/test → restart → dry-run → apply → pending-feedback sequence. Neither a model call nor a regrade request is part of the automated tests; provider responses and ledgers are isolated even if the local environment enables the flag.
