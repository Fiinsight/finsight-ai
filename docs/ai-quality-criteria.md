# FinSight AI MVP 품질 기준

이 기준은 GPU 학습 모델이 없는 로컬 모드에서도 반복 실행할 수 있는 최소 품질 기준이다.

## 뉴스 리라이팅 (#1)

- 세 수준 모두 원문에 실제로 있는 사실을 포함한다.
- beginner는 analyst보다 전문 용어와 문장 길이가 적다.
- 원문에 없는 수치, 기업, 원인, 전망을 추가하지 않는다.
- `detectedTerms`는 원문에 등장한 용어만 반환한다.

## 문맥 기반 시장 영향·용어 설명 (#2)

- 시장 방향의 근거는 입력 기사 문장 또는 그 문장에 포함된 핵심어로 추적 가능해야 한다.
- 긍정·부정 신호가 함께 있으면 NEUTRAL과 낮은 confidence를 사용한다.
- 기사 맥락이 없으면 일반론으로 시장 영향을 단정하지 않는다.

## 예측 피드백 (#3)

- `isAligned`는 `user_choice == market_result`의 대소문자 무시 비교와 일치해야 한다.
- 정답·오답·중립 모두 결과 방향과 판단 방향을 명시한다.
- 확정적 수익 보장 표현 대신 시점·거시 변수·수급 등 한계를 안내한다.

## 평가 실행 (#4)

```bash
pytest
python scripts/mini_eval_run.py --base-url http://localhost:8001
python scripts/check_level_quality.py --base-url http://localhost:8001
```

`mini_eval_articles.json`은 10개 기사, 리라이팅 3수준, 용어 설명, 피드백 정합성을 확인하는 작은 회귀 데이터셋이다. `mini_eval_results.json`은 실행 결과 산출물이며, 점수는 모델 품질의 최종 증명이 아니라 회귀 감지용으로만 사용한다.
