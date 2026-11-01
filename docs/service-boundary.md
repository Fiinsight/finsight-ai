# AI 서비스 배포 경계

AI 서비스는 기본 실행처럼 `127.0.0.1:8001`, worker 1개로만 노출한다. 외부 접근 가능한 주소로 바인딩할 경우 백엔드와 AI 프로세스에 같은 `AI_INTERNAL_TOKEN`을 비밀 환경변수로 지정해야 한다. 백엔드의 모든 AI 요청과 검색 어댑터 요청이 Bearer 인증을 전송한다. 토큰을 브라우저의 EXPO_PUBLIC 변수에 넣지 않는다. 토큰이 비어 있는 설정은 loopback 또는 별도 private network 정책이 있는 배포에만 사용한다.

- `/health`: 인증 없는 `{ "status": "ok" }`만 반환한다.
- `/internal/status`: 기존 모델·호출량 진단. AI_INTERNAL_TOKEN 설정 시 인증이 필요하다.
- `/ai/*`, `/v1/search`, API 문서도 같은 인증 경계를 적용한다.
- 기본 전체 요청 한도는 worker당 분당 600건, 동시 4건, 본문 12,000,000바이트, 처리 30초다. 각각 `AI_REQUESTS_PER_MINUTE`, `AI_MAX_CONCURRENT_REQUESTS`, `AI_MAX_BODY_BYTES`, `AI_REQUEST_TIMEOUT_SECONDS`로 조절한다. 본문은 Content-Length 값과 무관하게 실제 수신 바이트를 제한한다.
- 여러 worker/인스턴스가 필요해지면 ingress에서 공유 한도를 추가한다. 현재 한도는 단일 worker에 적용된다. 동기 provider 작업은 취소 후에도 실행될 수 있으므로 기존 provider timeout과 호출 예산을 함께 유지한다.
- 기존 USE_REAL_LLM, USE_REAL_EMBEDDINGS, REWRITE_WITH_LLM 등은 기본 false다. 인증 추가가 유료 호출을 켜지 않으며 기존 일일·프로세스 예산을 바꾸지 않는다.

로컬 검증: `.venv/bin/python -m pytest -q`. 운영 환경변수 변경이나 배포는 이 변경에 포함하지 않았다.
