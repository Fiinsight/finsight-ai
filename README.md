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

실제 모델을 사용하더라도 실패하면 서비스가 중단되지 않고 경고 로그와 안전한 폴백 응답을 반환합니다. 따라서 졸업작품 시연은 무료 로컬 모드로 진행하고, 품질 비교가 필요할 때만 제한적으로 실제 모델을 켜는 방식입니다.

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
# {"status":"ok","useRealLlm":false}
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
| `ANTHROPIC_API_KEY` | 빈 값 | 실제 LLM을 선택했을 때만 사용 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | 실제 호출 모델 |
| `ML_SENTIMENT_MODEL_PATH` | 빈 값 | 학습한 감성 모델 경로 |
| `CHROMA_HOST` / `CHROMA_PORT` | `localhost` / `8000` | 선택적 로컬 벡터 저장소 |

실제 키와 학습 산출물은 저장소에 커밋하지 않습니다.

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

