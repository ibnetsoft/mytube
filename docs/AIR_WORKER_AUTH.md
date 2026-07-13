# AIR Worker — 중앙 서버 인증 계약 (AIR-0227C, AIR-0227D §0-A에서 실제 구현으로 갱신)

- 상태: **AIR-0227D에서 auth-web에 실제 라우트/토큰 저장 구현 완료 - 실 DB(staging/production) 어디에도 미적용, 미배포. [AIR-0227D-STAGING-UNBLOCK] `worker/central_client.py`가 실제로는 §1-3의 구식 스케치 경로(`/api/worker/*`, `renew-lease`)를 호출하던 실제 코드 버그를 발견·수정함 — 실 구현 경로는 `/api/internal/worker/**` + `renew`(§CENTRAL_API 참고). 로컬 모의 서버 기준 register→claim→lease 갱신→progress→complete 전체 라운드트립 재검증 완료(worknote/AIR-0227D-STAGING-UNBLOCK.md).**
- 관련 문서: [SECURITY](./AIR_WORKER_SECURITY.md), [LEASE_PROTOCOL](./AIR_WORKER_LEASE_PROTOCOL.md), [REMOTE_E2E_QA](./AIR_WORKER_REMOTE_E2E_QA.md), [MIGRATION_PLAN](./AIR_WORKER_MIGRATION_PLAN.md), [CENTRAL_API](./AIR_WORKER_CENTRAL_API.md)

## 0-A. AIR-0227D: §3(아래)의 서명 토큰 설계에서 저장-해시 토큰으로 변경한 이유

§3은 원래 `desktopSession.ts`처럼 **자기완결적 HMAC 서명 토큰**(비밀만 알면 검증 가능,
서버는 아무것도 저장 안 함)을 계획했다. AIR-0227D 구현 중 이 설계로는 작업 지시서 Stage 4의
"재발급 시 즉시 이전 토큰 무효화"를 만족시킬 수 없다는 걸 확인했다 - 서명 토큰은 서버가
별도 폐기(revocation) 목록을 유지하지 않는 한 자기 만료 시각까지는 계속 유효하다. 그래서
실제 구현(`auth-web/lib/workerAuth.ts`)은 **저장-해시 토큰**으로 바꿨다:

- 발급 시 `token_id`(공개, 조회용)와 `secret`(비밀)을 따로 생성 - 원문 토큰은
  `awt_<token_id>_<secret>` 형태.
- DB(`worker_tokens.token_hash`)에는 `sha256(secret)`만 저장, 원문은 발급 응답에만
  1회 등장(§CENTRAL_API.md §4).
- 검증은 매 요청마다 DB를 다시 읽는다(캐시 없음) - `revoked_at`/`expires_at`을 지운다는
  것 자체가 즉시 무효화다. `local_api_token.py`(로컬 Local API 토큰, AIR-0227C Stage 3)와
  똑같은 "캐시하지 않고 매번 재확인" 원칙을 중앙 서버 쪽에도 그대로 적용했다.
- 비교는 `crypto.timingSafeEqual`(Node) - 해시끼리 비교라 원문 길이 유추 위험은 없지만,
  일관성을 위해 상수시간 비교를 유지했다.

§1~§3(아래)은 AIR-0227C 시점의 최초 설계 스케치로 그대로 남겨둔다 - 실제 구현과 다른
부분은 위 §0-A를 우선한다.

## 0. 이번 Task의 범위 결정 (투명하게 명시)

"기존 중앙 서버 구조를 먼저 분석하고 가장 자연스러운 위치에 구현한다"는 지시를 이렇게
해석했다: **분석과 설계는 auth-web 기준으로 완성**하되(§2), **실제 살아있는 E2E 검증
(Stage 9)은 `worker/dev_central_server/`라는 로컬 Python 모의 서버로 수행**했다 — 동일한
wire contract(경로/요청/응답 형태)를 구현하므로 `central_client.py`는 실제 auth-web이
붙어도 `CENTRAL_SERVER_URL`/`AIRWORKER_TOKEN` 값만 바꾸면 코드 변경 없이 동작한다. 이건
AIR-0226에서 Gemini가 실제 Hermes/Nous Research 자격증명 부재를 메웠던 것과 정확히 같은
패턴이다 — auth-web에 실제 라우트 파일을 만들어 배포하는 것은 운영 Vercel/Supabase를
건드리는 일이라 이번 Task에서 하지 않았다(§ARCHITECTURE §0, "실제 서비스 코드 연결은 CTO의
별도 승인 전까지 진행하지 않는다"의 연장). 대신 아래 §2는 auth-web에 실제로 옮겨 붙일 수
있을 만큼 구체적으로 작성했다.

## 1. 기존 auth-web 구조 분석

`auth-web/lib/desktopSession.ts`(AIR-0225B)가 이미 검증된 패턴을 갖고 있다:
- `crypto.createHmac('sha256', secret)`로 서명, `crypto.timingSafeEqual`로 검증
- 비밀은 전용 환경변수(`DESKTOP_SESSION_SECRET`) — Supabase 키와 절대 재사용하지 않음
- 라우트는 `auth-web/app/api/<name>/route.ts`, `NextResponse.json({success, ...}, {status})`
  형태로 통일, 에러는 항상 success:false + 적절한 HTTP 상태코드

Worker Token은 이 패턴을 그대로 재사용하되, 페이로드를 dot-delimited 평문 대신 **JSON
직렬화**로 바꿨다 — `desktopSession.ts`의 `verifyDesktopSessionToken`이 겪었던 "이메일에
점이 여러 개 있어서 delimiter가 모호해지는" 버그 클래스를 애초에 만들지 않기 위해서다.

```
payload = {"worker_id": "...", "token_id": "...", "allowed_job_types": ["render_video"],
           "issued_at": 1234567890, "expires_at": 1234567890,
           "worker_group": null, "capabilities": []}
payload_b64 = base64url(json.dumps(payload, separators=(',',':')))
token = payload_b64 + "." + HMAC_SHA256(WORKER_TOKEN_SECRET, payload_b64).hex()
```

`WORKER_TOKEN_SECRET`은 `DESKTOP_SESSION_SECRET`과 별도의 새 환경변수 — 신뢰 도메인이
다르면 비밀도 다르다는 이 세션 전체의 원칙 그대로.

## 2. auth-web 실제 구현 위치 (설계, 미배포)

```
auth-web/lib/workerAuth.ts          - signWorkerToken/verifyWorkerToken (desktopSession.ts 패턴)
auth-web/app/api/worker/register/route.ts
auth-web/app/api/worker/heartbeat/route.ts
auth-web/app/api/worker/jobs/claim/route.ts
auth-web/app/api/worker/jobs/[job_id]/progress/route.ts
auth-web/app/api/worker/jobs/[job_id]/complete/route.ts
auth-web/app/api/worker/jobs/[job_id]/fail/route.ts
auth-web/app/api/worker/jobs/[job_id]/renew-lease/route.ts
```

각 라우트의 실제 로직(테이블 조회/lease 갱신/idempotency 체크)은
`worker/dev_central_server/server.py`에 이미 동일한 계약으로 구현·검증되어 있다 — auth-web
버전은 SQLite 대신 신설 Supabase 테이블(§MIGRATION_PLAN)을 쓰고, `_authorize()`는
`workerAuth.ts`의 HMAC 검증으로, 나머지 claim/lease/idempotency 로직은 거의 그대로
포팅 가능하다.

## 3. Worker Token 최소 claim (지시사항 그대로)

| 필드 | Worker가 결정 | 중앙 서버가 결정 |
|---|---|---|
| `worker_id` | - | ✅ 발급 시 확정 |
| `token_id` | - | ✅ 발급 시 확정 (재발급 시 새 값 - 폐기 판별용) |
| `allowed_job_types` | 요청 시 참고만 제시 | ✅ 최종 결정 - `dev_central_server`가 실측 증명: `claim()`은 요청의 `allowed_job_types`와 토큰의 authoritative 목록의 **교집합**만 허용 (§7 실측) |
| `issued_at`/`expires_at` | - | ✅ |
| `worker_group`/`capabilities` | - | ✅ (선택 필드, Stage 12 병행 운영에서 구형/신형 워커 구분에 쓸 수 있도록 스키마에 포함) |
| `tenant_id`/`user_id`/job ownership/billing/priority/승인여부 | ❌ 절대 없음 | ✅ 전부 서버 소유 - Worker Token 자체에도 포함하지 않음(claim() 응답에 tenant_id가 붙어 나올 뿐, Worker가 스스로 주장할 방법이 없음) |

## 4. 지원 API (실측 검증 완료, 로컬 모의 서버 기준)

```
POST /api/worker/register          - 워커 자기 자신 확인, 허용 job_type 리스트 반환
POST /api/worker/heartbeat          - 생존 신고
POST /api/worker/jobs/claim         - lease 발급 (§LEASE_PROTOCOL)
POST /api/worker/jobs/{id}/progress - 진행률 보고 (lease 검증)
POST /api/worker/jobs/{id}/complete - 완료 보고 (lease 검증 + Idempotency-Key)
POST /api/worker/jobs/{id}/fail     - 실패 보고 (lease 검증 + Idempotency-Key)
POST /api/worker/jobs/{id}/renew-lease - lease 연장
```

전부 `Authorization: Bearer <worker_token>` 요구, 실패 시 401/403. 실측 결과는
[REMOTE_E2E_QA.md](./AIR_WORKER_REMOTE_E2E_QA.md) 참고.

## 5. 운영 DB migration

Worker Token 자체는 자기완결적 HMAC 토큰이라 DB 저장이 필요 없다(검증만 필요). 하지만
`claim`이 참조할 실제 작업 테이블(`worker_jobs` 또는 기존 `remote_render_queue`의
worker-lease 확장판)은 신설/변경이 필요하다 — SQL 초안은 [MIGRATION_PLAN.md](./AIR_WORKER_MIGRATION_PLAN.md)에
작성했고, **CTO 승인 전까지 운영 DB에 실행하지 않았다.**
