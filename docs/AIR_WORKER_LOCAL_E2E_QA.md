# AIR Worker — 로컬 E2E 픽스처 및 QA 결과 (AIR-0227B)

- 관련 문서: [RENDER_ADAPTER](./AIR_WORKER_RENDER_ADAPTER.md), [JOB_RECOVERY](./AIR_WORKER_JOB_RECOVERY.md), [SHUTDOWN_PROTOCOL](./AIR_WORKER_SHUTDOWN_PROTOCOL.md)
- 픽스처: `worker/fixture/build_fixture.py` → `worker/fixture/sample_render/`

모든 시나리오는 **실제로 Manager를 띄우고** (`python manager.py`), `cli_status.py`와
`curl`/PowerShell로 상태를 조작·관찰하며 라이브로 검증했다. 정적 코드 리뷰만으로는
아래 3개 버그를 하나도 못 찾았을 것 — 전부 실행 중에 발견하고 그 자리에서 고친 뒤
재검증했다.

## 1. 픽스처

`worker/fixture/build_fixture.py`가 매번 새로 생성:
- `images/scene1.jpg`, `scene2.jpg` — ffmpeg `testsrc`/`smptebars`로 만든 1280x720 정지 이미지
- `audio/voice.mp3` — 4초 무음 mono 트랙
- `config.json` — `remote_render_executor_func`가 기대하는 정확한 스키마(`app_mode:
  "longform"`, `aspect_ratio: "16:9"`, `resolution: "720p"`, 두 이미지에 대한
  `image_timing_starts`)

`cli_status.py --submit-fixture`로 `render_video` 작업을 로컬 API에 제출한다.

## 2. 발견하고 고친 버그 (실행 QA로만 발견)

| # | 증상 | 근본 원인 | 수정 |
|---|---|---|---|
| 1 | `video_service.py`가 렌더 도중 `UnicodeEncodeError`로 죽음 | 한국어 Windows 콘솔(cp949)에서 이모지(`🎬`) stdout 출력 실패 — 파이프라인 연동을 처음 실제로 시도하면서 드러남 | `manager.py::start_process`가 모든 자식에 `PYTHONIOENCODING=utf-8` 환경변수 강제 (video_service.py 자체는 미수정) |
| 2 | Render Worker 크래시 후 작업이 RENDERING에 영원히 멈춤, `[RECOVERY]` 로그 없음 | `job['worker_pid']`(자식이 자기 `os.getpid()`로 기록)과 Manager의 `popen.pid`가 이 venv 환경에서 서로 다름(런처 재실행 구조) — 크래시 즉시 복구 필터가 아무것도 못 찾음 | pid 일치 필터 제거, Manager가 Render Worker 크래시를 처리하는 시점엔 ACTIVE 상태의 모든 작업이 정의상 고아이므로 무조건 복구 시도로 단순화 |
| 3 | `--shutdown` 호출 시 로그가 4/13단계에서 멈추고 Render Worker/Local API가 절대 안 죽음 | `shutdown_all` 커맨드가 데몬 스레드에서 `graceful_shutdown()`을 실행했는데, 그 2단계가 `self._stopping=True`를 설정하자마자 메인 스레드의 supervisor loop가 빠져나가 `main()`이 끝나버림 — 데몬 스레드는 인터프리터 종료 시 즉시 잘림 | 스레드를 `daemon=False`로 바꾸고 `main()`이 `.join()`으로 완주를 기다리게 함 |

버그 #1을 우연히 만나면서 "Windows에서 `Popen.terminate()`가 자식의 `SIGTERM` 핸들러를
안 깨운다"는 사실도 구현 착수 전에 먼저 확인해, 시그널 기반이 아니라 파일 플래그 기반
종료 신호(`worker/shutdown_flag.py`)로 처음부터 설계를 바꿨다 — 이건 버그 목록에 안
올렸지만(실행해서 실패를 본 게 아니라 설계 중 재검토로 방지했으므로) 같은 종류의
Windows 특유 가정 오류였다.

## 3. 시나리오 매트릭스 및 결과

### A. 정상 E2E 플로우

| 시나리오 | 결과 |
|---|---|
| A1. 3개 프로세스 기동 (render_worker.py, hermes_worker_mock.py, local_api_process.py) | PASS — `cli_status.py`로 전부 `running`/`idle` 확인, 서로 다른 PID |
| A2. 픽스처 작업 제출 → QUEUED→CLAIMED→PREPARING→RENDERING→UPLOADING→COMPLETED | PASS — 전이 이력 전부 `job_transitions`에 기록, 총 소요 ~20초 |
| A3. 출력물이 진짜 재생 가능한 MP4인가 | PASS — ffprobe로 확인: h264/aac, 1280x720, 24fps, 4.00초, 23,628 bytes |
| A4. 렌더링 중 Hermes 자동 일시정지, 완료 후 자동 재개 | PASS — `manager.log`: `Render job active -> pausing Hermes new-job intake` / `Render queue idle -> resuming Hermes` |
| A5. per-job 로그 파일 생성 및 내용 | PASS — `worker/logs/jobs/<job_id>.log`에 claim/prepare/render/upload/complete 타임스탬프 전부 기록 |

### B. 취소

| 시나리오 | 결과 |
|---|---|
| B1. QUEUED 상태 작업 취소 | PASS — `cancelled_queued`, 0.9초 이내, 프로세스 안 건드림 |
| B2. RENDERING 중인 작업 하드 취소 | PASS — `cancelled_hard_kill`, 1.7초, `taskkill /T /F`로 render_worker 프로세스 트리 전체 종료 확인(`Get-CimInstance`로 고아 프로세스 0개 검증), 새 Render Worker 자동 재시작 후 정상 동작 |

### C. 크래시/복구

| 시나리오 | 결과 |
|---|---|
| C1. Local API 강제 종료 → 자동 재시작 | PASS — pid 32076→44204, restart_count 1→2 |
| C2. Render Worker RENDERING 중 강제 종료 → 즉시(Manager 재시작 없이) 복구 | PASS(버그 수정 후) — 같은 tick에 `[RECOVERY] ... RENDERING -> QUEUED`, 재큐잉된 작업이 `retry_count=1`로 재렌더링되어 COMPLETED |
| C3. 복구된 작업이 이미 유효한 output을 가지고 있으면 재렌더 생략 | 코드 경로 존재(`mark_abandoned_and_recover`의 output_path 존재 확인), 이번 QA 세션에서 이 특정 분기는 별도 재현 안 함 — 코드 리뷰로만 확인 |
| C4. 10분 창 내 3회 연속 크래시 → 자동 비활성화 | PASS — `render_worker: disabled`, `disabled_reason: "3 crashes within 600s (limit 3)"`, `--start render` 시도 시 `{'success': False}` + `Refusing to start` 로그로 정상 거부 |
| C5. 한 프로세스가 죽거나 비활성화되어도 다른 프로세스는 영향 없음 | PASS — render_worker가 disabled인 동안 hermes_worker/local_api 계속 `running` |

### D. 종료

| 시나리오 | 결과 |
|---|---|
| D1. 정상 상태(활성 작업 없음)에서 `--shutdown` | PASS(수정 후) — 11단계 전부 로그, `total_elapsed=2.22s`, `leftover_pids=0` |
| D2. 종료 후 프로세스 트리 확인 | PASS — `Get-CimInstance Win32_Process`로 manager.py/render_worker.py/hermes_worker_mock.py/local_api_process.py 커맨드라인을 가진 프로세스 0개 |
| D3. `os._exit` 없이 Manager 프로세스 자체가 정상 종료되는가 | PASS — `main()`이 정상 반환, 인터프리터가 스스로 끝남 (하드 kill 로그 없음) |

### 실행하지 않은 시나리오 (알려진 갭)

- RENDERING 도중 Manager 자체(자식이 아니라 부모)가 강제 종료되는 경우의 고아-프로세스
  거동 — Windows Job Object 상속 여부에 따라 다를 수 있음, 다음 Task 후보.
- 여러 작업이 동시에 QUEUED되어 있을 때 priority/FIFO 순서가 실제로 지켜지는지의 다건
  동시 제출 테스트 — `claim_next_job`의 `ORDER BY priority DESC, created_at ASC`는 코드
  리뷰로만 확인, 별도 다건 시나리오로 실측하지 않음.
- 포트 충돌(8765 already in use) — AIR-0227A 스켈레톤 QA에서 이미 검증된 항목이라 이번
  세션에서 재실행하지 않음(코드 변경 없음: `LOCAL_API_PORT` 로직 그대로).
