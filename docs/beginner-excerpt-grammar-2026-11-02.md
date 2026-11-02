# 초보자 EXCERPT 문법 수정과 수동 재생성 계획

## 수정

- 서술 동사 치환은 `(?=[.!?]|$)` 경계에서만 적용합니다. 간접 인용의 `기록했다고`는 그대로 두고 문장 끝 `밝혔다`만 `밝혔어요`로 바꿉니다. `내다봤다`도 문장 끝에서 변환합니다.
- 용어 치환 목록에는 용어만 남겼습니다. `컨센서스를` → `시장 전문가들의 예상을`처럼 받침이 달라지는 치환에서도 은/는·이/가·을/를·과/와를 맞춥니다.
- 초보자 중요도 문구와 용어 설명, 같은 파일의 직접 결합 조사 템플릿에 `_with_particle`를 사용합니다.
- 초보자 본문과 초보자 중요도 인용에서 괄호·대괄호형 및 단독 6자리 종목코드를 제거합니다. 금액 단위·통화기호가 있는 수치, 소수·쉼표가 있는 금액, 연도는 보존합니다. 기존 여러 종목 요약도 금액·연도가 있는 문장은 축약하지 않습니다.
- 일반·분석용의 원문 종목코드는 유지합니다. 숫자나 주가 방향을 새로 만들지 않습니다.

재현 예시의 수정 결과:

```text
삼성전자가 3분기 영업이익 12조1000억원을 기록했다고 31일 밝혔어요.
같은 기간의 매출·이익과 일회성 요인을 확인해요.
```

## 검증

`USE_REAL_LLM=false REWRITE_WITH_LLM=false .venv/bin/python -m pytest` 전체 통과.

- 간접 인용 4종, 직접 인용, 받침/모음 조사 4쌍, 중요도 5개 변수 템플릿.
- 종목코드 3형태 및 구두점, 연도·한국식 금액·6자리 금액·소수·통화기호 숫자 보존.
- `tests/fixtures/collected_excerpt_articles.json`: 운영 DB에서 읽은 실제 수집 기사 20개. 기사별 id·출처·URL·발행시각을 기록하고 본문은 노이즈를 제거한 300자 이하의 짧은 발췌만 저장했습니다. 이 fixture에서 `어요고`, `어요라고`, 검사한 잘못된 조사 및 잔존 6자리 종목코드 패턴은 0건입니다. 한국어 전체 문법에 오류가 없다는 일반화는 아닙니다.
- 새 유지보수 모드는 mock DB로 dry-run 무생성/무쓰기, 최근 7일 범위 제한, 무료 경로, 중요도 문구 포함 저장, 스냅샷 보호·동시 변경 스킵, 동일 결과 무쓰기, 잘못된 결과 거부를 검사합니다.

## 기존 저장값은 자동 갱신되지 않음

backend NewsAssembler는 저장된 요약이 있고 retry_pending이 아니면 재작성하지 않습니다. 새 AI 코드만 배포해도 기존 DB 요약·중요도 문구는 그대로입니다.

기존 backend `scripts/backfill_rewrites.py`는 Gemini 활성화를 요구하고 REWRITTEN 성공 결과만 저장합니다. 현재의 무료 EXCERPT 문법 수정에는 사용할 수 없으며, 그 도구를 실행하거나 유료 LLM을 켜지 않았습니다.

대신 기존 AI `scripts/rewrite_news_batch.py`의 guarded manual batch에 `--excerpt`를 추가했습니다. 기존 DB 연결 도구와 읽기 전용 기본값을 재사용합니다.

- `allow_llm=False`로 직접 호출하므로 Gemini/Ollama/Claude 호출과 예전 rewrite budget 캐시를 사용하지 않습니다.
- published_at이 최근 7일 이내이고 미래 시각이 아닌 EXCERPT만 대상으로 합니다. 예전 --since를 입력해도 7일보다 오래된 값으로 확장하지 않습니다.
- NULL/REWRITTEN 모드는 보존합니다. 원문·제목·URL·발행시각·모드·기존 3수준 요약·중요도 4필드·retry 상태가 snapshot과 같을 때만 UPDATE합니다. 동일 결과는 UPDATE하지 않습니다.
- 3수준 요약과 중요도 4필드, retry_pending=false를 함께 저장합니다. raw_content·기사 id·판단·퀴즈·사용자 기록은 수정하지 않습니다.
- dry-run은 대상 목록만 읽고 새 텍스트 생성이나 DB 쓰기를 하지 않습니다. --apply도 요청 범위에서 실제 실행하지 않았습니다.
- 한 번에 최대 1,000개까지 선택합니다. 예상 대상이 이를 넘으면 무작정 반복하지 말고 별도 범위 분할 계획을 검토해야 합니다.

## 읽기 전용 대상 수 조회 결과

2026-11-02 조회 시점:

| 범위 | 전체 기사 | 최근 7일 | 재생성 가능 EXCERPT |
|---|---:|---:|---:|
| 설정된 Supabase DB | 534 | 111 | 111 |
| 로컬 localhost:5432/finsight | 423 | 0 | 0 |

Supabase의 기사 id와 이전 운영 API 응답 id 10개가 모두 일치했습니다. DB 쿼리는 읽기 전용 세션으로 실행했습니다. 실제 UPDATE 예상 상한은 111건이며, 동일 값 또는 동시 변경이면 더 적을 수 있습니다. 시간 경과·추가 수집에 따라 다시 조회한 건수는 달라집니다. 20개 fixture는 이 최근 7일 운영 기사에서 발췌했습니다.

읽기 전용 재확인 SQL:

```sql
BEGIN READ ONLY;
SELECT count(*) AS excerpt_targets
FROM news
WHERE published_at >= now() - interval '7 days'
  AND published_at <= now()
  AND rewrite_mode = 'EXCERPT'
  AND length(trim(coalesce(raw_content, ''))) > 0
  AND coalesce(source, '') NOT LIKE 'SYNTHETIC%'
  AND url NOT LIKE '%example.invalid%';
ROLLBACK;
```

## 승인 후 실행할 명령 — 지금은 실행하지 않음

먼저 새 AI 고정 커밋을 배포해 검증합니다. 이 스크립트도 같은 AI 커밋의 체크아웃에서 실행합니다. DB_URL/DB_USERNAME/DB_PASSWORD는 실행 대상의 보안 환경으로 공급하며 명령·출력·커밋에 값을 넣지 않습니다. psycopg가 필요하지만 전체 ML 학습 패키지를 설치할 필요는 없습니다.

```sh
# 현재 개발 venv에는 psycopg가 없으므로 DB 작업 환경에만 준비합니다.
.venv/bin/python -m pip install 'psycopg[binary]>=3.2,<4'

FINSIGHT_REWRITE_SINCE=$(.venv/bin/python -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=7)).isoformat())')

# 우선 dry-run: 생성·쓰기 없음
USE_REAL_LLM=false REWRITE_WITH_LLM=false .venv/bin/python -m scripts.rewrite_news_batch \
  --excerpt --since "$FINSIGHT_REWRITE_SINCE" --limit 111

# 위 대상 수와 DB 환경을 확인하고 별도 승인한 뒤에만 실행
USE_REAL_LLM=false REWRITE_WITH_LLM=false .venv/bin/python -m scripts.rewrite_news_batch \
  --excerpt --since "$FINSIGHT_REWRITE_SINCE" --limit 111 --apply
```

111은 조회 시점의 상한 예시입니다. 실행 직전 count가 바뀌면 확인된 범위로 --limit을 다시 결정합니다. 현재 명령은 만들어 놓았을 뿐 실행하지 않았습니다. 운영 배포도 사용자 검토 전에는 수행하지 않습니다.
