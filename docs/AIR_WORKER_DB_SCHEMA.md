# AIR Worker — DB 스키마 (AIR-0227D)

- 상태: **SQL 작성 완료, 수기 리뷰만 거침 - 어떤 DB에도 미적용**
- 파일: `migrations/air_0227d_worker_central_protocol.sql` (+ `_rollback.sql`)
- 관련 문서: [MIGRATION_PLAN](./AIR_WORKER_MIGRATION_PLAN.md) (왜 이 설계로 갔는지의 배경),
  [CENTRAL_API](./AIR_WORKER_CENTRAL_API.md)

## 1. `remote_render_queue` 확장 (기존 프로덕션 테이블)

기존 컬럼(`id, project_id, project_name, email, status, progress, message, render_mode,
asset_file_id, asset_file_name, result_file_id, result_file_name, worker_id, claimed_at,
error_message, retry_count, metadata, created_at, updated_at, completed_at`)은 **전혀
건드리지 않는다**. 추가 컬럼:

| 컬럼 | 타입 | 용도 |
|---|---|---|
| `job_type` | TEXT, 기본 `'render_video'` | claim 시 `allowed_job_types` 필터링 대상 |
| `priority` | INTEGER, 기본 0 | claim 정렬 기준 (`ORDER BY priority DESC`) |
| `worker_status` | TEXT, nullable | 세분화 상태(QUEUED\|CLAIMED\|PREPARING\|RENDERING\|UPLOADING\|COMPLETED\|FAILED\|CANCELED\|ABANDONED). NULL = 레거시가 claim한 행 |
| `worker_group` | TEXT, nullable | `'air-worker'` \| `'legacy'` \| NULL(누구나 claim 가능) |
| `worker_instance_id` | TEXT | lease 소유 증명의 일부 |
| `lease_id` | UUID | claim마다 새로 발급 |
| `lease_acquired_at` / `lease_expires_at` | TIMESTAMPTZ | |
| `heartbeat_at` | TIMESTAMPTZ | claim/renew/progress마다 갱신 |
| `attempt_number` | INTEGER | claim(재할당 포함)마다 증가 |
| `result_reference` | TEXT | AIR Worker의 범용 결과 포인터(Drive file id 등). 레거시는 계속 `result_file_id`/`result_file_name` 사용 - `report_worker_render_job_outcome`이 두 컬럼 모두에 값을 채운다 |
| `error_code` | TEXT | |
| `tenant_id` | TEXT | |

`status`(기존 컬럼, `pending`/`rendering`/`completed`/`failed`)는 그대로 유지되고,
AIR Worker 경로가 이 컬럼도 함께 갱신해 레거시 워커/기존 admin UI 필터가 계속 작동한다.
CHECK 제약이 없는 컬럼이라 `worker_status`의 새 값들을 추가해도 기존 제약 위반이 없다.

인덱스 2개: claim 대상 필터링용(`status='pending'` 부분 인덱스), lease 만료 스윕용
(`status='rendering'` 부분 인덱스).

## 2. `workers` (신설)

워커 "신원" 레지스트리. `worker_id`가 PK, 토큰 회전과 무관하게 안정적으로 유지된다.
`worker_tokens.worker_id`가 여길 FK로 참조(`ON DELETE CASCADE`).

## 3. `worker_tokens` (신설)

원문 토큰은 저장하지 않는다 - `token_hash`(sha256 hex)만. `token_id`가 PK이자 원문 토큰에
그대로 노출되는 공개 조회 키(`awt_<token_id>_<secret>`). `revoked_at IS NULL`이고
`expires_at`이 미래(또는 NULL)인 행만 유효. 자세한 발급/폐기 흐름은 §AIR_WORKER_AUTH.md §0-A.

## 4. `worker_job_events` (신설)

append-only 감사 로그. `job_id`는 nullable - register/heartbeat 이벤트는 특정 작업과
무관하다. `event_type`은 자유 텍스트(CHECK 제약 없음 - 새 이벤트 타입 추가 시 마이그레이션
불필요, §CENTRAL_API.md §6에 현재 쓰이는 값 목록).

## 5. `worker_idempotency_keys` (신설)

PK가 `(job_id, idempotency_key)` 복합키. `request_hash`는 정규화된(키 정렬) payload의
sha256 - 같은 키로 다른 payload가 오면 불일치를 감지해 `409 conflict`. `response_snapshot`은
최초 응답을 그대로 저장해뒀다가 재전송 시 그대로 재반환 - 재시도가 진짜로 안전하다
(부작용이 두 번 일어나지 않는다).

## 6. `claim_worker_render_job()` RPC — 원자적 claim

```
SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1   -- 행 하나만 잠금, 잠긴 행은 건너뜀
  WHERE job_type = ANY(allowed) AND (worker_group IS NULL OR = 요청 그룹)
    AND (status='pending' OR (status='rendering' AND lease_expires_at < NOW()))
  ORDER BY priority DESC, created_at ASC
UPDATE ... SET status='rendering', worker_status='CLAIMED', lease_id=신규, ...
INSERT INTO worker_job_events (... 'claim' ...)
RETURN 갱신된 행
```

`SELECT FOR UPDATE`가 이미 그 행을 잠갔으므로 뒤이은 `UPDATE`는 안전하다(같은 트랜잭션
안에서 락을 이미 쥐고 있음). `SKIP LOCKED`가 있어 여러 워커가 동시에 이 RPC를 호출해도
서로 다른 행을 골라 각자 진행하고, 같은 행을 고른 나머지는 즉시 다음 후보로 넘어간다(대기
없음) - 이것이 "10개 Worker 동시 요청 → 정확히 1건 claim" 요구사항의 구현이다. **실제
Postgres에 대해 이 동시성 자체를 실행 검증하지는 못했다** - 수기 리뷰로 표준적인
`FOR UPDATE SKIP LOCKED` 큐잉 패턴임을 확인했을 뿐이다(`migrations/air_0158g_...`가 이미
쓰는 단일행 `FOR UPDATE`의 다중행/SKIP LOCKED 확장).

만료된 lease를 가진 `status='rendering'` 행도 같은 WHERE 절에 포함되어 재할당 대상이 된다.
단, `lease_expires_at IS NULL`인 행(레거시 워커가 claim한 행 - 레거시는 이 컬럼을 아예 모름)은
**의도적으로 재할당 대상에서 제외** - AIR Worker가 레거시가 붙잡고 있는 작업을 함부로
가로채지 않는다.

## 7. `renew_worker_render_job_lease()` RPC

`WHERE lease_id = ? AND worker_instance_id = ? AND status='rendering' AND
lease_expires_at > NOW()` 조건에 맞는 행이 없으면 빈 결과 반환 → 라우트가 `409`로 변환.
이미 재할당됐거나(lease_id 불일치), 이미 만료됐거나, 다른 worker_instance_id(재시작된
동일 worker_id)면 전부 거부된다.

## 8. `report_worker_render_job_progress()` RPC

서버가 소유한 상태 전이표(§CENTRAL_API.md §4)를 강제. lease 불일치 또는 잘못된 전이면 빈
결과 반환.

## 9. `report_worker_render_job_outcome()` RPC — complete/fail 공용

```
1. (job_id, idempotency_key) 이미 존재?
   같은 request_hash → 저장된 response 그대로 재반환 (idempotent_replay)
   다른 request_hash → 409 conflict + 감사 로그 (idempotent_conflict)
2. FOR UPDATE로 현재 행 잠금, lease_id 불일치 또는 status != 'rendering' → 409 stale_lease
3. status/worker_status 갱신, result_reference(+레거시 result_file_id) 기록
4. worker_job_events에 complete/fail 기록
5. worker_idempotency_keys에 response 스냅샷 저장
6. 응답 반환
```

전부 하나의 plpgsql 함수 호출 안에서 일어나므로(단일 트랜잭션), "서버가 처리는 끝냈는데
응답만 유실"과 "처리 자체가 안 됨"을 idempotency 조회로 구분할 수 있다 - 재시도가 절대
같은 작업을 두 번 완료 처리하지 않는다.

## 10. 검증되지 않은 것

이 파일 전체가 **실 Postgres 실행 없이 작성**됐다. 문법/락 순서/트랜잭션 경계를 신중히
수기 검토했지만, staging Supabase 프로젝트에 실제로 적용해 아래를 확인하기 전까지는
"동작한다"고 주장할 수 없다:
- `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN IF NOT EXISTS`가 기존
  `remote_render_queue` 데이터가 있는 상태에서 문제없이 적용되는지
- 4개 RPC 함수가 실제로 컴파일(`CREATE FUNCTION`)되는지 - plpgsql 문법 오류는 로컬에서
  잡을 방법이 없었다(Docker/psql 둘 다 이 환경에 없음)
- `FOR UPDATE SKIP LOCKED` 동시성이 실제 부하 하에서 지시서가 요구하는 결과(10-way 동시
  claim, priority/FIFO, worker_group 필터)를 내는지
