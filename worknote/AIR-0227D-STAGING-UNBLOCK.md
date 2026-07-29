# AIR-0227D-STAGING-UNBLOCK — 경로 불일치 버그 수정 + 로컬 E2E 재검증

## Task ID
`AIR-0227D-STAGING-UNBLOCK`

## Date
`2026-07-13`

## 상태
**부분 진행 — 코드 버그 1건 발견·수정·재검증 완료. staging 자격증명 없이 진행 가능한 작업은
여기까지이며, 나머지(실 Supabase 적용/실 auth-web 배포/실 관리자 계정/실 Drive)는 사용자
확인 대기.**

브랜치: `feat/air-0227d-staging-unblock` (base: `feat/air-0227e-p2-installer-validation`, PR #84 브랜치)

---

## 1. 발견한 버그

`worker/central_client.py`가 호출하는 경로(`/api/worker/register`, `/api/worker/heartbeat`,
`/api/worker/jobs/claim`, `/api/worker/jobs/{id}/{progress,complete,fail}`,
`/api/worker/jobs/{id}/renew-lease`)가 **실제로 구현된 auth-web 라우트와 다르다**:

- 실제 구현: `auth-web/app/api/internal/worker/{register,heartbeat}/route.ts`,
  `auth-web/app/api/internal/worker/jobs/claim/route.ts`,
  `auth-web/app/api/internal/worker/jobs/[jobId]/{progress,complete,fail,renew}/route.ts`
  (`docs/AIR_WORKER_CENTRAL_API.md` §1 표와 정확히 일치).
- 즉 접두사가 `/api/worker/*`가 아니라 `/api/internal/worker/*`이고, `renew-lease`가 아니라
  `renew`다.
- **이 버그 때문에 staging 자격증명이 있었어도 `AIRWORKER_CENTRAL_SERVER_URL`을 실 staging
  auth-web URL로 바꾸는 순간 모든 호출이 404가 났을 것** — 순수 자격증명 문제가 아니라
  진짜 코드 결함이었다.
- `worker/dev_central_server/server.py`(로컬 모의 서버)도 지금까지 구 경로로 구현되어 있어서,
  이 불일치가 로컬 E2E 테스트에서는 드러나지 않고 숨어 있었다(모의 서버가 잘못된 계약을
  그대로 미러링하고 있었기 때문).

## 2. 수정 내용

- `worker/central_client.py`: 7개 엔드포인트 경로 전부 `/api/internal/worker/*`로 수정,
  `renew_lease()` 함수의 경로도 `renew-lease` → `renew`로 수정(함수/변수명은 하위 호환을
  위해 유지, 실제 URL 경로만 수정).
- `worker/dev_central_server/server.py`: 동일하게 7개 라우트 데코레이터 수정 — 로컬 모의
  서버가 이제부터는 실제 auth-web 계약을 정확히 미러링하므로, 이 모의 서버로 검증한 것이
  실제 배포에도 그대로 적용된다는 기존 설계 의도(주석에 명시)가 다시 참이 됨.
- `docs/AIR_WORKER_AUTH.md`, `docs/AIR_WORKER_CENTRAL_API.md`,
  `docs/AIR_WORKER_REMOTE_E2E_QA.md` 상태 라인 갱신.

## 3. 재검증 — 로컬 모의 서버 기준 전체 라운드트립

`worker/dev_central_server`(수정본) + `worker/render_worker.py`를
`AIRWORKER_CENTRAL_SERVER_URL=http://127.0.0.1:8799`로 원격 활성화 모드 실행:

```
Claimed job ... (POST /api/internal/worker/jobs/claim)
-> PREPARING -> RENDERING
Lease renewed (POST /api/internal/worker/jobs/{id}/renew, 3회 이상 반복 확인)
progress=50 (POST /api/internal/worker/jobs/{id}/progress)
-> UPLOADING -> COMPLETED
Central server acknowledged completion (POST /api/internal/worker/jobs/{id}/complete)
```

수정 전(구 경로 그대로 재현 테스트)에는 `claim` 호출부터 404가 반복 발생함을 먼저
확인했고, 수정 후 위 라운드트립이 정상 완료되는 것으로 대조 확인.

**부수 발견(회귀 아님, 테스트 방법론 이슈)**: 이 테스트를 `python render_worker.py`로 직접
실행했을 때(즉 `air_worker_entry.py`/`manager.py`를 거치지 않고) 이미 알려진 cp949 이모지
인코딩 문제(§AIR-0227E 문서에 기록된 것과 동일)가 재현됐다 — `PYTHONIOENCODING=utf-8`을
직접 넘겨주지 않았기 때문(정상 배포 경로인 Manager 경유 실행에서는 이미 해결된 문제).
새로운 버그 아님, 테스트 스크립트가 그 env var를 빠뜨린 것 — 재현 후 env var를 추가해
정상 동작 확인.

## 4. staging 자격증명 없이는 더 진행할 수 없는 부분

`docs/AIR_WORKER_STAGING_E2E_QA.md`(§1)/`docs/AIR_WORKER_DRIVE_LIVE_QA.md`(§1)에 이미
정리된 체크리스트 그대로 — 다음이 없으면 이 이상 실행/검증이 불가능:

1. 프로덕션과 분리된 staging Supabase 프로젝트(URL, `SUPABASE_SERVICE_ROLE_KEY`,
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`).
2. `migrations/air_0227d_worker_central_protocol.sql`을 그 staging 프로젝트에 적용할 권한.
3. 위 값들로 구성된 staging auth-web 배포(Vercel preview 등).
4. staging에 슈퍼관리자 테스트 계정 1개 — **주의**: `requireSuperAdmin`(`auth-web/app/api/admin/_auth.ts`)이
   이메일 `ejsh0519@naver.com`을 하드코딩 비교한다 — staging에서 Worker Token을 발급하려면
   (a) 그 계정을 staging `auth.users`에 그대로 두거나, (b) staging용으로 다른 슈퍼관리자
   식별 방식을 코드에 추가해야 한다. 이건 사용자와 함께 결정할 사안.
5. 격리된 Google Drive 테스트 자격증명 + 입/출력 폴더 ID + 테스트 파일.

이번 세션은 이 중 아무것도 갖고 있지 않아 §STAGING_E2E_QA/§DRIVE_LIVE_QA의 나머지 항목은
착수하지 못했다.

## 다음 단계 (갱신: 사용자가 staging 대신 프로덕션 직접 진행을 명시적으로 선택함, 위험 인지)

사용자 지시: "staging Supabase 하지말고 현재 supabase 계정에 바로 연결... 위험 인지하고
진행한다." 이에 따라 아래 5. 항목으로 이어서 실제 프로덕션 DB에 대해 진행함.

## 5. 프로덕션 DB 적용 + 등록/토큰 발급 + RPC 레벨 실측 (Method A)

- `migrations/air_0227d_worker_central_protocol.sql`을 사용자가 직접 Supabase SQL Editor
  (프로젝트 `picadiri`, `main/PRODUCTION`)에서 실행 — "Success. No rows returned" 확인.
- `service_role` 키(`auth-web/.env.local`, 사용자가 직접 저장)를 이용해 PostgREST로
  `workers` 테이블에 `worker_id=air-worker-01` 등록, `worker_tokens` 테이블에
  `auth-web/lib/workerAuth.ts`와 동일한 스킴(`awt_<token_id>_<secret>`,
  `token_hash=sha256(secret)` hex)으로 토큰 1건 직접 발급 — 실제 admin UI/API 배포 없이
  DB에 바로 삽입(Method A). 원문 토큰은 채팅에 노출하지 않고 로컬 파일에만 저장.
- **RPC 레벨 실제 왕복 테스트** — 임시로 태그된 테스트 잡(`project_id=-999001`,
  `project_name=AIR-0227D-DB-RPC-TEST-DELETE-ME`, 실 프로젝트와 FK 없음)을 실 프로덕션
  `remote_render_queue`에 seed 후, `service_role` 키로 4개 RPC를 실제 순서대로 호출:
  `claim_worker_render_job`(200, 정상 claim+lease 발급) → `renew_worker_render_job_lease`
  (200) → `report_worker_render_job_progress` x2 (PREPARING→RENDERING, 200) →
  `report_worker_render_job_outcome`(success=true, 200, `outcome:"ok"`, 최종
  `status=completed`/`worker_status=COMPLETED`) → 같은 idempotency-key로 재호출(다른
  `output_ref`) → 최초 저장값(`test-output-ref`)이 그대로 유지됨을 확인(재적용 안 됨) →
  테스트 잡 즉시 삭제(cleanup, 204) — 실 admin 대시보드의 "리모트 렌더 큐" 탭에 남지 않도록.
- **경계 정직하게 명시**: 이 테스트는 `service_role` 키로 **RPC를 직접 호출**한 것이지,
  실제 auth-web Next.js 라우트(`/api/internal/worker/**`, `workerAuth.ts`의
  `authenticateWorkerRequest` 포함)를 거친 것이 아니다 — 그 라우트 코드는 아직 배포
  브랜치(main 미병합)에만 있어 이번 세션에서 배포하지 않았다(배포는 별도 승인 필요 - 사용자
  질의 결과 "DB 레벨만 테스트"로 범위를 명시적으로 좁힘). 따라서 검증된 것은 **마이그레이션
  SQL(테이블+RPC 함수)이 실 프로덕션 Postgres에서 정확히 설계대로 동작한다**는 것이고,
  **HTTP 인증 레이어(Bearer 토큰 파싱, 401/409 응답, Idempotency-Key 헤더 처리)는 여전히
  미검증**이다.
- **사소한 설계 관찰**(버그 아님, 기록만): `report_worker_render_job_outcome`이 저장하는
  `response_snapshot`의 `idempotent_replay` 필드는 최초 저장 시점 값(`false`)이 그대로
  재생되므로, 재호출 응답 바디만 봐서는 "이번 호출이 replay였는지"를 알 수 없다(감사로그
  `worker_job_events`에는 `idempotent_replay` 이벤트가 별도로 남아 실제로는 구분 가능).
  데이터 무결성(중복 미적용)에는 영향 없음 — 응답 바디의 자기서술 정확성만의 문제.

## 6. 실 HTTP 레이어 왕복 테스트 (사용자 승인 후 진행) — 완료

사용자가 "HTTP 테스트도 진행" + "자동화 우회 키 만들어서 계속"을 명시적으로 승인함에 따라
진행:

- PR #85(`feat/air-0227d-staging-unblock`, base `feat/air-0227e-p2-installer-validation`)가
  GitHub 연동으로 이미 자동 배포해 둔 실제 Vercel 프리뷰
  (`mytube-git-feat-air-0227d-staging-unblock-eclozers-projects.vercel.app`)를 그대로 사용 —
  새로 배포하지 않음. 이 프리뷰의 환경변수(Preview 스코프)는 프로덕션과 동일한
  `SUPABASE_SERVICE_ROLE_KEY`/`NEXT_PUBLIC_SUPABASE_URL`을 씀 — 별도 staging Supabase가
  없다는 이번 세션의 전제와 일치.
- Vercel의 프리뷰 배포 보호(Deployment Protection/SSO)가 처음엔 모든 요청을 401로 막음 —
  앱 코드의 Worker Token 인증과 무관한, Vercel 자체 보안 레이어. `vercel project protection
  enable mytube --protection-bypass`로 "자동화 우회 비밀키"를 발급받아
  `x-vercel-protection-bypass` 헤더로 우회(SSO 보호 자체는 끄지 않음 - 다른 사람의 접근은
  여전히 차단됨).
- **실제 HTTP 라운드트립 실측** (모두 실제 배포 코드 + 실제 프로덕션 Postgres 대상):
  - 가짜/오염된 토큰으로 `register` 호출 → **401 `unauthorized`/`unknown_token`** (실제
    `workerAuth.ts::authenticateWorkerRequest`가 진짜로 검증하고 있음을 확인)
  - 발급된 진짜 토큰으로 `register`(200) → `heartbeat`(200) → 임시 태그 잡 1건 DB에 seed →
    `claim`(200, 우리 잡을 정확히 반환) → `renew`(200) → `progress`(PREPARING→RENDERING,
    각 200) → `complete`(Idempotency-Key 헤더 포함, 200, `outcome:"ok"`,
    `status:COMPLETED`)
  - `Idempotency-Key` 헤더 누락 시 `complete` 재호출 → **400** (필수 헤더 검증 확인)
  - 최종 DB 상태 조회로 `status=completed`/`result_reference` 정상 반영 확인 후 테스트 잡
    즉시 삭제(204) — 실 관리자 화면에 흔적 없음.
- **결론**: Worker Token → 실제 배포된 auth-web 라우트(`/api/internal/worker/**`) → RPC →
  실 프로덕션 Postgres까지 전체 경로가 실측으로 검증됨. AIR-0227D의 "실 DB/실 서버 기준
  미검증" 상태는 이제 해소됨 — 단, 이번 세션에서 검증한 것은 이 **PR 브랜치의 Vercel
  프리뷰**이지 `main`에 병합된 프로덕션 배포가 아니다(PR은 여전히 미병합 상태 유지, 병합
  여부는 별도 결정).
- **정리 완료**: 테스트 종료 후 사용자 확인을 받아 `vercel project protection disable
  mytube --protection-bypass --protection-bypass-secret <secret>`으로 자동화 우회 키 제거,
  `vercel project protection mytube --format json`으로 `protectionBypass: {}` 확인 —
  프로젝트 보안 설정이 테스트 이전 상태로 원복됨.

## 다음 단계

- Google Drive 실 자격증명 기반 업로드/다운로드 E2E는 여전히 미착수.
- PR #85를 언제/어떻게 병합할지(단계적 rollout, 관리자 UI 배포 시점 등)는 별도 결정 필요.
