# AIR Worker — 운영 DB 마이그레이션 초안 (AIR-0227C)

- 상태: **SQL 초안만 - 운영 DB에 실행하지 않았음, CTO 승인 필요**
- 관련 문서: [AUTH](./AIR_WORKER_AUTH.md), [LEASE_PROTOCOL](./AIR_WORKER_LEASE_PROTOCOL.md)

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
