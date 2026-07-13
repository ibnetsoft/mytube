# AIR Worker — 실제 auth-web 중앙 서버 API (AIR-0227D)

- 상태: **[AIR-0227D-STAGING-UNBLOCK 최종] 실제 프로덕션 Supabase(`picadiri`) + 실제 배포된 Vercel 프리뷰(PR #85, `/api/internal/worker/**`)를 대상으로 진짜 HTTP 라운드트립 실측 완료 — 가짜 토큰 401 거부, register/heartbeat/claim/renew/progress/complete 전부 200, Idempotency-Key 누락 400 정상 거부, 최종 DB 상태 확인 후 테스트 데이터 삭제까지 확인(worknote/AIR-0227D-STAGING-UNBLOCK.md §6). 이전엔 워커 클라이언트가 구식 `/api/worker/*`(+`renew-lease`) 경로를 호출하던 버그가 있었고(이미 수정), 그 수정 이후 이 실측까지 완료됨. 단, 이 실측 대상은 아직 `main`에 병합되지 않은 PR #85의 프리뷰 배포다 — 프로덕션(`main`) 배포 자체에 대한 실측은 별도.**
- 구현 위치: `auth-web/app/api/internal/worker/**`, `auth-web/lib/workerAuth.ts`
- 관련 문서: [AUTH](./AIR_WORKER_AUTH.md), [LEASE_PROTOCOL](./AIR_WORKER_LEASE_PROTOCOL.md), [DB_SCHEMA](./AIR_WORKER_DB_SCHEMA.md), [STAGING_E2E_QA](./AIR_WORKER_STAGING_E2E_QA.md)

## 0. 기존 라우팅 규칙과의 관계

`auth-web/app/api/internal/**`은 이전에 존재하지 않았다(조사로 확인, §STAGING_E2E_QA.md
참고). 기존 admin 라우트는 전부 `/api/admin/**` + `requireAdmin`/`requireSuperAdmin`
(사람 관리자의 Supabase 세션 JWT)을 쓰는데, Worker Token은 **사람이 아니라 기계** 자격증명이라
같은 미들웨어를 쓸 수 없었다 - 그래서 새 네임스페이스(`/api/internal/worker/**`)를 분리했다.
Worker Token 발급/조회/폐기(`/api/admin/worker-tokens/**`, `/api/admin/workers`)는 반대로
**사람 관리자만** 호출해야 하므로 기존 `requireSuperAdmin`/`requireAdmin`을 그대로 재사용했다
(`app/api/admin/_auth.ts`) - 이 부분은 충돌 없이 기존 패턴에 자연스럽게 얹혔다.

## 1. 엔드포인트

| 메서드/경로 | 인증 | 설명 |
|---|---|---|
| `POST /api/internal/worker/register` | Worker Token | Manager 프로세스 시작 시 1회, `workers` 레지스트리 upsert |
| `POST /api/internal/worker/heartbeat` | Worker Token | 워커 레벨 생존 신호 (작업 유무와 무관) |
| `POST /api/internal/worker/jobs/claim` | Worker Token | 원자적 claim, lease 발급 |
| `POST /api/internal/worker/jobs/{jobId}/renew` | Worker Token | lease 연장 |
| `POST /api/internal/worker/jobs/{jobId}/progress` | Worker Token | 진행률/세부상태 보고 (lease-gated) |
| `POST /api/internal/worker/jobs/{jobId}/complete` | Worker Token + `Idempotency-Key` | 성공 완료 보고 |
| `POST /api/internal/worker/jobs/{jobId}/fail` | Worker Token + `Idempotency-Key` | 실패 보고 |
| `GET /api/admin/workers` | 사람 관리자(Bearer=Supabase 세션) | §STAGING_E2E_QA/OPERATIONS용 목록 |
| `GET/POST /api/admin/worker-tokens` | 사람 관리자(super admin) | 토큰 목록/발급 |
| `DELETE /api/admin/worker-tokens/{tokenId}` | 사람 관리자(super admin) | 즉시 폐기 |

## 2. 인증

`Authorization: Bearer awt_<token_id>_<secret>` 헤더 필수. 쿼리 파라미터/바디를 통한 토큰
전달은 지원하지 않는다(로그·브라우저 히스토리 노출 방지, `AIR_WORKER_LOCAL_API_SECURITY.md`의
로컬 원칙과 동일). 실패 시 항상 `401 {"error":"unauthorized","detail":"..."}` - `detail`
값은 디버깅용이지 사용자에게 "정확히 무엇이 틀렸는지" 알려주는 용도가 아니다(토큰 추측
공격 방어).

## 3. Claim이 신뢰하지 않는 것

작업 지시서의 "Worker가 보낸 tenant_id, priority, ownership, allowed job_type을 신뢰하지
않는다" 원칙을 코드 구조로 강제했다(`app/api/internal/worker/jobs/claim/route.ts`):

- `allowed_job_types`는 **토큰 레코드**(`worker_tokens.allowed_job_types`)에서만 온다.
  요청 바디의 `requested_job_types`는 **교집합으로만 좁힐 수 있고 넓힐 수 없다**
  (`allowedJobTypes.filter(t => requested_job_types.includes(t))`).
- `worker_group`도 토큰 레코드에서만 온다.
- `tenant_id`/`priority`는 애초에 claim 요청 바디에 필드 자체가 없다 - claim RPC가 큐에서
  고른 행의 값을 그대로 응답에 실어 보낼 뿐, 워커가 무엇을 원하는지 지시할 수 없다.

## 4. 상태 전이

서버(RPC)가 소유:

```
QUEUED --(claim)--> CLAIMED --(progress)--> PREPARING --(progress)--> RENDERING
  --(progress)--> UPLOADING --(complete)--> COMPLETED
                            --(fail)------> FAILED
(어느 상태에서든 lease 만료 후 재claim 없이 방치되면 운영상 ABANDONED로 간주 - DB 컬럼상
 별도 자동 전이는 없고, §OPERATIONS.md의 모니터링 쿼리로 식별)
```

`report_worker_render_job_progress` RPC가 위 화살표 순서를 강제하고(§DB_SCHEMA.md §8),
`같은 상태로의 재보고`(예: RENDERING → RENDERING, progress 갱신만)는 멱등 허용. 화살표에
없는 전이(예: CLAIMED → UPLOADING처럼 단계를 건너뜀, 또는 COMPLETED → RENDERING처럼
역행)는 `409`.

## 5. 에러 응답 규약

| 상황 | 상태코드 | 본문 |
|---|---|---|
| 토큰 없음/malformed/미상/폐기/만료/해시불일치 | 401 | `{"error":"unauthorized","detail":"..."}` (사유는 서버 로그에만 상세히) |
| 요청 바디 스키마 위반 | 400 | `{"error":"invalid_request","detail":"..."}` |
| 바디 256KB 초과 | 413 | `{"error":"payload_too_large"}` |
| JSON 파싱 실패 | 400 | `{"error":"invalid_json"}` |
| stale lease / 잘못된 상태 전이 | 409 | `{"error":"conflict"|"lease_conflict",...}` |
| 같은 idempotency key + 다른 payload | 409 | `{"outcome":"conflict","http_status":409,...}` (complete/fail 전용, RPC가 직접 반환) |
| RPC/DB 오류 | 500 | `{"error":"db_error","detail":"..."}` |

## 6. 감사 로그

`worker_job_events`에 claim/renew_lease/progress/complete/fail/reject_stale_lease/
reject_invalid_transition/idempotent_replay/idempotent_conflict/register/heartbeat 이벤트가
쌓인다. RPC들이 직접 쓰는 이벤트(claim/renew/progress/complete/fail/reject_*)와, 라우트
핸들러가 `logWorkerAuditEvent()`로 직접 쓰는 이벤트(register - job과 무관하므로 RPC 경로가
아님)로 나뉜다. 감사 로그 삽입 실패는 절대 원 요청을 실패시키지 않는다(best-effort,
`workerAuth.ts::logWorkerAuditEvent`의 try/catch).

## 7. 아직 검증 안 된 것 (정직하게 명시)

- 실 Postgres/Supabase에 대해 단 한 번도 실행되지 않았다 - `npx tsc --noEmit` 통과와
  SQL 수기 리뷰만 거쳤다. §STAGING_E2E_QA.md §0 참고.
- Vercel 함수 타임아웃/콜드스타트 하에서의 실제 지연시간 - §OPERATIONS.md §4.
