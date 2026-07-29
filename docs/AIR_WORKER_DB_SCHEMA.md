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

## 9-A. AIR-0227D-VALIDATION Stage 4: 정적 재검토에서 실제로 발견하고 고친 문제

실 Postgres 실행 없이도 수기 리뷰만으로 3개의 실질적 문제를 발견했다 - 전부 이미 migration
파일에 반영 완료:

1. **EXECUTE 권한이 기본적으로 PUBLIC(=anon/authenticated 포함)에 부여됨** - Postgres는
   `CREATE FUNCTION` 시 기본적으로 PUBLIC에 EXECUTE를 준다. `SECURITY DEFINER`는 "누구
   권한으로 실행되는가"만 정하지 "누가 호출할 수 있는가"는 막지 않는다 - 고치지 않았다면
   브라우저에서 anon key만으로 `supabase.rpc('claim_worker_render_job', ...)`를 직접 호출해
   Worker Token 인증 전체를 건너뛸 수 있었다. `REVOKE ALL ... FROM PUBLIC` +
   `GRANT EXECUTE ... TO service_role`로 4개 함수 전부 수정(§9 파일 끝).
2. **`SET search_path` 미지정** - Supabase가 공식적으로 경고하는 `SECURITY DEFINER` 취약점
   클래스(search_path를 통한 함수/테이블 shadowing으로 상승된 권한을 탈취). 4개 함수 전부
   `SET search_path = ''`로 고정 - 모든 테이블 참조가 이미 `public.` 접두사로 완전
   한정되어 있음을 먼저 확인한 뒤 적용했다(내장 함수 `gen_random_uuid`/`make_interval`/
   `now`/`json_build_object` 등은 `pg_catalog`가 항상 암묵적으로 검색되므로 영향 없음).
3. **신설 테이블 4개 모두 RLS 미설정** - AIR-0227C 계획 문서(§MIGRATION_PLAN.md)는 RLS를
   의도했다고 적었지만 실제 SQL에는 빠져 있었다. `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
   4개 추가, 정책은 0개(= anon/authenticated 완전 차단, service_role은 RLS를 원천
   우회하므로 무정책으로 충분).

부수적으로 2건 더 고쳤다:
- `CREATE INDEX` → `CREATE INDEX CONCURRENTLY` (운영 테이블 락 회피, rollback의
  `DROP INDEX`도 동일하게 `CONCURRENTLY`로 통일 - 파일을 트랜잭션으로 감싸면 안 된다는
  주의사항을 파일 상단에 명시).
- `worker_job_events.job_id`의 FK `ON DELETE CASCADE` → `ON DELETE SET NULL`로 변경 -
  감사 로그 테이블이 CASCADE였다면 render-queue 행 삭제 시(관리자 삭제 포함) 그 행에 대한
  감사 기록까지 함께 사라져 "무슨 일이 있었는지"를 삭제로 지울 수 있는 구멍이 됐을 것.

기존 `remote_render_queue` 자체의 RLS 미설정 상태는 **의도적으로 건드리지 않았다** - 이미
프로덕션에 그 상태로 존재하고 레거시 워커가 어떻게 접근하는지 확실치 않아, 바꾸면 레거시를
깨뜨릴 위험이 이번 migration 범위보다 크다고 판단했다. 별도 검토 대상으로 문서에만 남긴다.

## 9-B. AIR-0227D-VALIDATION 계속: 추가 정적 확인 1 — CONCURRENTLY 재검토

§9-A에서 두 인덱스를 `CREATE INDEX CONCURRENTLY`로 바꿨었으나, 재검토 결과 **메인
migration 파일에서는 다시 일반 `CREATE INDEX IF NOT EXISTS`로 되돌렸다.** 이유:

1. `CREATE INDEX CONCURRENTLY`는 트랜잭션 블록 안에서 실행할 수 없다. 이 세션은 staging
   migration을 실제로 어떤 도구(Supabase SQL 에디터가 붙여넣은 스크립트 전체를 암묵적
   트랜잭션으로 감싸는지, `psql -f`가 파일을 문장 단위로 실행하는지)로 적용할지 확정할
   방법이 없었다 - "감싸지 않는다"고 가정하는 것보다 "감쌀 수도 있다"고 가정하고 설계하는
   쪽이 안전했다.
2. staging의 `remote_render_queue`는 작은/새로 만든 클론이므로 일반 `CREATE INDEX`의
   짧은 쓰기 락은 실질적으로 무해하다 - 작업 지시서가 제시한 두 옵션 중 "staging
   데이터량이 작으면 일반 CREATE INDEX 사용" 쪽을 그대로 채택.
3. **운영(production) 적용 시에는 다르다** - `remote_render_queue`가 실사용 중인 테이블이라
   일반 `CREATE INDEX`의 락이 레거시 워커의 claim PATCH를 체감 가능한 시간 동안 막을 수
   있다. 그래서 두 인덱스 문장을 별도 파일
   `migrations/air_0227d_worker_central_protocol_PRODUCTION_INDEXES.sql`로 분리했다 -
   `CONCURRENTLY` 버전, **반드시 트랜잭션 밖에서, 다른 문장과 섞지 않고 단독 실행**.
   운영 적용 순서는: 메인 migration 파일에서 이 두 인덱스 문장만 제외하고 적용 → 이
   파일을 별도로 실행.
4. **실패한 CONCURRENTLY의 위험을 그 파일 자체에 명시**했다 - 중단되면 Postgres가 자동
   정리하지 않고 `INVALID` 인덱스를 남긴다(쿼리 플래너는 무시하지만 디스크·쓰기 비용은
   그대로 남음). 복구는 `DROP INDEX CONCURRENTLY IF EXISTS <name>;` 후 재실행. 파일 끝에
   `pg_index.indisvalid` 체크 쿼리를 넣어 실행 직후 확인할 수 있게 했다.
5. rollback 파일의 `DROP INDEX`도 일반 형태로 되돌리되, 운영에서
   PRODUCTION_INDEXES.sql로 만들었다면 `DROP INDEX CONCURRENTLY`를 대신 써야 한다는
   주석을 남겼다.

## 9-C. AIR-0227D-VALIDATION 계속: 추가 정적 확인 2 — search_path 재검사 결과

4개 함수 본문 전체를 다시 훑어 `public.`로 완전 수식되지 않은 테이블/컬럼/타입 참조가
있는지 재검사했다(`grep -nE "^\s*(FROM|UPDATE|INSERT INTO|JOIN)\s+[a-z_]"`로 비수식 참조를
찾는 방식 + 모든 함수 호출형 식별자 목록을 수동 대조) - **비수식 참조 없음**을 재확인:

- 테이블 참조: `public.remote_render_queue`, `public.worker_job_events`,
  `public.worker_idempotency_keys` - 전부 완전 수식.
- 함수 호출: `gen_random_uuid()`, `make_interval()`, `now()` (대문자 `NOW()`),
  `json_build_object()`, `jsonb_build_object()` - 전부 `pg_catalog` 내장 함수. `pg_catalog`는
  `search_path`에 무엇이 설정돼 있든(빈 문자열이어도) **항상 암묵적으로 가장 먼저
  검색된다**(Postgres 공식 동작) - 스키마 수식이 필요 없다. `gen_random_uuid()`는 PG13+
  코어 내장(pgcrypto 확장 불필요)이고, 이 프로젝트의 기존 스키마(`remote_render_queue.id
  DEFAULT gen_random_uuid()`)가 이미 같은 함수를 쓰고 있어 이 Supabase 프로젝트에서
  실제로 해석 가능함이 간접 확인된다.
- ENUM/커스텀 타입 참조: 없음(전부 표준 TEXT/UUID/INTEGER/BOOLEAN/JSONB/TIMESTAMPTZ 사용,
  커스텀 타입·시퀀스 직접 참조 없음 - `BIGSERIAL`은 컬럼 정의 시점에만 쓰이고 함수 본문
  안에서 시퀀스를 이름으로 참조하지 않는다).
- REVOKE/GRANT 4쌍의 인자 시그니처를 각 `CREATE OR REPLACE FUNCTION` 선언과 한 줄씩
  재대조 - 전부 정확히 일치 확인(타입 순서·개수 포함).

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
