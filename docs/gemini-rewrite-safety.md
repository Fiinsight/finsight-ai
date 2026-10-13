# Gemini 수집 리라이팅 안전장치 확인 (2026-10-13)

## 서버 상태

- 웹 8081: HTTP 200, 백엔드 8080: UP, AI 8001: ok.
- 재시작 시 startup 옵션이 중복되어 false,false로 해석된 백엔드 오류를 복구했습니다.
- 이번 검증 재시작은 `--finsight.news.collection.on-startup=false --finsight.feedback.on-startup=false`를 각 1회만 전달했습니다. 정규 스케줄과 기본값은 유지합니다. 강제 수집/판정 배치는 실행하지 않았습니다.

## 반영 파일과 동작

- AI config/.env.example: 수집 전용 flag, 하루 30건, 최소 6초, 프로세스 20회 유지. 실제 .env는 허용된 7개 설정만 변경했고 커밋하지 않습니다.
- llm_client/rewrite_budget: 단일 실행 잠금, KST 일일 ledger, 성공 기사 캐시, 429 환불·다음 수집 재시도, 당일 3회 차단, 제공자 Gemini 제한, JSON 형식 고정 및 숫자/문장 검증 실패 발췌.
- news router/main: allow_llm/retryable 계약과 키 없는 health 통계.
- 백엔드 NewsCollectionScheduler/NewsAssembler: 최대 10개 슬롯에만 LLM 허용, 순차 실행, 429 표시 기사만 다음 정상 수집에 재시도.
- AiRewriteRequest/Response·News·NewsRepository·V13: 새 필드/저장. V13은 ADD COLUMN IF NOT EXISTS이며 이전 마이그레이션을 수정하지 않았습니다.
- startup 제어 설정은 기존 데이터를 건드리는 재시작 배치를 피하기 위해 추가했고 기본 true입니다.

## 테스트

- AI pytest: 122개 통과. Gemini는 전부 mock입니다. 테스트 fixture는 실제 제공자 호출을 기본 차단합니다.
- 백엔드 ./gradlew test: 성공. JUnit {'tests': 169, 'failures': 0, 'errors': 0, 'skipped': 4}, 내부 Python 7개 통과. V13 포함 prod migration/validate는 PR CI에서 확인합니다.
- 프런트: 변경 없음. 앞선 학습 흐름 PR의 typecheck 및 78개 테스트는 통과했습니다.

## 실제 호출 결과와 제한

| 기사 | 호출 | 결과 | DB 변경 |
|---|---:|---|---|
| 333 삼성전자·반도체 기사 | 최초 허용 1회 | 출력 검증 실패 → EXCERPT | 없음 |
| 319 IMF 한국 성장률 전망 기사 | 사용자가 추가 허용한 1회 | 원문에 없는 숫자 검출 → EXCERPT | 없음 |

실제 호출은 총 2회입니다. 추가 호출/일괄 재생성을 하지 않았습니다. REWRITTEN 저장 및 초보자 4~5문장 해요체의 실제 성공 확인은 **미완료**입니다. 검증을 느슨하게 하거나 생성 숫자를 임의로 수정하지 않았습니다. 실패 응답은 발췌로 제공되어 앱과 수집을 중단하지 않습니다. 첫 호출은 당시 유형 로그만 있어 정확한 검증 항목은 확인되지 않았고, 두 번째 호출은 숫자 검증 실패 로그를 확인했습니다.

성공한 리라이팅이 없으므로 생성된 3수준 리라이팅 결과를 보고할 수 없습니다. 후속 확인은 별도 승인받은 새 기사 1건 또는 다음 정상 수집에서 해야 합니다. 원문 허용 수치 목록 및 연도/단위 환산 금지 지시를 프롬프트에 보강했습니다.

## /health (키 없음)

```json
{
  "rewriteDay": "2026-10-13",
  "rewriteSuccessCount": 0,
  "rewriteFailureCount": 2,
  "rewrite429Count": 0,
  "rewriteUsedCalls": 2,
  "rewriteDailyLimit": 30,
  "rewriteStoppedToday": false,
  "rewriteLast429At": null,
  "rewriteEnabled": true,
  "provider": "gemini",
  "rewriteMinIntervalSeconds": 6.0,
  "processCallLimit": 20,
  "processCalls": 1,
  "status": "ok",
  "useRealLlm": false,
  "llmEnabled": false,
  "llmProvider": "disabled",
  "llmFallback": true,
  "llmMode": "fallback",
  "llmTimeoutSeconds": 20.0,
  "realEmbeddingsEnabled": false,
  "sentimentModel": {
    "mode": "rule_fallback",
    "configured": false
  }
}
```

## 남은 리스크

- Gemini 실제 출력의 숫자 준수와 REWRITTEN 성공 검증이 남았습니다. 현재는 실패 시 안전하게 발췌합니다.
- Google 무료 등급은 키 문자열만으로 검증되지 않습니다. 프로젝트 결제 설정에 따라 요금 등급이 달라지므로 호출 상한은 과금 자체의 보증이 아닙니다. [공식 결제 문서](https://ai.google.dev/gemini-api/docs/billing)
- 프로세스 20회가 하루 30건보다 먼저 도달하면 그 프로세스에서는 추가 생성이 제한됩니다. 429는 하루 슬롯에서 제외하되 실제 네트워크 시도이므로 프로세스 횟수에는 포함합니다.
- CI 및 병합은 백그라운드에서 확인합니다. 실제 생성 성공 확인이 끝나지 않아 AI PR은 초안으로 보존하며, 의존 백엔드 PR도 선행 AI 검증 전 병합하지 않습니다.
