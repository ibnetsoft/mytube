# AIR Worker — 운영 DB 마이그레이션 초안 (AIR-0227C, AIR-0227D에서 갱신)

- 상태: **SQL 초안만 - 운영 DB에 실행하지 않았음, staging DB에도 아직 적용 안 함(접속 정보 없음), CTO 승인 필요**
- 관련 문서: [AUTH](./AIR_WORKER_AUTH.md), [LEASE_PROTOCOL](./AIR_WORKER_LEASE_PROTOCOL.md), [CENTRAL_API](./AIR_WORKER_CENTRAL_API.md), [DB_SCHEMA](./AIR_WORKER_DB_SCHEMA.md)

## AIR-0227D 갱신 사항 (이 섹션이 최신 - §1~4는 AIR-0227C 시점의 초기 스케치로 보존만 함)

AIR-0227C 당시엔 auth-web의 실제 스키마를 조사하지 않은 채 스케치만 했다. AIR-0227D에서
실제 `auth-web/supabase_schema.sql`을 읽어보니 **치명적인 이름 충돌을 스스로 만들 뻔했다**:
아래 §1이 제안한 `worker_jobs` 테이블명이 **이미 `migrations/air_0164a_worker_jobs.sql`에
존재하는, 완전히 무관한 기능**(일반 사용자용 태스크보드, `auth.uid()` 기반 RLS)과 충돌한다.

실제 구현은 아래처럼 바뀌었다 - 최종 SQL은
`migrations/air_0227d_worker_central_protocol.sql`:

1. **새 `worker_jobs` 테이블을 만들지 않는다.** 대신 이미 프로덕션에 존재하고 레거시
   PicadiriRemoteWorker가 실제로 사용 중인 `public.remote_render_queue`
   (`auth-web/supabase_schema.sql:519-540`)를 확장한다 - lease 컬럼(`lease_id`,
   `lease_expires_at`, `worker_instance_id`, `heartbeat_at`, `attempt_number` 등)과
   세분화된 `worker_status`(QUEUED/CLAIMED/PREPARING/RENDERING/UPLOADING/COMPLETED/
   FAILED/CANCELED/ABANDONED)를 추가하되, 기존 `status`(pending/rendering/completed/
   failed) 컬럼은 그대로 유지해 레거시 워커의 맹목적 PostgREST PATCH
   (`?status=eq.pending`)를 절대 깨지 않는다. 근거: `worknote/AIR-0227A-stage1-render-worker-analysis.md`가
   기록한 레거시 claim 방식.
2. **`worker_registry` 대신 `workers`/`worker_tokens`로 분리.** §1의 단일
   `worker_registry` 테이블은 "worker 신원"과 "토큰"을 한 테이블에 섞고 있었다 -
   실제로는 토큰 회전(재발급)이 신원과 독립적으로 자주 일어나므로 분리했다
   (§DB_SCHEMA.md 참고). `tenant_id UUID REFERENCES profiles(id)` FK도 뺐다 -
   워커는 특정 tenant에 속하지 않고 여러 tenant의 작업을 처리하는 인프라이므로,
   FK보다는 작업 행 자체의 `tenant_id`(remote_render_queue에 추가)가 맞는 자리다.
3. **원자적 claim을 실제로 구현했다.** §1엔 인덱스만 있고 claim 로직 자체가 없었다 -
   AIR-0227D는 `claim_worker_render_job()` RPC(`FOR UPDATE SKIP LOCKED`)로 구현
   (§DB_SCHEMA.md §6).
4. **idempotency를 페이로드 해시까지 검증하도록 강화.** AIR-0227C의 로컬 모의 서버는
   같은 키의 재전송을 무조건 replay 처리했다(다른 payload여도). AIR-0227D의
   `report_worker_render_job_outcome()` RPC는 같은 키+다른 payload를 `409 conflict`로
   명시 거부하고 감사 로그를 남긴다(작업 지시서의 명시적 요구사항).

### 미적용 상태 (정직하게 명시)

`migrations/air_0227d_worker_central_protocol.sql`과 rollback 파일은 **작성만 됐고 어떤
DB에도 적용되지 않았다** - 이 세션에는 staging Supabase 프로젝트 접속 정보가 없어 실제
`CREATE TABLE`/`CREATE FUNCTION` 실행 자체를 검증하지 못했다. SQL은 신중하게 수기 리뷰했지만
(FOR UPDATE 락 순서, RETURN QUERY 흐름, idempotency 분기 등) **실제 Postgres 실행 검증 없이는
staging에도 적용해선 안 된다** - AIR_WORKER_OPERATIONS.md §2의 적용 절차를 따를 것.

## 0. 원칙

"운영 DB migration이 필요하면 SQL 초안과 적용 절차만 작성하고 CTO 승인 없이 운영 DB에
실행하지 않는다"는 지시를 그대로 지켰다 - 아래 SQL은 **어디에도 실행되지 않았다**, 로컬
모의 서버(`worker/dev_central_server/server.py`)는 별도의 로컬 SQLite 파일을 쓰며 이
스키마와 논리적으로 동일하지만 물리적으로 완전히 분리되어 있다.

## 1. 신설 테이블 초안 (Supabase/Postgres 문법)

```sql
-- worker_jobs: AIR Worker가 claim하는 작업 큐. 기존 remote_render_queue와는
-- 별도 테이블로 신설한다 - remote_render_queue는 이미 살아있는 Drive-릴레이
-- 기능이 계속 쓰고 있으므로, 스키마를 공유시키면 두 기능이 서로의 변경에
-- 취약해진다. worker_id/lease 개념 자체가 remote_render_queue에는 없었다.

CREATE TABLE worker_jobs (
    job_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type            text NOT NULL,
    tenant_id           uuid NOT NULL REFERENCES profiles(id),  -- 실제 FK 대상은 운영 스키마 확인 후 확정
    priority            integer NOT NULL DEFAULT 0,
    payload             jsonb NOT NULL,
    status              text NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','leased','completed','failed','cancelled')),
    lease_id            uuid,
    worker_id           text,
    worker_instance_id  text,
    lease_expires_at    timestamptz,
    attempt_number      integer NOT NULL DEFAULT 0,
    max_attempts        integer NOT NULL DEFAULT 3,
    output_ref          text,
    error_message       text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_worker_jobs_claim ON worker_jobs (status, job_type, priority DESC, created_at ASC)
    WHERE status = 'queued';

-- idempotency_seen: complete/fail 요청의 재전송 중복 방지.
CREATE TABLE worker_job_idempotency (
    idempotency_key text PRIMARY KEY,
    job_id          uuid NOT NULL REFERENCES worker_jobs(job_id),
    response        jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- worker_registry: Worker Token 발급 대상 + 권한 범위. 토큰 자체는
-- 자기완결적 HMAC이라 저장하지 않지만, "이 worker_id가 실제로 유효한가/
-- 어떤 job_type을 받을 수 있는가"의 authoritative 소스는 여기.
CREATE TABLE worker_registry (
    worker_id           text PRIMARY KEY,
    tenant_id           uuid NOT NULL REFERENCES profiles(id),
    worker_group        text,
    allowed_job_types   text[] NOT NULL,
    capabilities        jsonb NOT NULL DEFAULT '{}',
    is_legacy           boolean NOT NULL DEFAULT false,  -- Stage 12: 구형 PicadiriRemoteWorker 구분
    disabled_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);
```

## 2. RLS 정책 초안

`worker_jobs`/`worker_job_idempotency`/`worker_registry`는 **service_role 전용** - Worker는
이 테이블을 직접 쿼리하지 않고 auth-web의 `/api/worker/*` 라우트(service_role로 실행되는
서버 코드)를 통해서만 접근한다(원칙 #2/#4 그대로). RLS는 `service_role`만 허용, 다른 모든
role은 차단:

```sql
ALTER TABLE worker_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_job_idempotency ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_registry ENABLE ROW LEVEL SECURITY;
-- 기본적으로 정책이 없으면 service_role을 제외한 모든 접근이 거부됨(Supabase 기본 동작) -
-- 별도 permissive policy를 추가하지 않는 것 자체가 의도된 방어.
```

## 3. 적용 절차 (실행 전 CTO 승인 필요)

1. 스테이징(또는 별도 테스트) Supabase 프로젝트에 먼저 적용, `worker/dev_central_server`의
   테스트 시나리오(§REMOTE_E2E_QA.md)를 auth-web 실제 라우트로 재현해 통과 확인.
2. `worker_registry`에 최소 1개 실 worker_id(AIR Worker) + 1개 legacy worker_id를 등록해
   Stage 12 병행 운영 시나리오도 스테이징에서 재현.
3. 운영 적용은 트래픽이 적은 시간대에, 롤백 스크립트(아래) 준비 후 진행.
4. 적용 직후 `worker_jobs` 테이블에 실제 큐잉/클레임이 없는 상태(신규 테이블이므로 당연히
   비어있음)임을 확인 - 기존 기능(remote_render_queue 기반 Drive 릴레이)에 영향 없음을
   재확인.

## 4. 롤백

```sql
DROP TABLE IF EXISTS worker_job_idempotency;
DROP TABLE IF EXISTS worker_jobs;
DROP TABLE IF EXISTS worker_registry;
```
신규 테이블뿐이라 기존 데이터에 대한 영향이 없어 롤백이 단순하다 - 기존 테이블 변경(ALTER)은
전혀 포함되어 있지 않다.
