# AIR Worker — Staging 원격 E2E QA (AIR-0227D)

- 상태: **미실행 - staging Supabase/Vercel 접속 정보가 이 세션에 없음**
- 관련 문서: [CENTRAL_API](./AIR_WORKER_CENTRAL_API.md), [DB_SCHEMA](./AIR_WORKER_DB_SCHEMA.md), [DRIVE_LIVE_QA](./AIR_WORKER_DRIVE_LIVE_QA.md)

## 0. 이 문서가 "결과 없이" 존재하는 이유

작업 지시서 13단계(Staging 원격 E2E)와 15단계(구형 Worker 병행)는 실제 staging DB +
실제 배포된 auth-web 인스턴스가 있어야 실행 가능하다. 이 세션은:
- staging Supabase 프로젝트의 접속 정보(URL/service_role key/DB 비밀번호)를 받지 않았다
- auth-web을 Vercel(또는 다른 곳)의 staging 환경에 배포할 권한/자격증명이 없다
- 로컬에 Docker/psql이 없어 Postgres 자체를 임시로도 띄우지 못했다(§DB_SCHEMA.md §10)

그래서 이 문서는 "실행 결과"가 아니라 **실행 계획 + 완료 기준**이다. §AIR_WORKER_OPERATIONS.md
§2에 실제 적용 절차가 있다.

## 1. 사전 준비 (CTO 또는 인프라 담당자)

1. staging Supabase 프로젝트(운영과 분리된 프로젝트, 또는 최소한 별도 스키마) 접속 정보
2. `migrations/air_0227d_worker_central_protocol.sql` 적용 권한
3. auth-web을 그 staging Supabase를 가리키도록 배포(Vercel preview 배포 또는 별도 staging URL)
4. `AIRWORKER_LEASE_TTL_SECONDS` 등 환경변수 설정 권한

## 2. 실행 계획

```
1. §OPERATIONS.md §2 절차대로 migrations/air_0227d_worker_central_protocol.sql을
   staging에 적용, 아래 스모크 테스트로 4개 RPC가 실제로 생성/호출 가능한지 확인
     SELECT * FROM claim_worker_render_job('probe','probe-inst','{render_video}','air-worker',300);
   (빈 결과가 정상 - 큐가 비어있으므로)

2. POST /api/admin/worker-tokens 로 테스트 worker_id 하나에 토큰 발급

3. 관리자가 remote_render_queue에 실제 fixture 작업 1건 직접 INSERT (§DRIVE_LIVE_QA.md의
   격리 폴더를 source로) - "관리자 API로 job 생성"은 이번 범위에 없으므로(§CENTRAL_API.md §0,
   지시서 15단계가 "운영 UI 전체를 만들 필요는 없다"고 명시) 직접 INSERT 또는 별도 fixture
   스크립트로 대체

4. worker/worker_config.py의 AIRWORKER_CENTRAL_SERVER_URL을 staging auth-web URL로,
   AIRWORKER_TOKEN을 위에서 발급한 토큰으로 설정 후 실제 AIR Worker(manager.py) 기동

5. 전체 흐름 관찰: claim -> lease 발급 -> Drive 다운로드(§DRIVE_LIVE_QA.md) ->
   PREPARING -> RENDERING(진행률 보고) -> UPLOADING -> Drive 업로드 -> complete

6. 확인 항목:
   - remote_render_queue.status='completed', worker_status='COMPLETED'
   - result_reference/result_file_id에 실제 Drive file id
   - worker_job_events에 claim/progress(복수)/complete 이벤트 순서대로 기록
   - worker_idempotency_keys에 1건, 같은 키로 재요청 시 idempotent_replay
   - 결과 파일을 재다운로드해 ffprobe로 재생 가능 확인
   - 렌더링 도중 heartbeat_at/lease_expires_at이 실제로 갱신되는지 (renew 호출 로그)
   - 절대 로그에 원문 토큰/Drive 자격증명이 찍히지 않는지 확인

7. 구형 워커 병행(15단계): 같은 staging DB에서 PicadiriRemoteWorker(레거시)를 동시에
   기동, worker_group 필터로 서로 다른 큐 항목만 집는지, 혹은 worker_group=NULL 공용
   항목 하나를 동시에 claim 시도했을 때 정확히 하나만 성공하는지 확인
   (claim_worker_render_job은 legacy의 PostgREST 방식과 다른 경로지만 같은 테이블 행을
   대상으로 하므로, Postgres 행 잠금 수준에서는 여전히 상호 배타적이다 - PostgREST의
   조건부 PATCH도 내부적으로 `UPDATE ... WHERE status='pending'`이라 SKIP LOCKED RPC와
   동시에 실행되면 둘 중 하나만 행을 갱신에 성공한다. 다만 이 상호작용 자체는
   실제로 실행해 확인한 적이 없다 - staging에서 반드시 재확인 필요)

## 3. 완료 기준 (Go 판정에 필요)

- [ ] migrations/air_0227d_worker_central_protocol.sql이 staging에 오류 없이 적용됨
- [ ] 4개 RPC 전부 정상 호출됨(문법 오류 없음)
- [ ] 위 §2의 6번 확인 항목 전부 통과
- [ ] 10-way 동시 claim 테스트가 staging Postgres에서 재현되어 정확히 1건만 성공
- [ ] 구형 워커 병행 시나리오 통과
- [ ] Vercel 함수 타임아웃 내에 claim/heartbeat/progress/complete 각각 완료(§OPERATIONS.md §4)
