# AIR Worker — Lease 기반 작업 소유권 (AIR-0227C Stage 5/6)

- 상태: **구현 + 로컬 모의 중앙 서버로 실측 검증 완료**
- 구현: `worker/job_store.py` (lease 컬럼), `worker/central_client.py`, `worker/render_worker.py`, `worker/dev_central_server/server.py`
- 관련 문서: [JOB_RECOVERY](./AIR_WORKER_JOB_RECOVERY.md) (AIR-0227B의 PID 기반 로컬 복구는 그대로 유지 - 로컬 dev job에는 계속 적용), [REMOTE_E2E_QA](./AIR_WORKER_REMOTE_E2E_QA.md)

## 1. 왜 PID를 버렸는가

AIR-0227B에서 이미 한 번 겪은 문제(`AIR_WORKER_JOB_RECOVERY.md`의 "pid 불일치" 버그)가
그대로 재발할 자리였다 - 이 로컬 Windows venv 환경은 `subprocess.Popen`이 돌려주는 pid와
자식 프로세스가 스스로 인식하는 pid가 다르다(런처 재실행 구조). 로컬 작업은 이미 그 버그를
고친 방식(pid 매칭 없이 "현재 살아있는 Render Worker가 없으면 전부 고아"로 판정)으로
우회했지만, **원격 lease는 애초에 PID라는 개념 자체가 없다** - 중앙 서버는 이 워커의 OS
프로세스에 대해 아무것도 모르고 알아서도 안 된다. lease_id + worker_instance_id가 유일하게
유효한 소유권 증명이다.

## 2. 필드 (지시사항 그대로, job_store.py에 구현)

```
lease_id            TEXT   - 서버가 claim 성공 시 발급, 매 claim마다 새 값
worker_instance_id  TEXT   - Manager 프로세스 시작 시 1회 생성한 uuid4 (§3)
lease_expires_at    REAL   - 서버가 발급/갱신
heartbeat_at        -      - 기존 render_worker.json 상태 파일의 heartbeat_at 재사용
attempt_number      INTEGER - 서버 쪽 claim 테이블에서 관리(재할당마다 증가)
remote_job_id        TEXT   - 로컬 job_id와 원격 job_id를 잇는 매핑
remote_ack_status    TEXT   - 'pending'/'acked'/'abandoned' (§5)
```

## 3. Worker Instance ID (Stage 6)

`worker/manager.py::WorkerManager.__init__`이 `uuid.uuid4().hex`를 1회 생성해
`self.worker_instance_id`에 보관하고, `start_process()`가 모든 자식 프로세스에
`AIRWORKER_INSTANCE_ID` 환경변수로 전파한다. **Manager가 재시작되면 무조건 새 값** - 이전
instance가 만료 안 된 작업을 새 instance가 마음대로 완료 처리할 수 없다(claim/complete
요청의 `worker_instance_id`가 서버에 기록된 lease 소유자와 일치해야 하므로, 재시작 후에는
자동으로 불일치 → 거부됨).

## 4. 규칙과 실측 결과

| 규칙 | 실측 검증 |
|---|---|
| claim 성공 시 lease_id 발급 | ✅ `/api/worker/jobs/claim` 응답에 lease_id + lease_expires_at |
| progress/complete/fail 요청 시 lease_id 검증 | ✅ `_check_lease()`가 status/lease_id/worker_instance_id/만료 4중 확인 |
| lease 만료 후 이전 Worker의 완료 보고 거부 | ✅ 실측: 만료된 lease_id로 `/complete` 호출 → `409 job is not in leased state` |
| Worker가 주기적으로 lease 연장 | ✅ `render_worker.py`의 백그라운드 스레드가 `LEASE_RENEW_INTERVAL_SECONDS=3s`마다 갱신 - 실측: 8초 TTL로 설정한 모의 서버에서 ~20초 렌더링 동안 6회 갱신 로그 확인, 정상 완료 |
| Worker 크래시/네트워크 단절 시 lease 만료 | ✅ 실측: RENDERING 중 강제 종료 → 갱신 중단 → 다음 claim() 호출 시 만료된 lease가 스윕되어 재할당(`attempt_number: 2`로 확인) |
| 만료 작업은 ABANDONED 또는 재할당 대상 | ✅ 재할당까지 실측 확인. 로컬 job_store 쪽은 기존 AIR-0227B 복구 로직(ABANDONED, `max_retries=0`이라 로컬 재시도는 없음 - 재시도 소유권은 중앙 서버가 가짐)이 그대로 적용 |
| 중복 완료 방지(idempotency) | ✅ `Idempotency-Key` 헤더(로컬 job_id) - 실측: 동일 키로 2번 호출 시 두 번째는 `idempotent_replay: true`, 첫 응답 그대로 재반환(두 번째 호출의 다른 output_ref는 무시됨) |
| 로컬 SQLite에도 lease_id/worker_instance_id 저장 | ✅ `job_store.create_from_remote_claim()` |

## 5. 실행 중 발견한 두 가지 버그와 수정 (REMOTE_E2E_QA.md에 상세 로그)

1. **409 응답이 처리되지 않아 프로세스 크래시**: `_report_remote_outcome()`이 좁은 예외만
   잡아서, 예상 밖 409가 `process_one_job`의 바깥 `except Exception`까지 새어나갔고, 그
   핸들러가 이미 COMPLETED인 작업을 FAILED로 전이하려다 `InvalidTransitionError`를 내며
   전체 프로세스가 죽었다. **수정**: 원격 보고 실패는 로컬 상태 기계와 완전히 분리 -
   `except Exception`으로 넓게 잡고 절대 위로 전파하지 않음.
2. **lease TTL보다 긴 네트워크 장애 시 중복 렌더링 가능성**: 장애 중 완료 보고가 실패해
   `remote_ack_status='pending'`으로 남는데, 같은 시간 동안 원본 lease가 만료되어 서버가
   그 작업을 "재할당 가능"으로 스윕한다 - 그 결과 **같은 워커가 스스로 그 작업을 다시
   claim해서 두 번째로 렌더링**하는 것을 실측으로 확인했다. 서버 쪽 idempotency는 정상
   동작해 "완료 기록이 두 번 남는" 사고는 막았지만, **워커가 이미 끝난 작업을 다시
   렌더링하는 낭비 자체는 완전히 막지 못한다** - 아래 §6에 알려진 제한사항으로 명시.

## 6. 알려진 제한사항 (정직하게 명시, 완전히 해결하지 않음)

`lease TTL < 실제 네트워크 장애 지속시간`인 상황에서, 갱신도 실패하고 완료 보고도 실패하는
동안 서버가 lease를 스윕해버리면, 같은 워커(또는 다른 워커)가 이미 로컬에서 끝난 작업을
다시 클레임해 중복 렌더링할 수 있다. 이번 Task에서 부분적으로만 완화했다:
- `LeaseConflict`(409)를 받으면 무한 재시도를 멈추고 `remote_ack_status='abandoned'`로
  전환해 최소한 헛된 재시도 로그가 영원히 쌓이는 건 막았다(실측 확인, 유닛 테스트로 재현).
- 완전한 해결(예: lease를 잃은 것을 감지하면 진행 중인 렌더 자체를 중단하거나, 서버가
  콘텐츠 체크섬으로 중복 결과를 감지)은 이번 Task 범위 밖 - **다음 Task(AIR-0227D 이후)
  후보로 제안**. 실무적으로는 lease TTL을 실제 평균 렌더 시간의 여러 배로 넉넉히 설정하면
  (모의 서버의 8초는 테스트 편의를 위한 값, 운영값은 분 단위가 되어야 함) 위험을 크게
  낮출 수 있다는 점도 함께 기록해둔다.
