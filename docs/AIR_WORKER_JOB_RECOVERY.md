# AIR Worker — Job 상태 기계, 복구, 취소 정책

- 관련 문서: [JOB_PROTOCOL](./AIR_WORKER_JOB_PROTOCOL.md), [RENDER_ADAPTER](./AIR_WORKER_RENDER_ADAPTER.md), [SHUTDOWN_PROTOCOL](./AIR_WORKER_SHUTDOWN_PROTOCOL.md)
- 구현: `worker/job_store.py`

## 1. 상태 기계

```
QUEUED → CLAIMED → PREPARING → RENDERING → UPLOADING → COMPLETED
   ↓         ↓          ↓           ↓            ↓
CANCELED  CANCELED/  CANCELED/   CANCELED/    CANCELED/
          FAILED/    FAILED/     FAILED/      FAILED/
          ABANDONED  ABANDONED   ABANDONED    ABANDONED

FAILED     → QUEUED (retry_count < max_retries일 때만)
ABANDONED  → QUEUED (재시도) 또는 FAILED (재시도 소진, 격리)
```

전이는 `job_store.transition()`이 `TRANSITIONS` 테이블로 검증한다 — 정의되지 않은 전이는
`InvalidTransitionError`를 던진다. 모든 전이는 `job_transitions` 테이블에 `(from, to, at,
reason)`으로 로그된다 — `GET /jobs/{id}`가 이 이력을 그대로 반환한다.

## 2. 취소 정책 — 왜 두 갈래인가

`remote_render_executor_func`(실제로 감싸고 있는, 수정하지 않은 렌더 함수)에는 취소 훅이
없다. 그래서 취소는 작업이 어디까지 진행됐는지에 따라 근본적으로 다르게 처리된다:

| 상태 | 처리 | 프로세스 kill 필요? |
|---|---|---|
| QUEUED | 즉시 `job_store.transition(CANCELED)` | 아니오 |
| CLAIMED / PREPARING | cancel flag 파일 기록 → Render Worker가 RENDERING 진입 직전 체크포인트에서 스스로 CANCELED로 전이 (최대 ~4초 대기) | 아니오(성공 시) |
| RENDERING / UPLOADING | Manager가 Render Worker 프로세스 트리를 `taskkill /PID <pid> /T /F`로 강제 종료 후 CANCELED로 전이, 새 Render Worker를 즉시 재시작 | **예** |

CLAIMED/PREPARING에서 소프트 취소를 시도했는데 그 사이 RENDERING으로 넘어가버리면
(레이스), Manager는 상태를 재확인하고 하드 kill로 자동 승격한다 —
`worker/manager.py::_cancel_job()`.

### 실측 검증

- QUEUED 취소: `{'success': True, 'result': 'cancelled_queued'}`, 0.9초 이내 응답, 프로세스
  전혀 건드리지 않음.
- RENDERING 중 하드 취소: `{'success': True, 'result': 'cancelled_hard_kill'}`, 1.7초
  이내 응답. `taskkill /PID <pid> /T /F`가 render_worker.py 프로세스와 그 자식(venv
  런처가 만드는 내부 재실행 프로세스 포함)까지 전부 종료시켰음을 `Get-CimInstance
  Win32_Process`로 확인 — 고아 프로세스 없음. Render Worker는 새 PID로 재시작되어 다음
  작업을 정상적으로 받았다.

## 3. 크래시 복구 (Stage 7)

`job_store.find_stale_active_jobs(alive_pid)` — ACTIVE_STATUSES(CLAIMED/PREPARING/RENDERING/
UPLOADING)에 있는 작업 중, 살아있는 Render Worker가 없는(또는 그 pid가 다른) 것을 찾는다.
`mark_abandoned_and_recover()`가 ABANDONED로 전이한 뒤:
- 이미 유효한 output이 있으면(파일 존재 + 크기 > 0) 재렌더 없이 바로 COMPLETED로 전이
  ("불필요한 재렌더 회피" 요구사항).
- 아니면 `retry_count < max_retries`면 QUEUED로 재큐잉(`retry_count += 1`).
- 재시도 소진 시 `error_code=ABANDONED_MAX_RETRIES_EXCEEDED`로 영구 격리(FAILED, 더 이상
  자동 재시도되지 않음).

두 호출 지점:
1. **시작 시** (`WorkerManager.run_startup_recovery`) — `alive_pid=None`으로 무조건 전수
   스캔. Manager가 완전히 재시작될 때(이전 인스턴스가 어떻게 죽었든) 안전망 역할.
2. **런타임 중 크래시 감지 즉시** (`WorkerManager._recover_jobs_owned_by`) — Health
   Monitor가 Render Worker의 예기치 않은 종료를 감지한 바로 그 tick에 호출.

### 실행 중 발견하고 고친 버그: pid 불일치

처음 구현은 `_recover_jobs_owned_by(dead_pid)`가 `job['worker_pid'] == dead_pid`로 필터링했다.
`dead_pid`는 `subprocess.Popen.pid`(Manager가 자식을 띄울 때 받는 pid)이고,
`job['worker_pid']`는 render_worker.py 자신이 `os.getpid()`로 기록한 pid다. **이 로컬 Windows
Python/venv 환경에서는 이 둘이 다르다** — venv의 `python.exe`가 같은 커맨드라인을 가진
자식 프로세스로 재실행(relaunch)하는 런처 동작 때문에, Manager가 아는 pid와 프로세스
내부에서 보는 자기 자신의 pid가 서로 다르다. `Get-CimInstance Win32_Process`로 실제
부모/자식 pid 쌍(예: 31448 → 41912, 동일 커맨드라인)을 확인해 원인을 확정했다.

실제로 Render Worker를 강제 종료(`Stop-Process -Force`, taskkill이 아니라 kill 신호만)해
재현했더니, 로그에 `[RECOVERY]` 줄이 전혀 안 찍히고 작업이 RENDERING 상태로 영원히
멈춰버리는 걸 확인했다 — Manager 재시작(`run_startup_recovery`, `alive_pid=None`이라 이
버그에 안 걸림) 전까지는 복구되지 않았다.

**수정**: pid 매칭을 완전히 제거했다. Manager는 Render Worker 프로세스를 한 번에 하나만
운영하므로, 그 프로세스의 크래시를 처리하는 바로 그 시점에는 ACTIVE_STATUSES에 있는
어떤 작업도 정의상 고아일 수밖에 없다 — `alive_pid=None`으로 무조건 전수 처리하는 것이
시작 시 복구와 동일한, 더 견고한 정답이었다.

### 실측 검증 (수정 전 vs 수정 후, 둘 다 재현)

**수정 전**: Render Worker를 RENDERING 도중 강제 종료 → Manager가 크래시를 감지하고
`exit_code=4294967295`로 로그, `restart_count` 증가, 새 Render Worker 기동까지는 됐지만
`[RECOVERY]` 로그가 전혀 찍히지 않았다 — pid 불일치로 필터가 아무것도 못 찾은 것.
작업은 Manager를 재시작할 때까지(`run_startup_recovery`, `alive_pid=None`이라 이 버그의
영향을 안 받음) RENDERING 상태로 멈춰 있었다: `[RECOVERY] Found 1 job(s) left active by
a previous run` → `RENDERING -> ABANDONED -> QUEUED`, 재큐잉된 작업이 `retry_count=1`로
다시 렌더링되어 **COMPLETED**까지 도달(진짜 output.mp4 생성 확인).

**수정 후**: 같은 시나리오(Manager 재시작 없이, RENDERING 도중 강제 종료)를 다시
재현했다. 이번에는 크래시 감지 tick 안에서 바로
`[RECOVERY] job 40300b0a-... (owning Render Worker pid=35372 crashed): RENDERING -> QUEUED`가
로그에 찍혔고, 새로 기동된 Render Worker가 곧바로 그 작업을 재클레임해 `retry_count=1`로
다시 렌더링, **Manager를 한 번도 재시작하지 않은 채로 COMPLETED**까지 도달했다 — 시작 시
스캔에만 의존하지 않고 즉시 복구 경로가 실제로 동작함을 확인.
