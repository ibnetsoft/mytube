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

## 다음 단계

사용자에게 위 5개 항목 중 무엇을 안전한 채널(절대 채팅/로그/git에 값 자체를 남기지 않는
방식)로 제공할 수 있는지 확인 필요 — 이 문서 다음 메시지에서 질의함.
