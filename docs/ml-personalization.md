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

DB_URL/DB_USERNAME/DB_PASSWORD는 호출 환경에서 이미 export된 값을 사용합니다. 스크립트는 .env 값을 수정/출력하지 않습니다. V12 적용 후:

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

# ML2 · 로컬 기사 임베딩과 관심 추천

[ko-sroberta-multitask 모델 카드](https://huggingface.co/jhgan/ko-sroberta-multitask)를 기준으로 제목 + 정제 본문 앞 500자를 벡터화합니다. 유료 API·외부 임베딩 서비스는 사용하지 않습니다. sentence-transformers/numpy/DB 드라이버는 requirements-ml.txt의 선택 설치에만 있습니다(기본 requirements.txt 불변).

## 수동 인덱스 준비

```sh
# 별도 ML 환경에서 기본/선택 의존성을 준비한 뒤, 사용자가 실행하는 다운로드 안내
python -c "from huggingface_hub import snapshot_download; snapshot_download('jhgan/ko-sroberta-multitask', local_dir='artifacts/ko-sroberta')"
python -m scripts.embed_news --model "$PWD/artifacts/ko-sroberta" --output artifacts/news-index
export ML_NEWS_INDEX_PATH="$PWD/artifacts/news-index"
```

DB_URL/DB_USERNAME/DB_PASSWORD는 export된 환경을 사용합니다. .env 값을 출력·수정하지 않습니다. DB 연결은 읽기 전용이고 수집 스케줄러에서 실행하지 않습니다. 운영자가 수동/크론으로 실행합니다. 이번 작업에서는 모델 다운로드/실제 DB 임베딩 배치를 실행하지 않았습니다.

기존 ml/retrieval.py, build_news_index.py, news_retrieval.py를 재사용합니다. index.npz 한 파일에 정규화 float32 벡터와 모델/기사 id/정제 내용 메타데이터를 원자적으로 저장합니다. 기존 embeddings.npy + metadata.json 검색도 지원합니다. 증분 배치는 기사 id가 있는 동일 모델 인덱스만 확장하며 이미 있는 id는 재인코딩하지 않습니다. 모델 변경 또는 id 없는 옛 인덱스는 별도 디렉터리가 필요합니다. 로컬 파일 잠금으로 동시 수동/크론 배치의 갱신 유실을 방지합니다. API는 파일 변경 후 새 인덱스를 읽으며 앱 요청 시 모델을 다운로드하지 않습니다.

## 관심 벡터와 추천

최근 30일 저장된 퀴즈 오답 1.0, 메모 0.8, 판단 0.6과 기기 읽기 0.3을 기사별로 합산합니다. 관심 벡터는 `sum(weight × normalized_article_vector) / sum(weight)`이며 코사인 계산에서는 다시 정규화해 분모가 상쇄됩니다. 이전 답변/읽기 시간은 기존 저장 정밀도 범위만 사용합니다(퀴즈는 마지막 답, 읽기는 한국 날짜 단위). 메모는 updated_at, 판단은 created_at을 사용합니다.

GET `/api/learning/recommendations?readNewsIds=...`는 인증된 사용자의 행동만 조회합니다. readNewsIds는 기기 저장소에서 최근 30일 읽은 id 최대 200개이며 서버 읽기 기록 테이블을 만들지 않습니다. 모든 저장 행동 기사와 전달된 읽은 기사, 제목이 거의 같은 사건을 제외하고 최근 30일 후보(최대 300개)에서 최대 3개를 추천합니다. 각 추천의 reasonNewsId/reasonTitle은 실제 그 사용자 행동 기사이며, 반환 시 서버 데이터로 재확인해 외부 응답의 제목을 그대로 신뢰하지 않습니다. 홈 핵심 3개 선별은 변경하지 않습니다.

AI `/ai/news/recommendations`는 사전 계산된 벡터만 사용하므로 추천 요청에는 모델 추론이 없습니다. 인덱스/선택 의존성이 없으면 백엔드는 기존 용어·종목·제목 규칙으로 관심 추천, 행동이 없으면 최신 기사 안내로 대체합니다. cold start에는 개인 행동 근거를 만들지 않습니다. 학습 탭에서 추천 기사/근거와 읽기 바로가기를 표시합니다.

같은 사건 중복은 URL/거의 같은 제목의 근사 규칙입니다. 제목이 크게 다른 동일 사건을 완벽히 구분하지 못하며, 정확한 사건 클러스터 라벨은 별도 검토가 필요합니다. 코사인은 의미 유사도이며 사실 검증/주가 원인이 아닙니다.

## 관련 뉴스 (News A)

`/v1/search`의 news 검색과 `/ai/news/similar`는 인덱스/로컬 모델이 있으면 코사인 순위를 사용합니다. News A는 기존 날짜/공개 문서/종목/중복 필터와 후보 id를 유지합니다. basis=LOCAL_SENTENCE_TRANSFORMER이며, 미설정/누락/추론 실패 시 기존 규칙 결과와 basis=RULE_BASED_FALLBACK을 유지합니다. query 인코딩에 모델을 쓸 때도 local_files_only=True입니다. 평가 전 qualityValidated는 false입니다. 기존 News A 어댑터 사용에는 FINSIGHT_LOCAL_ML_ENABLED=true 및 FINSIGHT_LOCAL_ML_BASE_URL을 해당 AI 서비스 주소로 지정해야 하며 기본 비활성 설정은 바꾸지 않았습니다.

## 발표 평가

datasets/retrieval_eval.jsonl에는 비슷함/다름 30쌍 **합성 검토 초안**(suggested_similar)과 비어 있는 사람 라벨(similar,labelled_by)을 제공합니다. 직접 검토해 similar를 true/false로 채운 뒤:

```sh
python -m scripts.evaluate_retrieval --model "$PWD/artifacts/ko-sroberta" --threshold 0.7
```

규칙과 임베딩 정확도 비교표를 출력합니다. 0.7은 초기 비교 임계값이며 실데이터로 보정되지 않았습니다. 사람이 확인한 30쌍/모델이 없으면 미준비/미설정으로 표시하고 정확도를 꾸며내지 않습니다. 실제 모델 성능 평가는 아직 미실행입니다. mock 벡터 테스트로 가중 평균/읽음 제외/근거/중복/새 id만 처리/인덱스 실패 fallback을 검증합니다.
