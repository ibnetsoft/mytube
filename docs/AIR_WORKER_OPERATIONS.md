# AIR Worker — 운영 런북 (AIR-0227D)

- 관련 문서: [DB_SCHEMA](./AIR_WORKER_DB_SCHEMA.md), [CENTRAL_API](./AIR_WORKER_CENTRAL_API.md), [MIGRATION_PLAN](./AIR_WORKER_MIGRATION_PLAN.md)

## 1. Lease 운영값

| 값 | 후보 | 근거 |
|---|---|---|
| Lease TTL | 300초(5분) | 작업 지시서의 후보값 그대로, `LEASE_TTL_SECONDS` env(`AIRWORKER_LEASE_TTL_SECONDS`)로 조정 가능 - 하드코딩 아님(`auth-web/app/api/internal/worker/jobs/claim/route.ts`) |
| Renew interval | 60초 | 워커 쪽 값(`worker/render_worker.py`), 서버는 관여하지 않음 - AIR-0227C에서는 테스트 편의상 3초/8초 TTL로 실측했고, 300초 TTL이면 60초 간격으로도 갱신 실패 1~2회를 흡수할 여유가 충분 |
| Network grace | 10분 | 워커 로컬 정책(§LEASE_PROTOCOL.md §6) - 서버는 grace 개념 자체가 없다, lease_expires_at만 안다 |

**실 운영값은 이 세션에서 확정할 수 없다** - staging에서 실제 평균 렌더 시간 분포를 관찰한
뒤 "lease TTL은 평균 렌더 시간의 3~5배" 같은 경험칙으로 조정해야 한다(§LEASE_PROTOCOL.md §6
말미의 기존 권고와 동일 원칙). 300초는 출발점이지 최종값이 아니다.

## 2. Migration 적용 절차 (staging)

```
1. staging Supabase 프로젝트에서 SQL 에디터 또는 psql로
   migrations/air_0227d_worker_central_protocol.sql 실행
2. 스모크 테스트:
   SELECT * FROM claim_worker_render_job('smoke-test','smoke-inst-1','{render_video}','air-worker',300);
   -- 빈 결과가 정상 (큐 비어있음). 에러가 나면 여기서 멈추고 SQL 수정.
3. remote_render_queue에 테스트 행 1건 수동 INSERT (job_type='render_video', status='pending')
4. 같은 claim RPC를 다시 호출 - 이번엔 그 행이 반환되고 status='rendering'/worker_status='CLAIMED'로
   바뀌었는지 확인
5. worker_job_events에 claim 이벤트 1건 기록됐는지 확인
6. 문제 없으면 §STAGING_E2E_QA.md §2의 전체 흐름으로 진행
```

문제 발생 시: `migrations/air_0227d_worker_central_protocol_rollback.sql` 실행(신설
테이블/컬럼만 제거, 기존 `remote_render_queue` 데이터는 무손상).

**운영(production) DB에는 staging에서 §STAGING_E2E_QA.md의 완료 기준을 전부 통과하고
CTO가 별도 승인하기 전까지 절대 적용하지 않는다.**

## 3. 토큰 운영

- 발급: `/api/admin/worker-tokens` POST (super admin) 또는 `/admin/workers` 페이지의
  "Issue token" 폼.
- 회전: 같은 worker_id로 재발급하면 기존 유효 토큰이 자동 폐기됨(`revoke_existing` 기본
  true) - 폐기와 신규 발급 사이에 두 토큰이 동시에 유효한 창은 이 API 호출 하나의
  트랜잭션이 아니라 순차 실행(폐기 UPDATE 먼저, 발급 INSERT 나중)이라 **완벽한 원자성은
  아니다** - 실전에서는 무시할 수준(수 ms)이지만, 완벽을 요구한다면 향후 하나의 RPC로
  합칠 수 있다(이번 범위 밖으로 명시).
- 폐기: `/admin/workers` 페이지의 "Revoke token" 버튼, 또는 `DELETE
  /api/admin/worker-tokens/{tokenId}`.
- 단기 토큰 전환 경로(향후): 현재 저장 구조(`token_id`/`token_hash`/`expires_at`)는 이미
  단기 토큰을 지원한다 - `expires_in_days`를 짧게(예: 1) 주고 워커가 주기적으로
  `/register`를 다시 호출해 재발급받는 흐름을 추가하면 된다. 발급 로직만 바뀌고 검증
  로직(`authenticateWorkerRequest`)은 변경 불필요.

## 4. Vercel 제약 검토 결과 (AIR-0227D 조사)

- `auth-web/vercel.json` 없음, 어떤 route도 `maxDuration`/`runtime`을 export하지 않음 -
  기본 타임아웃(플랜에 따라 10~60초) 적용.
- 새 Worker API 7개 엔드포인트는 전부 짧은 단일 DB 왕복(claim/renew/progress) 또는
  RPC 1회 호출(complete/fail)로 설계했다 - 렌더링 자체는 워커 로컬에서 일어나고
  auth-web은 절대 렌더링을 기다리지 않는다. 기본 타임아웃 내에서 충분히 끝난다고
  판단하나, **실측한 적은 없다**.
- cron/장기 커넥션 없음 - claim은 워커가 짧은 간격으로 폴링(HTTP 요청-응답 1회씩)하는
  방식 그대로 유지, WebSocket/SSE 도입하지 않음(지시서 범위 제외 사항과 일치).
- `pg`(raw Postgres) 패키지가 이미 `auth-web/package.json`에 존재 - 이번 구현은
  `supabase-js`의 `.rpc()`만 사용했고 raw `pg` 커넥션은 열지 않았다(서버리스 환경에서
  커넥션 풀 관리 부담을 피하기 위해); 필요해지면 `pg`로 전환할 여지는 남겨뒀다.
- heartbeat 호출량: 워커 1대당 register 1회 + claim 폴링(유휴 시에도 지속) + 작업 중
  progress/renew - 다수 워커 운영 시 실제 QPS를 staging에서 관찰해 rate limit 여유가
  있는지 확인 필요(미검증).

## 5. 구형 워커 병행 정책

- `remote_render_queue.worker_group`이 NULL인 행은 레거시/AIR Worker 누구나 claim
  가능(기존 동작 그대로).
- `worker_group='legacy'`로 명시된 행은 `claim_worker_render_job`의 WHERE 절
  (`worker_group IS NULL OR worker_group = p_worker_group`)에 의해 AIR Worker에게
  노출되지 않는다 - 다만 이번 구현에 레거시 전용으로 행을 만드는 경로는 없다(필요해지면
  관리자가 INSERT 시 지정).
- 레거시 워커가 만든 claim(`lease_expires_at IS NULL`인 `status='rendering'` 행)은
  AIR Worker의 재할당 로직에서 의도적으로 제외 - §DB_SCHEMA.md §6 참고. 레거시가
  크래시해서 영원히 멈춘 행에 대한 처리는 이번 범위에 포함되지 않았다(기존에도 없던
  기능이라 새로 생긴 회귀가 아님).
- dead endpoint 삭제 없음 - `/api/admin/render-queue`(GET/DELETE만 있던 기존 라우트)는
  손대지 않았다.

## 6. 알려진 갭 / 다음 작업 후보

- `/api/admin/render-queue` GET/DELETE에 admin 인증 게이트가 없다는 사전 발견 - 이번
  작업 범위 밖(신규 `/api/internal/worker/**`와 무관)이라 수정하지 않았지만, 별도로
  플래그해뒀다.
- `supabaseAdmin.ts`가 `SUPABASE_SERVICE_ROLE_KEY` 미설정 시 anon key로 조용히
  폴백하는 기존 코드 - 새 워커 라우트도 이 클라이언트를 그대로 쓰므로, 이 폴백이
  발동하면 worker_tokens 테이블 조회 자체가 RLS에 막혀 전부 401이 될 것(안전한
  방향의 실패이긴 하나, 원인 파악이 어려울 수 있음) - staging 배포 시
  `SUPABASE_SERVICE_ROLE_KEY`가 실제로 설정됐는지 1차로 확인할 것.
