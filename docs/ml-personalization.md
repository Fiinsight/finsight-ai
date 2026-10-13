# ML3 · 무료 로컬 금융 감성

[KR-FinBert-SC 모델 카드](https://huggingface.co/snunlp/KR-FinBert-SC)를 기준으로 NEGATIVE/NEUTRAL/POSITIVE를 판정합니다. 모델의 config id2label(0 negative, 1 neutral, 2 positive)을 읽으며 API는 경로에 설치된 파일만 local_files_only=True로 엽니다. 신뢰도 0.6 미만은 NEUTRAL입니다. 확률은 감성 분류의 모델 신뢰도이며 투자 수익 확률이 아닙니다.

## 선택 설치 (자동 실행하지 않음)

별도 ML 가상환경에서 `pip install -r requirements-ml.txt` 후 다음을 사용합니다. 모델 가중치/로컬 인덱스는 artifacts 아래에서 관리하고 커밋하지 않습니다. API 기본 requirements.txt에는 ML 의존성을 추가하지 않습니다.

```sh
python -c "from huggingface_hub import snapshot_download; snapshot_download('snunlp/KR-FinBert-SC', local_dir='artifacts/kr-finbert-sc')"
export ML_SENTIMENT_MODEL_PATH="$PWD/artifacts/kr-finbert-sc"
```

문서의 다운로드 명령은 안내용입니다. 이 PR/CI에서는 모델 다운로드·외부 추론·유료 LLM 호출을 실행하지 않습니다. 모델/의존성이 없거나 추론이 실패하면 기존 금리/환율 방향 및 키워드 규칙을 사용합니다.

## 오프라인 점수 배치

DB_URL/DB_USERNAME/DB_PASSWORD는 호출 환경에서 이미 export된 값을 사용합니다. 스크립트는 .env를 읽거나 수정/출력하지 않습니다. V12 적용 후:

```sh
python -m scripts.score_sentiment --limit 1000
# 대상 확인 뒤 운영자가 명시적으로 선택하는 쓰기 명령(이 작업에서 실행하지 않음)
python -m scripts.score_sentiment --limit 1000 --apply
```

제목 + 정제 본문 리드만 입력합니다. 기본은 읽기 전용 DB 연결로 scanned/would_change 건수만 출력합니다. --apply일 때에도 변경 건수를 먼저 출력하고, 원래 감성/신뢰도가 그대로인 행만 갱신합니다. 작업 전체는 트랜잭션이며 수집 스케줄러나 앱 요청에 연결하지 않았습니다. limit은 검사 범위이므로 출력 건수는 그 범위의 값입니다.

## 도슨트·피드백

백엔드는 저장된 sentiment_hint와 sentiment_confidence를 AI 계약으로 전달합니다. 0.6 이상 방향성 분류만 호재/악재 가능성 표현에 사용하며 낮은 신뢰도는 중립 안내로 처리합니다. 감성만으로 DIRECT/MARKET 관계, 실제 결과, 정답 여부를 바꾸지 않습니다. relation은 기존 기사·종목 관련성 분류입니다. 뉴스가 가격 변화의 원인이라고 단정하지 않습니다. API가 없으면 백엔드 규칙도 같은 신뢰도 기준을 사용합니다. 이미 저장된 피드백/영속 도슨트 결과는 재생성하지 않습니다.

## 평가

datasets/sentiment_eval.jsonl은 **100개 빈 라벨 슬롯**입니다. title, label(NEGATIVE/NEUTRAL/POSITIVE), labelled_by를 사람이 채운 뒤:

```sh
python -m scripts.evaluate_sentiment
```

규칙 vs 모델 정확도 표와 혼동행렬(행=실제, 열=예측)을 출력합니다. 라벨 100개 또는 모델이 없으면 '평가 준비 필요/모델 미설정'을 표시하며 가짜 점수나 규칙 점수를 모델 점수로 보고하지 않습니다. 이번 작업은 실제 모델·사람 라벨의 정확도를 측정하지 않았습니다.

## 이번 작업의 읽기 전용 대상 확인

로컬 DB 301건, 규칙 기준 감성 방향 변경 후보 82건, 신뢰도 신규 저장 후보 301건입니다. 모델 설치 전이므로 모델 기준 변경 수는 미측정입니다. --apply는 실행하지 않았습니다. 운영 데이터에 대한 수정이나 배포도 실행하지 않았습니다.
